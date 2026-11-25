"""Create RaktSetu's Flagsmith features via the Admin API (idempotent: existing features are left alone).

Needs FLAGSMITH_ADMIN_KEY (an Organisation API key) in .env, only for this run; remove it afterwards.
Optional FLAGSMITH_PROJECT_ID if the organisation has more than one project.
  .venv/bin/python scripts/flagsmith_setup.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
API = "https://api.flagsmith.com/api/v1"

# name: (enabled by default, value or None, description)
FEATURES = {
    "outbound_calls_enabled": (True, None, "Kill switch: off pauses all calls (re-read before every dial)"),
    "call_real_banks": (False, None, "On = dial the REAL bank numbers from e-RaktKosh. Keep off for the demo."),
    "call_mode": (True, "live", "live = dial the demo lines (DEMO_BANK_PHONES / DEMO_DONOR_PHONES); simulated = dial no one"),
    "call_donors": (True, None, "On = also ring the demo donor line (DEMO_DONOR_PHONES) to restock; off = banks only"),
    "autopilot_mode": (False, None, "On = widen the search to wave 2 without asking"),
    "max_banks_per_wave": (True, "3", "Banks phoned per wave"),
    "max_parallel_calls": (True, "5", "Calls at once"),
    "bank_radius_km": (True, "8", "Wave 1 search radius (km)"),
    "wave2_radius_multiplier": (True, "2.5", "Wave 2 radius = bank_radius_km x this"),
    "donor_radius_km": (True, "10", "Donor search radius (km)"),
}


def main() -> None:
    key = os.environ.get("FLAGSMITH_ADMIN_KEY", "").strip()
    if not key:
        sys.exit("Put FLAGSMITH_ADMIN_KEY=<organisation API key> in .env first.")
    c = httpx.Client(base_url=API, headers={"Authorization": f"Api-Key {key}"}, timeout=15)
    r = c.get("/projects/")
    if r.status_code != 200:
        sys.exit(f"Admin API refused the key ({r.status_code}): {r.text[:200]}")
    projects = r.json()
    want = os.environ.get("FLAGSMITH_PROJECT_ID", "").strip()
    if want:
        projects = [p for p in projects if str(p["id"]) == want]
    if len(projects) != 1:
        sys.exit("Projects: " + ", ".join(f"{p['id']}={p['name']}" for p in r.json())
                 + "\nSet FLAGSMITH_PROJECT_ID in .env to pick one.")
    pid = projects[0]["id"]
    print(f"project {pid}: {projects[0]['name']}")

    existing = set()
    url = f"/projects/{pid}/features/?page_size=100"
    while url:
        page = c.get(url).json()
        existing |= {f["name"] for f in page.get("results", [])}
        url = page.get("next")
        if url:
            url = url.replace(API, "")

    for name, (enabled, value, desc) in FEATURES.items():
        if name in existing:
            print(f"  exists   {name}")
            continue
        body = {"name": name, "default_enabled": enabled, "description": desc, "is_server_key_only": True}
        if value is not None:
            body["initial_value"] = value
        r = c.post(f"/projects/{pid}/features/", json=body)
        print(f"  {'created ' if r.status_code in (200, 201) else 'FAILED  '} {name}"
              + ("" if r.status_code in (200, 201) else f" ({r.status_code}: {r.text[:150]})"))


if __name__ == "__main__":
    main()
