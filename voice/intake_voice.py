"""Laptop mic/speaker client for the Sarvam intake agent ("ChatGPT voice mode" for the coordinator).

The agent's brain (STT + LLM + TTS + tool calling) runs on Sarvam. This script only:
  1. asks our backend for the greeting + context (agent_variables),
  2. opens a Sarvam voice session with the laptop mic/speaker,
  3. prints the live transcript.
The agent calls our backend's HTTP tools itself (find_leads, start_calls, get_status, approve_wave2).

Usage:
  pip install "sarvam-conv-ai-sdk[all]"          # needs PortAudio (brew install portaudio)
  python voice/intake_voice.py --name Shivam
  python voice/intake_voice.py --text             # same agent, typed chat (no mic)

Env (.env in the raktsetu folder): SARVAM_API_KEY, SARVAM_ORG_ID, SARVAM_WORKSPACE_ID,
SARVAM_INTAKE_APP_ID, optional SARVAM_INTAKE_APP_VERSION, BACKEND_URL (default http://localhost:8000),
DASHBOARD_TOKEN if you set one.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

# python.org builds on macOS ship without root CAs; use certifi's bundle for the Sarvam websocket.
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def make_half_duplex_audio(tail_s: float = 0.7):
    """Mic is muted (sent as silence) while the agent's audio plays, plus a short tail.

    The SDK's default interface has no echo cancellation, so on laptop speakers the agent hears
    itself and answers its own words. Trade-off: you cannot talk over the agent.
    """
    import time

    from sarvam_conv_ai_sdk import AsyncDefaultAudioInterface

    class HalfDuplexAudio(AsyncDefaultAudioInterface):
        _mute_until = 0.0

        def _agent_audible(self) -> bool:
            return (self.output_queue is not None and not self.output_queue.empty()) \
                or time.monotonic() < self._mute_until

        def _pyaudio_input_callback(self, in_data, frame_count, time_info, status):
            if self._agent_audible():
                in_data = b"\x00" * len(in_data)
            return super()._pyaudio_input_callback(in_data, frame_count, time_info, status)

        async def _output_task(self):
            try:
                while self.should_stop and not self.should_stop.is_set():
                    audio_data, sample_rate = await self.output_queue.get()
                    if sample_rate != self.current_output_sample_rate:
                        await self._recreate_output_stream(sample_rate)
                    self._mute_until = time.monotonic() + 10  # muted while this chunk plays
                    await asyncio.to_thread(self.output_stream.write, audio_data)
                    self._mute_until = time.monotonic() + tail_s
            except asyncio.CancelledError:
                pass

    return HalfDuplexAudio(input_sample_rate=16000)


def need(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"Missing {name} in environment/.env")
    return v


async def fetch_context(name: str, hospital: str) -> dict:
    url = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
    headers = {}
    if os.environ.get("DASHBOARD_TOKEN"):
        headers["X-Dashboard-Token"] = os.environ["DASHBOARD_TOKEN"]
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{url}/api/intake/context", params={"coordinator_name": name, "hospital": hospital},
                            headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"(backend context unavailable: {e}; using a plain greeting)")
        return {"agent_variables": {"coordinator_name": name, "default_hospital": hospital, "active_requests": "[]"},
                "initial_bot_message": f"Hi {name}, RaktSetu here. What blood do you need, how many units, and by when?"}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=os.environ.get("COORDINATOR_NAME", "there"))
    ap.add_argument("--hospital", default=os.environ.get("DEFAULT_HOSPITAL", ""), help="optional; if empty the agent asks")
    ap.add_argument("--language", default="English", help="English, Hindi, Kannada, ...")
    ap.add_argument("--text", action="store_true", help="typed chat instead of mic/speaker")
    ap.add_argument("--barge-in", action="store_true",
                    help="keep the mic open while the agent talks (only with headphones)")
    args = ap.parse_args()

    from pydantic import SecretStr
    from sarvam_conv_ai_sdk import (AsyncSamvaadAgent, InteractionConfig, InteractionType, Role,
                                    ServerTranscriptMsg, SarvamToolLanguageName)
    from sarvam_conv_ai_sdk.messages.types import UserIdentifierType

    ctx = await fetch_context(args.name, args.hospital)
    print(f"Greeting: {ctx['initial_bot_message']}\n")

    version = os.environ.get("SARVAM_INTAKE_APP_VERSION", "").strip()
    config = InteractionConfig(
        user_identifier_type=UserIdentifierType.CUSTOM,
        user_identifier=f"coordinator-{args.name.lower()}",
        org_id=need("SARVAM_ORG_ID"),
        workspace_id=need("SARVAM_WORKSPACE_ID"),
        app_id=need("SARVAM_INTAKE_APP_ID"),
        version=int(version) if version.isdigit() else None,
        interaction_type=InteractionType.CHAT if args.text else InteractionType.CALL,
        agent_variables=ctx["agent_variables"],
        initial_bot_message=ctx["initial_bot_message"],
        initial_language_name=SarvamToolLanguageName(args.language),
        speech_hotwords=["B positive", "O negative", "packed red cells", "platelets", "crossmatch",
                         "Koramangala", "Basavanagudi", "Jayanagar"],
        sample_rate=16000,
    )

    async def on_transcript(msg: ServerTranscriptMsg) -> None:
        who = "You  " if msg.role == Role.USER else "Agent"
        print(f"{who}: {msg.content}")

    async def on_text(msg) -> None:
        print(f"Agent: {getattr(msg, 'text', msg)}")

    async def on_event(ev) -> None:
        t = getattr(ev, "type", "")
        if t and "interrupt" not in str(t):
            print(f"  · {t}")

    kwargs = dict(api_key=SecretStr(need("SARVAM_API_KEY")), config=config, event_callback=on_event)
    if args.text:
        kwargs["text_callback"] = on_text
    else:
        if args.barge_in:
            from sarvam_conv_ai_sdk import AsyncDefaultAudioInterface

            kwargs["audio_interface"] = AsyncDefaultAudioInterface(input_sample_rate=16000)
        else:
            kwargs["audio_interface"] = make_half_duplex_audio()
        kwargs["transcript_callback"] = on_transcript

    agent = AsyncSamvaadAgent(**kwargs)
    await agent.start()
    if not await agent.wait_for_connect(timeout=10):
        await agent.stop()
        sys.exit("Could not connect to Sarvam (check app id has a committed version, and the API key).")
    print(f"Connected (interaction {agent.get_interaction_id()}). "
          + ("Type messages; 'quit' to end." if args.text else "Speak now. Ctrl+C to end."))
    try:
        if args.text:
            loop = asyncio.get_running_loop()
            while agent.is_connected():
                line = await loop.run_in_executor(None, input, "")
                if line.strip().lower() in ("quit", "exit"):
                    break
                if line.strip():
                    await agent.send_text(line)
        else:
            await agent.wait_for_disconnect()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        await agent.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
