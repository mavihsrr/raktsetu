"""Live geocoding, all India, nothing stored between requests (OpenStreetMap Nominatim, 1 request/s).

- Patient location -> lat/lng + state + district candidates.
- Banks (e-RaktKosh gives names/addresses but no coordinates):
  1. a few category searches ("hospital", "blood bank", ...) around the patient return up to 50
     named places each; bank names are fuzzy-matched to them locally (words + acronyms like ANMMCH);
  2. banks still unmatched get a short name search of their own, likeliest first.
  Precision over recall: an unsure match is left unlocated rather than given a wrong distance.
"""
from __future__ import annotations

import asyncio
import re
import time

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "RaktSetu-hackathon/0.1"
MAX_KM_FROM_PLACE = 80.0   # a "match" further than this from the patient is the wrong place
COARSE = {"city", "town", "state", "state_district", "county", "country", "region", "postcode", "municipality"}
FAST_TERMS = ("hospital", "blood bank")                 # inside the voice tool's time limit
MORE_TERMS = ("blood centre", "medical college", "blood")  # in the background

_lock = asyncio.Lock()
_last = 0.0
_foreground = 0   # live requests in progress; background locating yields to them


class foreground:
    """Context manager: marks a user-facing lookup so background lookups pause meanwhile."""
    def __enter__(self):
        global _foreground
        _foreground += 1

    def __exit__(self, *exc):
        global _foreground
        _foreground -= 1


def viewbox_around(lat: float, lng: float, deg: float = 0.7) -> str:
    return f"{lng - deg},{lat + deg},{lng + deg},{lat - deg}"


async def _get(client: httpx.AsyncClient, params: dict, background: bool = False) -> list[dict]:
    global _last
    while background and _foreground:
        await asyncio.sleep(0.2)
    async with _lock:  # 1 request/second across the whole process (Nominatim usage policy)
        wait = 1.05 - (time.monotonic() - _last)
        if wait > 0:
            await asyncio.sleep(wait)
        _last = time.monotonic()
        try:
            r = await client.get(NOMINATIM, params={"format": "json", "countrycodes": "in", **params})
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return []


# ------------------------------------------------------------------ patient location
async def geocode_place(text: str) -> dict | None:
    """Place anywhere in India -> {lat, lng, label, approx, state, districts, city, area_words}."""
    words = re.sub(r"[^\w\s,]", " ", text).replace(",", " ").split()
    tries = [t for t in dict.fromkeys([text, " ".join(words[-2:]), words[-1] if words else ""]) if t]
    hit, approx = None, False
    async with httpx.AsyncClient(timeout=6, headers={"User-Agent": UA}) as client:
        for i, q in enumerate(tries):
            hits = await _get(client, {"q": q, "limit": 1, "addressdetails": 1})
            if hits:
                hit, approx = hits[0], i > 0   # i > 0: only the town matched, not the exact place
                break
    if not hit:
        return None
    addr = hit.get("address") or {}
    districts = [addr.get(k) for k in ("state_district", "county", "city_district", "city", "town", "suburb")]
    city = addr.get("city") or addr.get("town") or addr.get("state_district") or ""
    area = {w for k in ("suburb", "neighbourhood", "quarter", "city_district", "village")
            for w in re.findall(r"[a-z]{4,}", (addr.get(k) or "").lower())}
    return {"lat": float(hit["lat"]), "lng": float(hit["lon"]), "label": hit.get("display_name", ""),
            "approx": approx, "state": addr.get("state", ""), "districts": [d for d in districts if d],
            "city": city, "area_words": sorted(area)}


# ------------------------------------------------------------------ bank name matching
_STOP = set("""blood centre center bank banks and of the a an at in for hospital hospitals research institute
medical college sciences science voluntary unit storage ltd pvt private limited dr sri shri smt st m s ms
trust society memorial general district govt government transfusion services service bsu enterprises
care health healthcare centres foundation charitable multispeciality multi speciality super specialty
speciality clinic nursing home city ji""".split())
_JOIN = {"and", "of", "the", "&", "a", "an", "for", "at", "in"}


def _place_words(near: dict) -> set[str]:
    """City/district names: present in every address, so they can't identify a bank."""
    names = [near.get("city") or "", *(near.get("districts") or [])]
    base = {w for n in names for w in re.findall(r"[a-z]{3,}", n.lower())}
    if base & {"bangalore", "bengaluru"}:
        base |= {"bangalore", "bengaluru", "banglore", "bengalore"}
    return base | {"urban", "rural"}


def _words(s: str, drop: set[str]) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower()) if w not in _STOP and w not in drop}


def _initials(name: str) -> str:
    return "".join(w[0] for w in re.findall(r"[a-z]+", name.lower()) if w not in _JOIN)


