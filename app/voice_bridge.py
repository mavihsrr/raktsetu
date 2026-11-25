"""Browser <-> Sarvam intake agent bridge over one WebSocket.

The browser captures the mic (with its own echo cancellation) and plays the agent's audio; this
module runs the Sarvam session server-side so the API key never reaches the browser.

Protocol on /api/voice/ws  (optional ?token=<DASHBOARD_TOKEN>)
  browser -> server
    text  {"type": "start", "name": str, "hospital": str, "language": str}   (first message)
    bin   16-bit PCM mono @ 16 kHz mic audio, ~20 ms chunks
    text  {"type": "stop"}
  server -> browser
    text  {"type": "state", "state": "connecting"|"connected"|"ended"|"error", "detail"?: str}
    text  {"type": "greeting", "text": str}
    text  {"type": "transcript", "role": "user"|"agent", "text": str}
    text  {"type": "speech", "who": "user", "phase": "start"|"end"}
    text  {"type": "interrupt"}                     (stop playing buffered agent audio)
    bin   4-byte little-endian sample rate + 16-bit PCM mono agent audio
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import uuid
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketDisconnect

from .config import settings

log = logging.getLogger("raktsetu.voice")

try:  # python.org macOS builds ship without root CAs; Sarvam's websocket needs them.
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:  # pragma: no cover
    pass

HOTWORDS = ["A positive", "A negative", "B positive", "B negative", "O positive", "O negative",
            "AB positive", "AB negative", "packed red cells", "whole blood", "platelets", "crossmatch", "units"]


def _sdk_available() -> bool:
    try:
        import sarvam_conv_ai_sdk  # noqa: F401
        return True
    except Exception:
        return False


def voice_ready() -> bool:
    return settings.sarvam_ready() and bool(settings.sarvam_intake_app_id) and _sdk_available()


def origin_allowed(ws: WebSocket) -> bool:
    """Only this site (same host) or an origin in CORS_ORIGINS may open a voice session, so another
    website can't spend our Sarvam credits from a visitor's browser. Non-browser clients send no Origin."""
    origin = ws.headers.get("origin")
    if not origin:
        return True
    if origin in settings.cors_origins or "*" in settings.cors_origins:
        return True
    host = ws.headers.get("x-forwarded-host") or ws.headers.get("host") or ""
    return urlsplit(origin).netloc == host


async def run_session(ws: WebSocket, context_fn: Callable[[str, str], dict]) -> None:
    if not origin_allowed(ws):
        await ws.close(code=4403)
        return
    await ws.accept()

    async def send(obj: dict) -> None:
        try:
            await ws.send_text(json.dumps(obj))
        except Exception:
            pass

    if not voice_ready():
        await send({"type": "state", "state": "error",
                    "detail": "Voice is not configured on the server (Sarvam intake app)."})
        await ws.close()
        return

    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=15))
    except Exception:
        await ws.close()
        return
    name = str(first.get("name") or "there")[:60]
    hospital = str(first.get("hospital") or "")[:120]
    language = str(first.get("language") or "English")

    try:
        from pydantic import SecretStr
        from sarvam_conv_ai_sdk import (AsyncAudioInterface, AsyncSamvaadAgent, InteractionConfig,
                                        InteractionType, Role, SarvamToolLanguageName)
        from sarvam_conv_ai_sdk.messages.types import ServerMsgType, UserIdentifierType
    except Exception:
        log.exception("Sarvam SDK not importable")
        await send({"type": "state", "state": "error", "detail": "Voice is not installed on the server."})
        await ws.close()
        return

    out_q: asyncio.Queue[bytes | None] = asyncio.Queue()

    class BrowserAudio(AsyncAudioInterface):
        def __init__(self) -> None:
            self.cb: Optional[Callable[[bytes, int], Awaitable[None]]] = None

        async def start(self, input_callback):  # noqa: D401
            self.cb = input_callback

        async def stop(self):
            self.cb = None

        async def output(self, audio: bytes, sample_rate: Optional[int] = None):
            out_q.put_nowait(struct.pack("<I", int(sample_rate or 16000)) + audio)

        def interrupt(self):
            while not out_q.empty():
                out_q.get_nowait()
            asyncio.get_running_loop().create_task(send({"type": "interrupt"}))

        async def feed(self, pcm: bytes) -> None:
            if self.cb and pcm:
                await self.cb(pcm, len(pcm) // 2)

    audio = BrowserAudio()
    ctx = context_fn(name, hospital)

    try:
        lang = SarvamToolLanguageName(language)
    except ValueError:
        lang = SarvamToolLanguageName("English")
    version = settings.sarvam_intake_app_version
    config = InteractionConfig(
        user_identifier_type=UserIdentifierType.CUSTOM,
        user_identifier=f"web-{uuid.uuid4().hex[:12]}",  # one per browser session, never shared
        org_id=settings.sarvam_org_id,
        workspace_id=settings.sarvam_workspace_id,
        app_id=settings.sarvam_intake_app_id,
        version=int(version) if version.isdigit() else None,
        interaction_type=InteractionType.CALL,
        agent_variables=ctx["agent_variables"],
        initial_bot_message=ctx["initial_bot_message"],
        initial_language_name=lang,
        speech_hotwords=HOTWORDS,
        sample_rate=16000,
    )

    async def on_transcript(msg) -> None:
        await send({"type": "transcript", "role": "user" if msg.role == Role.USER else "agent",
                    "text": msg.content})

    async def on_event(ev) -> None:
        t = getattr(ev, "type", "")
        if t == ServerMsgType.USER_SPEECH_START:
            await send({"type": "speech", "who": "user", "phase": "start"})
        elif t == ServerMsgType.USER_SPEECH_END:
            await send({"type": "speech", "who": "user", "phase": "end"})
        elif t == ServerMsgType.INTERACTION_END:
            await send({"type": "state", "state": "ended"})

    # Voice only: this Sarvam intake app has no chat interaction, and a CALL closes on text input.
    agent = AsyncSamvaadAgent(api_key=SecretStr(settings.sarvam_api_key), config=config,
                              audio_interface=audio, transcript_callback=on_transcript,
                              event_callback=on_event)

    async def pump_out() -> None:
        while True:
            chunk = await out_q.get()
            if chunk is None:
                return
            try:
                await ws.send_bytes(chunk)
            except Exception:
                return

    await send({"type": "state", "state": "connecting"})
    pump = asyncio.create_task(pump_out())
    try:
        await agent.start()
        if not await agent.wait_for_connect(timeout=10):
            await send({"type": "state", "state": "error",
                        "detail": "Could not connect to Sarvam. Check the intake app version and API key."})
            return
        await send({"type": "state", "state": "connected"})
        await send({"type": "greeting", "text": ctx["initial_bot_message"]})
        while agent.is_connected():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await audio.feed(msg["bytes"])
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except ValueError:
                    continue
                if data.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("voice session failed")
        await send({"type": "state", "state": "error", "detail": "Voice session failed on the server."})
    finally:
        out_q.put_nowait(None)
        try:
            await agent.stop()
        except Exception:
            pass
        pump.cancel()
        await send({"type": "state", "state": "ended"})
        try:
            await ws.close()
        except Exception:
            pass
