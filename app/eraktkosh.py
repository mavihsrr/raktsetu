"""Live blood bank list + portal stock from e-RaktKosh (Govt. of India blood bank portal), any district in India.

Every request is fetched fresh: no cache. The portal stock is an UNVERIFIED LEAD (banks often
update late); only units a bank confirms on the phone count toward the patient.

Endpoint used by eraktkosh.mohfw.gov.in's own "blood availability" page:
  /BLDAHIMS/bloodbank/nearbyBB.cnt?hmode=GETNEARBYSTOCKDETAILS&stateCode=..&districtCode=..
      &bloodGroup=all&bloodComponent=<code>&lang=0
Row shape: [idx, "<name><br/><address><br/>Phone: ..,Fax: .., Email: ..", category,
            "<p ..>Available, B+Ve:6, O+Ve:2</p>" | "..Not Available..", "YYYY-MM-DD HH:MM:SS", type]
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
from datetime import datetime

import httpx

log = logging.getLogger("raktsetu.eraktkosh")

BASE = "https://eraktkosh.mohfw.gov.in/BLDAHIMS/bloodbank/nearbyBB.cnt"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# Districts fetched together because one city spans both (e.g. Bengaluru: Urban 572 + Rural 583).
TWIN_DISTRICTS = {"572": ["583"], "583": ["572"]}
# Renamed places: what OpenStreetMap says -> what e-RaktKosh calls it.
ALIASES = {"bengaluru": "bangalore", "mysuru": "mysore", "belagavi": "belgaum", "kalaburagi": "gulbarga",
           "vijayapura": "bijapur", "shivamogga": "shimoga", "tumakuru": "tumkur", "gurugram": "gurgaon",
           "prayagraj": "allahabad", "mumbai suburban": "mumbai suburban", "new delhi": "new delhi"}

# Our component -> e-RaktKosh component codes whose stock counts for it.
COMPONENT_CODES = {
    "packed_red_cells": [12, 28],          # Packed Red Blood Cells, SAGM Packed RBC
    "whole_blood": [11],
    "platelets": [23, 20, 14],             # Random Donor Platelets, Platelet Concentrate, Single Donor Platelet
}

_GROUP_RE = re.compile(r"(AB|A|B|O)\s*([+-])\s*ve\s*:\s*(\d+)", re.I)


class PortalError(RuntimeError):
    pass


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip(" ,")


def _parse_row(row: list, district: str) -> dict | None:
    if len(row) < 5:
        return None
    parts = re.split(r"<br\s*/?>", row[1] or "", flags=re.I)
    name = _clean(parts[0])
    address = _clean(" ".join(parts[1:-1])) if len(parts) > 2 else ""
    contact = _clean(parts[-1]) if len(parts) > 1 else ""
    phones_raw = re.search(r"Phone:\s*([^,]*(?:,[^,A-Za-z]*)*)", contact)
    phones = []
    if phones_raw:
        for p in re.split(r"[,/]", phones_raw.group(1)):
            digits = re.sub(r"\D", "", p)
            if len(digits) >= 8:
                phones.append(digits)
    email = re.search(r"Email:\s*(\S+@\S+)", contact)
    stock_html = row[3] or ""
    stock = {}
    if "Not Available" not in stock_html:
        for g, sign, n in _GROUP_RE.findall(_clean(stock_html)):
            stock[f"{g.upper()}{sign}"] = stock.get(f"{g.upper()}{sign}", 0) + int(n)
    updated = None
    try:
        updated = datetime.strptime(str(row[4]).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    if not name:
        return None
    bid = "E" + hashlib.sha1(f"{name}|{address}".lower().encode()).hexdigest()[:8]
    stale = bool(updated and (datetime.now() - updated).days > 7)
    return {"id": bid, "name": name, "address": address, "district": district, "phones": phones, "stale": stale,
            "email": email.group(1).rstrip(",") if email else None, "category": _clean(str(row[2])),
            "stock": stock, "portal_updated_at": updated.isoformat() if updated else None}


HEADERS = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
           "Referer": "https://eraktkosh.mohfw.gov.in/BLDAHIMS/bloodbank/stockAvailability.cnt"}


def _json(r: httpx.Response):
    """The portal mixes in Windows-1252 bytes (smart quotes) now and then."""
    import json
    try:
        return json.loads(r.content.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(r.content.decode("cp1252", errors="replace"))


def _key(s: str) -> str:
    s = re.sub(r"[^a-z ]", " ", (s or "").lower())
    s = re.sub(r"\b(district|dist|city|urban district|division)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for a, b in ALIASES.items():
        s = re.sub(rf"\b{a}\b", b, s)
    return s


def _best(name: str, options: dict[str, str]) -> str | None:
    """options: label -> code. Exact (normalised) match, then containment, then fuzzy >= 0.8."""
    import difflib
    k = _key(name)
    if not k:
        return None
    norm = {_key(lbl): code for lbl, code in options.items()}
    if k in norm:
        return norm[k]
    for lbl, code in norm.items():
        if lbl and (lbl in k or k in lbl):
            return code
    m = difflib.get_close_matches(k, list(norm), n=1, cutoff=0.8)
    return norm[m[0]] if m else None


async def resolve(state: str, district_names: list[str]) -> tuple[str, str, list[str]] | None:
    """(state_code, district label, [district codes]) from OSM state + candidate district names. Live."""
    async with httpx.AsyncClient(timeout=8, headers=HEADERS) as client:
        try:
            r = await client.get(BASE, params={"hmode": "GETSTATELIST", "lang": 0})
            states = {x["label"]: x["value"] for x in _json(r)}
            sc = _best(state, states)
            if not sc:
                return None
            r = await client.get(BASE, params={"hmode": "GETDISTRICTLIST", "selectedStateCode": sc, "lang": 0})
            dists = {x["id"]: x["value"] for x in _json(r).get("records", [])}
        except (httpx.HTTPError, ValueError, KeyError) as e:
            raise PortalError(f"e-RaktKosh unavailable: {e}") from e
    for name in district_names:
        dc = _best(name, dists)
        if dc:
            label = next(l for l, c in dists.items() if c == dc)
            return sc, label, [dc, *TWIN_DISTRICTS.get(dc, [])]
    return None


async def _fetch(client: httpx.AsyncClient, state: str, district: str, comp_code: int) -> list[list]:
    params = {"hmode": "GETNEARBYSTOCKDETAILS", "stateCode": state, "districtCode": district,
              "bloodGroup": "all", "bloodComponent": comp_code, "lang": 0}
    for attempt in (1, 2):   # the portal drops the odd request; one retry
        try:
            r = await client.get(BASE, params=params)
            r.raise_for_status()
            return (_json(r) or {}).get("data") or []
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise
            await asyncio.sleep(0.3)
    return []


async def fetch_banks(component: str, state: str, districts: list[str]) -> list[dict]:
    """Every bank in the given districts with live portal stock for `component` (summed over codes)."""
    codes = COMPONENT_CODES[component]
    jobs = [(d, c) for d in districts for c in codes]
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            results = await asyncio.gather(*(_fetch(client, state, d, c) for d, c in jobs))
    except (httpx.HTTPError, ValueError) as e:
        raise PortalError(f"e-RaktKosh unavailable: {e}") from e
    banks: dict[str, dict] = {}
    for (district, _), rows in zip(jobs, results):
        for row in rows:
            b = _parse_row(row, f"{state}:{district}")
            if not b:
                continue
            cur = banks.get(b["id"])
            if cur is None:
                banks[b["id"]] = b
            else:  # same bank, another component code: add stock
                for g, n in b["stock"].items():
                    cur["stock"][g] = cur["stock"].get(g, 0) + n
    return list(banks.values())
