"""Live blood bank list + portal stock from e-RaktKosh (Govt. of India blood bank portal).

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

# Karnataka = 29; Bangalore Urban = 572, Bangalore Rural = 583 (codes from the portal's own links).
STATE_CODE = 29
DISTRICTS = {572: "Bangalore Urban", 583: "Bangalore Rural"}

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
    return {"id": bid, "name": name, "address": address, "district": district, "phones": phones,
            "email": email.group(1).rstrip(",") if email else None, "category": _clean(str(row[2])),
            "stock": stock, "portal_updated_at": updated.isoformat() if updated else None}


async def _fetch(client: httpx.AsyncClient, district: int, comp_code: int) -> list[list]:
    params = {"hmode": "GETNEARBYSTOCKDETAILS", "stateCode": STATE_CODE, "districtCode": district,
              "bloodGroup": "all", "bloodComponent": comp_code, "lang": 0}
    r = await client.get(BASE, params=params)
    r.raise_for_status()
    return (r.json() or {}).get("data") or []


async def fetch_banks(component: str) -> list[dict]:
    """All banks in the configured districts with live portal stock for `component` (summed over codes)."""
    codes = COMPONENT_CODES[component]
    jobs = [(d, c) for d in DISTRICTS for c in codes]
    headers = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
               "Referer": "https://eraktkosh.mohfw.gov.in/BLDAHIMS/bloodbank/stockAvailability.cnt"}
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            results = await asyncio.gather(*(_fetch(client, d, c) for d, c in jobs))
    except (httpx.HTTPError, ValueError) as e:
        raise PortalError(f"e-RaktKosh unavailable: {e}") from e
    banks: dict[str, dict] = {}
    for (district, _), rows in zip(jobs, results):
        for row in rows:
            b = _parse_row(row, DISTRICTS[district])
            if not b:
                continue
            cur = banks.get(b["id"])
            if cur is None:
                banks[b["id"]] = b
            else:  # same bank, another component code: add stock
                for g, n in b["stock"].items():
                    cur["stock"][g] = cur["stock"].get(g, 0) + n
    return list(banks.values())
