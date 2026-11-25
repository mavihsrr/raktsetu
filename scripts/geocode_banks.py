"""One-time: geocode every e-RaktKosh blood bank in Bengaluru into data/bank_locations.json.

Run again any time to pick up new banks (already-located banks are kept).
  .venv/bin/python scripts/geocode_banks.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.eraktkosh import COMPONENT_CODES, fetch_banks  # noqa: E402
from app.geocode import LOCATIONS_FILE, UA, geocode_bank, load_locations  # noqa: E402


async def main() -> None:
    banks: dict[str, dict] = {}
    for comp in COMPONENT_CODES:  # union over components so banks without PRC stock are included too
        for b in await fetch_banks(comp):
            banks.setdefault(b["id"], b)
    locs = load_locations()
    todo = [b for b in banks.values() if b["id"] not in locs]
    print(f"{len(banks)} banks, {len(locs)} already located, {len(todo)} to geocode")
    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": UA}) as client:
        for i, b in enumerate(todo, 1):
            hit = await geocode_bank(client, b)
            if hit:
                locs[b["id"]] = {"name": b["name"], **hit}
            print(f"[{i}/{len(todo)}] {'ok ' if hit else 'MISS'} {b['name'][:60]}"
                  + (f"  <- {hit['matched'][:40]}" if hit else ""), flush=True)
            if i % 10 == 0:
                LOCATIONS_FILE.write_text(json.dumps(locs, indent=1))
    LOCATIONS_FILE.write_text(json.dumps(locs, indent=1))
    print(f"done: {len(locs)}/{len(banks)} located -> {LOCATIONS_FILE}")


asyncio.run(main())
