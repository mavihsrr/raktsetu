"""Place ONE real Sarvam outbound call to a phone you own, to check credentials + agent setup.

  python voice/test_outbound.py --to +9198xxxxxxxx --agent bank
The result arrives on PUBLIC_BASE_URL/webhooks/... only for calls placed by the backend; for this
standalone test, check the call in the Sarvam dashboard (attempt id is printed).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.dialer import SarvamDialer  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="E.164 phone you own, e.g. +9198xxxxxxxx")
    ap.add_argument("--agent", choices=["bank", "donor"], default="bank")
    a = ap.parse_args()
    if not settings.sarvam_ready():
        sys.exit("Fill SARVAM_* in .env first.")
    if a.to not in settings.live_targets.values():
        sys.exit("Refusing: --to must be one of the LIVE_TARGETS phones in .env (teammates only).")
    av = {"hospital_name": "City General Hospital", "blood_group": "B positive",
          "component": "packed red cells", "units_needed": 4, "request_ref": "TEST",
          "target_name": "Test Blood Bank" if a.agent == "bank" else "Test D.",
          "compatible_alternatives": "B negative, O positive, O negative"}
    attempt = await SarvamDialer().place(call_id="TEST", target_type=a.agent, phone=a.to, agent_variables=av)
    print("attempt_id:", attempt)


if __name__ == "__main__":
    asyncio.run(main())