def _acronyms(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\b[A-Z]{3,8}\b", s or "")} - {"BSU", "MRC", "PVT", "LTD"}


def _bank_text(b: dict) -> str:
    hosp = " ".join(re.findall(r"[^,]*(?:hospital|college|institute)[^,]*", b.get("address") or "", re.I))
    return f"{b['name']} {hosp}"


def _plain(s: str, drop: set[str]) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower())
            if w not in drop and w not in {"blood", "centre", "center", "bank", "and", "the"}}


def _match(b: dict, pois: list[tuple[str, float, float]], drop: set[str]) -> tuple[float, float] | None:
    name_w = _words(b["name"], drop)
    if not name_w:   # all-generic name ("Karnataka Medical College And Research Institute"): use plain words
        return _match_plain(b, pois, drop)
    bw = name_w | _words(_bank_text(b), drop)
    acr = _acronyms(f"{b['name']} {b.get('address') or ''}")
    best, best_score = None, (0, 0, 0.0)
    for pname, lat, lng in pois:
        pw = _words(pname, drop)
        ini = _initials(pname)
        by_acr = any(a == ini or (len(a) >= 4 and ini.startswith(a)) for a in acr) if len(ini) >= 3 else False
        inter = bw & pw
        cov_p = len(inter) / len(pw) if pw else 0.0
        cov_b = len(name_w & pw) / len(name_w) if name_w else 0.0
        if not (by_acr or (inter and cov_p >= 0.6 and cov_b >= 0.6)):
            continue
        score = (int(by_acr), len(inter), cov_p)
        if score > best_score:
            best, best_score = (lat, lng), score
    return best


def _match_plain(b: dict, pois: list, drop: set[str]) -> tuple[float, float] | None:
    bw = _plain(b["name"], drop)
    best, best_score = None, 0.0
    for pname, lat, lng in pois:
        pw = _plain(pname, drop)
        inter = bw & pw
        if len(inter) < 2:
            continue
        score = min(len(inter) / len(bw), len(inter) / len(pw))
        if score >= 0.5 and score > best_score:
            best, best_score = (lat, lng), score
    return best


def _close(lat: float, lng: float, near: dict) -> bool:
    from .geo import haversine_km
    return haversine_km(lat, lng, near["lat"], near["lng"]) <= MAX_KM_FROM_PLACE


async def _pois(client: httpx.AsyncClient, near: dict, terms: tuple[str, ...], deg: float,
                background: bool = False) -> list:
    vb = viewbox_around(near["lat"], near["lng"], deg)
    out: dict = {}
    for t in terms:
        for h in await _get(client, {"q": t, "limit": 50, "viewbox": vb, "bounded": 1}, background):
            name = h.get("name") or h.get("display_name", "").split(",")[0]
            out[h.get("place_id")] = (name, float(h["lat"]), float(h["lon"]))
    return list(out.values())


def _priority(b: dict) -> tuple:
    fresh = sum(b["stock"].values()) if not b.get("stale") else 0
    return (-(fresh > 0), -fresh)


async def locate_banks(banks: list[dict], near: dict, terms: tuple[str, ...] = FAST_TERMS,
                       per_bank: bool = False, budget_s: float = 4.0, on_hit=None) -> int:
    """Sets b['lat'], b['lng'] on banks it can place confidently. Returns how many stay unlocated."""
    drop = _place_words(near)

    def place(b: dict, ll: tuple[float, float] | None) -> None:
        if ll and _close(ll[0], ll[1], near):
            b["lat"], b["lng"] = ll
            if on_hit:
                on_hit(b)

    async def run(client: httpx.AsyncClient) -> None:
        pois = await _pois(client, near, terms, 0.3, background=per_bank)
        for b in banks:
            if "lat" not in b:
                place(b, _match(b, pois, drop))
        if not per_bank:
            return
        city = near.get("city") or ""
        for b in sorted((b for b in banks if "lat" not in b), key=_priority):
            key = " ".join(sorted(_words(b["name"], drop), key=b["name"].lower().find)) or b["name"]
            hits = await _get(client, {"q": f"{key}, {city}", "limit": 5,
                                       "viewbox": viewbox_around(near["lat"], near["lng"]), "bounded": 1},
                              background=True)
            cands = [(h.get("name") or h.get("display_name", "").split(",")[0], float(h["lat"]), float(h["lon"]))
                     for h in hits if h.get("addresstype") not in COARSE]
            place(b, _match(b, cands, drop))

    async with httpx.AsyncClient(timeout=5, headers={"User-Agent": UA}) as client:
        try:
            await asyncio.wait_for(run(client), timeout=budget_s)
        except asyncio.TimeoutError:
            pass
    return sum(1 for b in banks if "lat" not in b)
