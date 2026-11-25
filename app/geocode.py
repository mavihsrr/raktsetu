"""Geocoding with OpenStreetMap Nominatim (max 1 request/second, per its usage policy).

- The patient's location is geocoded live on every request (one lookup).
- Bank coordinates come from data/bank_locations.json, built once by scripts/geocode_banks.py:
  banks don't move, and ~100 live lookups at 1/s cannot fit in a voice tool call. Bank list,
  phones and stock are still fetched live from e-RaktKosh on every request.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "RaktSetu-hackathon/0.1"
# Bengaluru Urban + Rural bounding box: lon_min, lat_max, lon_max, lat_min.
VIEWBOX = "77.20,13.45,77.95,12.55"
LOCATIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "bank_locations.json"

COARSE = {"city", "town", "state", "state_district", "county", "country", "region", "postcode", "municipality"}

_lock = asyncio.Lock()
_last = 0.0


async def _search(client: httpx.AsyncClient, **params) -> tuple[float, float, str] | None:
    global _last
    async with _lock:  # 1 request/second across the whole process
        wait = 1.05 - (time.monotonic() - _last)
        if wait > 0:
            await asyncio.sleep(wait)
        _last = time.monotonic()
        try:
            r = await client.get(NOMINATIM, params={"format": "json", "limit": 1, "countrycodes": "in",
                                                    "viewbox": VIEWBOX, "bounded": 1, **params})
            r.raise_for_status()
            hits = r.json()
        except (httpx.HTTPError, ValueError):
            return None
    # A hit on a whole city / district / state says nothing about where a bank is.
    hits = [h for h in hits if h.get("addresstype") not in COARSE]
    if not hits:
        return None
    h = hits[0]
    return float(h["lat"]), float(h["lon"]), h.get("display_name", "")


async def geocode_place(text: str) -> tuple[float, float, str] | None:
    """Patient location (hospital name, area, landmark) -> (lat, lng, label)."""
    async with httpx.AsyncClient(timeout=6, headers={"User-Agent": UA}) as client:
        for q in (text, f"{text}, Bengaluru"):
            hit = await _search(client, q=q)
            if hit:
                return hit
    return None


_BANK_WORDS = re.compile(
    r"\b(m/s|blood\s*(centre|center|bank|storage\s*(centre|center|unit)?)|storage\s*(centre|center)|"
    r"transfusion\s*services?|\(?bsu\)?|voluntary|and\s*research\s*centre|component.*|research\s*centre)\b",
    re.I)
_GENERIC = re.compile(r"^(bangalore|bengaluru|banglore|bengalore|karnataka|india|urban|rural|"
                      r"bangalore urban|bangalore rural|bengaluru urban|bengalore urban)$", re.I)
_JUNK = re.compile(r"\d|\b(floor|cross|main|stage|block|phase|no\.?|opp|near|above|below|behind|unit of|"
                   r"complex|building|bus stop|police|station|ltd|pvt|limited|situated)\b", re.I)


def _localities(address: str) -> list[str]:
    """Clean place-name segments of an address, most local last (as written)."""
    out = []
    for seg in re.split(r"[,]", address or ""):
        seg = re.sub(r"\s+", " ", seg).strip(" .-")
        if len(seg) < 5 or _GENERIC.match(seg) or _JUNK.search(seg):
            continue
        out.append(seg)
    return out


def bank_queries(bank: dict) -> list[tuple[dict, bool]]:
    """(query, precise) pairs, most specific first."""
    name = bank["name"]
    base = re.sub(r"\s+", " ", _BANK_WORDS.sub(" ", name)).strip(" ,.-")
    locs = _localities(bank.get("address") or "")
    hosp = [l for l in locs if re.search(r"hospital|college|institute|medical", l, re.I)]
    areas = [l for l in locs if l not in hosp]
    out: list[tuple[dict, bool]] = []
    for nm in dict.fromkeys(x for x in (base, name) if x and len(x) > 3):
        if areas:
            out.append(({"q": f"{nm}, {areas[-1]}"}, True))
        out.append(({"q": nm}, True))
    for h in hosp[:1]:
        out.append(({"q": h}, True))
    for a in reversed(areas[-2:]):
        out.append(({"q": f"{a}, Bengaluru"}, False))
    return out


async def geocode_bank(client: httpx.AsyncClient, bank: dict) -> dict | None:
    for params, precise in bank_queries(bank):
        hit = await _search(client, **params)
        if hit:
            return {"lat": hit[0], "lng": hit[1], "matched": params["q"], "precise": precise}
    return None


def load_locations() -> dict:
    try:
        return json.loads(LOCATIONS_FILE.read_text())
    except (OSError, ValueError):
        return {}
