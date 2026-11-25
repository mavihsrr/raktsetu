"""Two ways to make a call; both end in the same normalised CallResult.

- SimulatedDialer: plays out a fictional DONOR call from seed `sim` data (labelled SIM everywhere).
  Bank calls are never simulated: banks are real (e-RaktKosh) and only ever phoned for real.
- SarvamDialer: Sarvam Instant Outbound to an allow-listed teammate phone; the result arrives
  later on our webhook and is normalised by `parse_sarvam_webhook`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import settings
from .medical import COMPONENTS, compatible_groups, spoken_group


@dataclass
class CallResult:
    status: str                     # completed | no_answer | busy | failed
    confirmed_units: int = 0        # bank: exact-group units confirmed on the phone
    alt_units: int = 0              # bank: compatible-group units (packed red cells only)
    alt_group: str | None = None
    hold_hours: int | None = None
    willing: str | None = None      # donor: yes | no | later
    notes: str = ""
    transcript: list[dict[str, str]] = field(default_factory=list)


# --------------------------------------------------------------------------- simulated
class SimulatedDialer:
    def __init__(self, speed: float | None = None):
        self.speed = settings.sim_speed if speed is None else speed

    async def _sleep(self, rng: random.Random, lo: float, hi: float) -> None:
        if self.speed > 0:
            await asyncio.sleep(rng.uniform(lo, hi) * self.speed)
        else:
            await asyncio.sleep(0)

    async def call_donor(self, request: dict, donor: dict) -> CallResult:
        rng = random.Random(f"{request['id']}:{donor['id']}")
        sim = donor["sim"]
        await self._sleep(rng, 1.5, 3.5)
        if sim["answer"] != "answered":
            return CallResult(status=sim["answer"], notes="No answer" if sim["answer"] == "no_answer" else sim["answer"])
        await self._sleep(rng, 3.0, 6.0)
        willing = sim.get("willing") or "no"
        reply = {"yes": "Yes, I can come tomorrow morning.", "later": "Not this week, maybe next week.",
                 "no": "Sorry, I can't right now."}[willing]
        t = [
            {"role": "agent", "text": f"Hi {donor['name'].split()[0]}, you opted in to donor recall. Blood stocks "
                                      f"of {spoken_group(request['blood_group'])} are low near you after the holidays. "
                                      "Would you be able to donate at a blood bank to restock?"},
            {"role": "user", "text": reply},
        ]
        return CallResult(status="completed", willing=willing,
                          notes={"yes": "Can come tomorrow morning", "later": "Next week", "no": "Declined"}[willing],
                          transcript=t)


# --------------------------------------------------------------------------- Sarvam live
def webhook_signature(call_id: str) -> str:
    return hmac.new(settings.webhook_secret.encode(), call_id.encode(), hashlib.sha256).hexdigest()[:32]


def _int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def parse_sarvam_webhook(payload: dict, target_type: str) -> CallResult:
    """Normalise a Sarvam outbound webhook (status, final_agent_variables, interaction_transcript)."""
    raw_status = str(payload.get("status", "failed")).lower()
    status = {"connected": "completed", "completed": "completed", "no_answer": "no_answer",
              "busy": "busy"}.get(raw_status, "failed")
    v = payload.get("final_agent_variables") or {}
    transcript = [{"role": str(t.get("role", "")), "text": str(t.get("en_text") or t.get("text") or "")}
                  for t in (payload.get("interaction_transcript") or []) if isinstance(t, dict)]
    if status != "completed":
        return CallResult(status=status, notes=raw_status, transcript=transcript)
    if target_type == "bank":
        from .medical import parse_blood_group, InputError
        alt_group = v.get("alt_group") or None
        if alt_group:
            try:
                alt_group = parse_blood_group(str(alt_group))
            except InputError:
                alt_group = None
        alt_units = _int(v.get("alt_units")) if alt_group else 0
        units = _int(v.get("units_available"))
        hold = _int(v.get("hold_hours"), default=0) or None
        return CallResult(status="completed", confirmed_units=max(units, 0), alt_units=max(alt_units, 0),
                          alt_group=alt_group, hold_hours=hold, notes=str(v.get("notes") or ""), transcript=transcript)
    willing = str(v.get("willing") or "no").strip().lower()
    willing = willing if willing in ("yes", "no", "later") else "no"
    return CallResult(status="completed", willing=willing, notes=str(v.get("notes") or ""), transcript=transcript)


class SarvamDialer:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=20)

    async def place(self, *, call_id: str, target_type: str, phone: str, agent_variables: dict) -> str:
        s = settings
        app_id = s.sarvam_bank_app_id if target_type == "bank" else s.sarvam_donor_app_id
        app_version = s.sarvam_bank_app_version if target_type == "bank" else s.sarvam_donor_app_version
        if not app_id:
            raise RuntimeError(f"Sarvam app id for {target_type} caller is not configured")
        app_config: dict[str, Any] = {
            "app_id": app_id,
            "connection_config": {"connection_id": s.sarvam_connection_id, "agent_phone_number": s.sarvam_agent_phone},
            "agent_variables": {k: str(v) for k, v in agent_variables.items()},
            "app_overrides": {"initial_language_name": "English"},
        }
        if app_version:
            app_config["app_version"] = int(app_version) if app_version.isdigit() else app_version
        body = {
            "app_config": app_config,
            "user_config": {"user_phone_number": phone},
            "webhook_config": {"url": f"{s.public_base_url}/webhooks/sarvam/{call_id}?sig={webhook_signature(call_id)}"},
        }
        url = f"{s.sarvam_base_url}/api/outbounds/v1/orgs/{s.sarvam_org_id}/workspaces/{s.sarvam_workspace_id}/outbounds"
        r = await self.client.post(url, json=body, headers={"X-API-Key": s.sarvam_api_key})
        if r.status_code >= 300:
            raise RuntimeError(f"Sarvam outbound failed: HTTP {r.status_code} {r.text[:200]}")
        data = r.json()
        attempt = data.get("attempt_id") or (data.get("data") or {}).get("attempt_id")
        if not attempt:
            raise RuntimeError(f"Sarvam outbound: no attempt_id in response {str(data)[:200]}")
        return str(attempt)
