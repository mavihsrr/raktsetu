"""Request lifecycle: plan -> (human yes) -> wave 1 calls -> (human yes / autopilot) -> wave 2 -> plan.

State lives in SQLite so a restarted pod resumes where it left off.

Request status: planned -> calling -> awaiting_wave2 -> calling -> resolved | unresolved
Call status:    queued -> dialing -> completed | no_answer | busy | failed | skipped
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import date
from typing import Any

import httpx

from .config import settings
from .db import DB
from .dialer import CallResult, SarvamDialer, SimulatedDialer, parse_sarvam_webhook
from .flags import flags
from .medical import COMPONENTS, InputError, compatible_groups, parse_blood_group, parse_component, spoken_group
from .eraktkosh import PortalError, fetch_banks
from .eraktkosh import resolve
from .geocode import FAST_TERMS, MORE_TERMS, foreground, geocode_place, locate_banks
from .planner import build_plan, eligible_donors, plan_say, rank_banks

log = logging.getLogger("raktsetu.coordinator")

ACTIVE = ("calling",)
FINAL_CALL = ("completed", "no_answer", "busy", "failed", "skipped")
# Events the voice agent should hear about (others are dashboard-only).
SPEAK = {"calls_started", "bank_confirmed", "donor_result", "paused", "resumed", "target_met",
         "approval_needed", "wave2_started", "resolved", "unresolved", "resumed_after_restart"}


def _rid() -> str:
    return "R" + uuid.uuid4().hex[:6].upper()


def _e164(phone: str | None) -> str | None:
    """e-RaktKosh numbers are bare digits: 10-digit mobiles/landlines with STD code, maybe a leading 0 or 91.
    Anything else (e.g. a local number without STD code) is not dialled."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]
    elif len(d) == 12 and d.startswith("91"):
        d = d[2:]
    return "+91" + d if len(d) == 10 else None


class Coordinator:
    def __init__(self, db: DB, sim: SimulatedDialer | None = None, live: SarvamDialer | None = None):
        self.db = db
        self.sim = sim or SimulatedDialer()
        self.live = live
        self.inflight: set[str] = set()                   # call ids currently dialing (all requests)
        self.drivers: dict[str, asyncio.Task] = {}
        self.wake: dict[str, asyncio.Event] = {}           # per-request: something changed
        self.new_event = asyncio.Condition()               # any new event (long-poll + SSE)
        self.live_waiters: dict[str, asyncio.Future] = {}  # call_id -> future(CallResult)
        self.phone_locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self._http = httpx.AsyncClient(timeout=5)

    # ------------------------------------------------------------------ events
    async def emit(self, request_id: str, type_: str, payload: dict | None = None, say: str = "") -> None:
        payload = payload or {}
        self.db.add_event(request_id, type_, payload, say)
        self.db.conn.execute("UPDATE requests SET updated_at=? WHERE id=?", (time.time(), request_id))
        async with self.new_event:
            self.new_event.notify_all()
        if settings.nudgebee_webhook_url:
            self._spawn(self._forward(request_id, type_, payload, say))

    async def _forward(self, request_id: str, type_: str, payload: dict, say: str) -> None:
        try:
            await self._http.post(settings.nudgebee_webhook_url,
                                  json={"source": "raktsetu", "request_id": request_id, "type": type_,
                                        "payload": payload, "message": say})
        except Exception as e:  # best effort only
            log.debug("nudgebee forward failed: %s", e)

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def _poke(self, request_id: str) -> None:
        self.wake.setdefault(request_id, asyncio.Event()).set()

    # ------------------------------------------------------------------ queries
    def request(self, request_id: str) -> dict:
        r = self.db.one("SELECT * FROM requests WHERE id=?", (request_id,))
        if not r:
            raise InputError(f"I can't find request {request_id}.")
        return r

    def calls(self, request_id: str) -> list[dict]:
        return self.db.q("SELECT * FROM calls WHERE request_id=? ORDER BY wave, target_type, distance_km",
                         (request_id,))

    def confirmed_units(self, request_id: str) -> int:
        row = self.db.one("SELECT COALESCE(SUM(confirmed_units + alt_units),0) AS n FROM calls "
                          "WHERE request_id=? AND target_type='bank' AND status='completed'", (request_id,))
        return int(row["n"])

    def _with_coords(self, calls: list[dict]) -> list[dict]:
        """Attach each target's lat/lng (None when unknown): one query per target table, not per call."""
        for ttype, table in (("bank", "banks"), ("donor", "donors")):
            ids = sorted({c["target_id"] for c in calls if c["target_type"] == ttype})
            if not ids:
                continue
            qs = ",".join("?" for _ in ids)
            where = {row["id"]: row for row in self.db.q(f"SELECT id, lat, lng FROM {table} WHERE id IN ({qs})",
                                                        tuple(ids))}
            for c in calls:
                if c["target_type"] == ttype:
                    row = where.get(c["target_id"]) or {}
                    c["lat"], c["lng"] = row.get("lat"), row.get("lng")
        return calls

    def state(self, request_id: str) -> dict:
        r = self.request(request_id)
        calls = self._with_coords(self.calls(request_id))
        hospital = self.db.one("SELECT * FROM hospitals WHERE id=?", (r["hospital_id"],))
        plan = build_plan(r, hospital, calls, time.time())
        counts: dict[str, int] = {}
        for c in calls:
            counts[c["status"]] = counts.get(c["status"], 0) + 1
        return {"request": r, "hospital": hospital, "calls": calls, "plan": plan, "counts": counts,
                "needs_approval": r["status"] == "awaiting_wave2",
                "done": r["status"] in ("resolved", "unresolved", "cancelled")}

    # ------------------------------------------------------------------ tool: find_leads
    async def find_leads(self, *, blood_group: str, units: Any, location: str | None, deadline_hours: Any = None,
                   component: str | None = None, requested_by: str = "") -> dict:
        group = parse_blood_group(blood_group)
        comp, assumed = parse_component(component)
        try:
            n = int(float(units))
        except (TypeError, ValueError):
            raise InputError("How many units are needed?")
        if not 1 <= n <= 20:
            raise InputError("Units must be between 1 and 20 for a single request.")
        hours = None
        if deadline_hours not in (None, ""):
            try:
                hours = float(deadline_hours)
            except (TypeError, ValueError):
                raise InputError("Deadline should be a number of hours, for example 3.")
            if hours <= 0:
                raise InputError("The deadline must be in the future.")
        if not location or not str(location).strip():
            raise InputError("Where is the patient? Tell me the hospital and town or city.")
        location = str(location).strip()
        # Live, every request: place -> state/district -> that district's banks + stock from e-RaktKosh.
        # The voice tool times out at 15 s, so everything here works to an ~11 s deadline.
        t0 = time.monotonic()
        with foreground():
            place = await geocode_place(location)
            if not place:
                raise InputError(f"I couldn't find '{location}' on the map. Which hospital and town or city is it?")
            try:
                where = await resolve(place["state"], place["districts"])
                if not where:
                    raise InputError(f"I found {location} in {place['state'] or 'India'}, but couldn't match its "
                                     "district on the national blood bank portal. Which district is it in?")
                state_code, district_label, dcodes = where
                live = await fetch_banks(comp, state_code, dcodes)
            except PortalError:
                raise InputError("The national blood bank portal, e-RaktKosh, isn't responding right now. "
                                 "Try again in a minute.")
            # Locate the likeliest banks now; keep going in the background while the user hears the
            # answer, so start_calls ranks on more real distances.
            budget = min(4.5, 11.0 - (time.monotonic() - t0))
            if budget > 0.8:
                await locate_banks(live, place, FAST_TERMS, per_bank=False, budget_s=budget)
        unlocated = sum(1 for b in live if "lat" not in b)
        hospital = self._save_place(location, (place["lat"], place["lng"], place["label"]))
        self._save_banks(comp, live)
        self._spawn(self._locate_more(live, place))
        districts = [f"{state_code}:{d}" for d in dcodes]

        snap = flags.snapshot()["values"]
        r1 = float(snap["bank_radius_km"])
        r2 = round(r1 * float(snap["wave2_radius_multiplier"]), 1)
        rd = float(snap["donor_radius_km"])
        top_n = int(snap["max_banks_per_wave"])
        ring = rank_banks(self.db, hospital, group, comp, r1, districts)
        shortlist = ring[:top_n]
        near = [b for b in ring if b["distance_km"] is not None and b["distance_km"] <= r1]
        donors, excluded = eligible_donors(self.db, hospital, group, rd)
        now = time.time()
        rid = _rid()
        self.db.insert("requests", {
            "id": rid, "created_at": now, "updated_at": now, "hospital_id": hospital["id"],
            "blood_group": group, "component": comp, "units": n,
            "deadline_at": now + hours * 3600 if hours else None, "status": "planned", "wave": 0,
            "bank_radius_km": r1, "wave2_radius_km": r2, "donor_radius_km": rd, "requested_by": requested_by,
            "districts": ",".join(districts), "area_label": district_label,
        })
        with_stock = [b for b in ring if b["portal_compatible"] > 0 and not b["portal_stale"]]
        portal_total = sum(b["portal_compatible"] for b in ring)
        label = COMPONENTS[comp]
        say = (f"Request for {n} unit{'s' if n != 1 else ''} of {spoken_group(group)} {label} near {location}"
               + (f", {district_label} district" if district_label.lower() not in location.lower() else "")
               + (f", needed within {hours:g} hours" if hours else "") + ". ")
        if assumed:
            say += "I've assumed packed red cells; tell me if you need whole blood or platelets. "
        if place["approx"]:
            say += f"I couldn't pin the exact place, so I'm measuring from the centre of {place['city'] or district_label}. "
        if ring:
            scope = (f"within {r1:g} km" if len(near) >= len(shortlist) else f"in {district_label} district")
            pool = near if scope.startswith("within") else ring
            say += (f"The national portal, e-RaktKosh, lists {len(pool)} blood bank{'s' if len(pool) != 1 else ''} {scope}; "
                    f"{sum(1 for b in pool if b['portal_compatible'] > 0)} show compatible stock, "
                    f"{sum(b['portal_compatible'] for b in pool)} units in all. ")
            if with_stock:
                b0 = with_stock[0]
                d = b0["distance_km"]
                say += (f"Nearest with recently updated stock is {b0['bank']['name']}"
                        + ("" if d is None else ", right there" if d < 0.5 else f", {d:g} km away")
                        + f", showing {b0['portal_compatible']}. ")
            route = self._routing(snap)
            k = len(shortlist)
            say += f"Portal stock can be out of date, so I'll phone the top {k} to confirm. "
            if route == "demo":
                say += "Real bank calls are switched off, so the confirmation call goes to our demo line. "
            elif route == "none":
                say += "Live calling is off right now, so I'll list them as leads without phoning. "
        else:
            say += f"e-RaktKosh lists no blood banks with this component in {district_label} district right now. "
        if donors:
            say += (f"I also found {len(donors)} eligible donor{'s' if len(donors) != 1 else ''} who opted in to recall; "
                    "I'd ask them to restock, but donor blood is screened first and doesn't count for this patient. ")
        say += "Shall I start calling now?"
        payload = {
            "location": location, "located_as": place["label"], "approx_location": place["approx"],
            "state": place["state"], "district": district_label, "lat": hospital["lat"], "lng": hospital["lng"],
            "blood_group": group, "component": comp, "component_assumed": assumed,
            "units": n, "deadline_hours": hours, "bank_radius_km": r1, "source": "e-RaktKosh (live)",
            "banks_in_district": len(ring), "banks_in_radius": len(near), "banks_with_stock": len(with_stock),
            "banks_not_located": unlocated,
            "shortlist": [self._bank_view(b) for b in shortlist],
            "other_banks": [self._bank_view(b) for b in ring[top_n:top_n + 10]],
            "donors_eligible": [{"id": d["donor"]["id"], "name": d["donor"]["name"], "distance_km": d["distance_km"]}
                                for d in donors],
            "donors_excluded": [{"name": d["donor"]["name"], "reason": d["reason"]} for d in excluded],
            "portal_units_total": portal_total,
        }
        await self.emit(rid, "leads_found", payload, say)
        return {"ok": True, "request_id": rid, **payload, "say": say,
                "next_action": "Read `say` to the user and wait for an explicit yes before calling start_calls."}

    @staticmethod
    def _bank_view(b: dict) -> dict:
        bk = b["bank"]
        return {"id": bk["id"], "name": bk["name"], "address": bk["area"], "phone": bk["phone"],
                "lat": bk.get("lat"), "lng": bk.get("lng"), "distance_km": b["distance_km"], "portal_units": b["portal_compatible"],
                "portal_exact": b["portal_exact"], "portal_updated_at": bk.get("portal_updated_at"),
                "portal_stale": b.get("portal_stale", False)}

    def _save_place(self, text: str, hit: tuple[float, float, str]) -> dict:
        lat, lng, label = hit
        pid = "L" + hashlib.sha1(f"{text.lower()}|{lat:.4f}|{lng:.4f}".encode()).hexdigest()[:8]
        with self.db.lock:
            self.db.conn.execute("INSERT OR REPLACE INTO hospitals (id, name, aliases, lat, lng) VALUES (?,?,?,?,?)",
                                 (pid, text, label, lat, lng))
        return self.db.one("SELECT * FROM hospitals WHERE id=?", (pid,))

    def _save_banks(self, comp: str, live: list[dict]) -> int:
        """Upsert this live fetch into `banks` (stock for `comp`; lat/lng set by locate_banks)."""
        seen, districts = set(), {b["district"] for b in live}
        with self.db.lock:
            for b in live:
                old = self.db.one("SELECT portal FROM banks WHERE id=?", (b["id"],))
                portal = (old or {}).get("portal") or {}
                portal[comp] = b["stock"]
                self.db.conn.execute(
                    "INSERT OR REPLACE INTO banks (id, name, area, lat, lng, phone, portal, portal_updated_days_ago,"
                    " sim, portal_updated_at, email, district) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (b["id"], b["name"], b["address"], b.get("lat"), b.get("lng"),
                     ",".join(b["phones"]) or None, json.dumps(portal), None, None,
                     b["portal_updated_at"], b["email"], b["district"]))
                seen.add(b["id"])
            # banks of these districts missing from this fetch list no stock for this component right now
            qs = ",".join("?" for _ in districts) or "''"
            for row in self.db.q(f"SELECT id, portal FROM banks WHERE district IN ({qs})", tuple(districts)):
                if row["id"] not in seen and (row["portal"] or {}).get(comp):
                    p = row["portal"]
                    p[comp] = {}
                    self.db.update("banks", row["id"], portal=p)

    async def _locate_more(self, live: list[dict], place: dict) -> None:
        def save(b: dict) -> None:
            self.db.conn.execute("UPDATE banks SET lat=?, lng=? WHERE id=?", (b["lat"], b["lng"], b["id"]))
        try:
            await locate_banks(live, place, MORE_TERMS, per_bank=True, budget_s=60.0, on_hit=save)
        except Exception:
            log.exception("background bank locating failed")

    def _routing(self, snap: dict) -> str:
        """real: dial the bank's own number; demo: our demo line stands in; none: list as leads only."""
        live = snap["call_mode"] == "live" and settings.sarvam_ready() and self.live is not None
        if live and snap["call_real_banks"]:
            return "real"
        if live and settings.demo_bank_phones:
            return "demo"
        return "none"

    # ------------------------------------------------------------------ tool: start_calls
    async def start_calls(self, request_id: str, confirmed: Any) -> dict:
        r = self.request(request_id)
        if confirmed is not True and str(confirmed).strip().lower() not in ("true", "yes", "1"):
            return {"ok": False, "request_id": request_id, "error": "confirmation_required",
                    "say": "I need your explicit yes before I phone anyone. Shall I start calling?"}
        if r["status"] != "planned":
            return {"ok": True, "request_id": request_id, "already": r["status"],
                    "say": "Calls are already under way for this request.", "next_action": "call get_status"}
        hospital = self.db.one("SELECT * FROM hospitals WHERE id=?", (r["hospital_id"],))
        banks = self._shortlist(r, hospital, r["bank_radius_km"])
        donors, _ = eligible_donors(self.db, hospital, r["blood_group"], r["donor_radius_km"])
        dialled, demo = self._queue_banks(r, banks, wave=1)
        for d in donors:
            self._queue(r["id"], "donor", d["donor"], 1, d["distance_km"], None)
        self.db.update("requests", request_id, status="calling", wave=1, updated_at=time.time())
        paused = not await flags.aget("outbound_calls_enabled")
        say = self._calling_say(banks, dialled, demo, len(donors))
        if paused:
            say += " Note: outbound calls are currently paused by the operator; they'll start when re-enabled."
        await self.emit(request_id, "calls_started", {"banks": len(banks), "donors": len(donors), "wave": 1}, say)
        self._start_driver(request_id)
        return {"ok": True, "request_id": request_id, "say": say,
                "next_action": "Call get_status repeatedly and read each `say` to the user."}

    def _shortlist(self, r: dict, hospital: dict, max_km: float) -> list[dict]:
        called = {c["target_id"] for c in self.calls(r["id"]) if c["target_type"] == "bank"}
        n = int(flags.get("max_banks_per_wave"))
        districts = (r.get("districts") or "").split(",")
        return rank_banks(self.db, hospital, r["blood_group"], r["component"], max_km, districts, called)[:n]

    def _queue_banks(self, r: dict, banks: list[dict], wave: int) -> tuple[int, int]:
        """Route each shortlisted bank. Returns (calls queued, of which to the demo line)."""
        route = self._routing(flags.snapshot()["values"])
        demo_phones = list(settings.demo_bank_phones)
        dialled = demo = 0
        for b in banks:
            bank, real_phone = b["bank"], _e164((b["bank"]["phone"] or "").split(",")[0])
            if route == "real" and real_phone:
                self._queue(r["id"], "bank", bank, wave, b["distance_km"], b["portal_compatible"],
                            route="real", dial_to=real_phone, phone=bank["phone"])
                dialled += 1
            elif route == "demo" and demo < len(demo_phones):
                self._queue(r["id"], "bank", bank, wave, b["distance_km"], b["portal_compatible"],
                            route="demo", dial_to=demo_phones[demo], phone=bank["phone"])
                dialled += 1
                demo += 1
            else:
                why = ("no phone number on the portal" if route == "real" else
                       "real bank calls are off; demo line already in use" if route == "demo" else
                       "live calling is off")
                self._queue(r["id"], "bank", bank, wave, b["distance_km"], b["portal_compatible"],
                            route="lead", phone=bank["phone"], status="skipped", mode="lead",
                            notes=f"Not phoned ({why}). Portal shows {b['portal_compatible']}.")
        return dialled, demo

    @staticmethod
    def _calling_say(banks: list[dict], dialled: int, demo: int, donors: int) -> str:
        def where(b: dict) -> str:
            d = b["distance_km"]
            return b["bank"]["name"] + ("" if d is None else f", {d:g} km")
        leads = banks[dialled:]
        if dialled == 0 and not donors:
            return ("I haven't phoned anyone: live calling is off. These banks are leads with their numbers in the plan: "
                    + "; ".join(where(b) for b in banks) + ".")
        bits = []
        if dialled:
            bits.append("; ".join(where(b) for b in banks[:dialled]) + (" through the demo line" if demo else ""))
        if donors:
            bits.append(f"{donors} donor{'s' if donors != 1 else ''}")
        say = "Calling " + ", and ".join(bits) + " now. I'll update you as they answer."
        if leads:
            say += (f" Also worth phoning yourself, not called by me: " + "; ".join(where(b) for b in leads) + ".")
        return say

    def _queue(self, request_id: str, ttype: str, target: dict, wave: int, km: float, portal: int | None,
               *, route: str | None = None, dial_to: str | None = None, phone: str | None = None,
               status: str = "queued", mode: str | None = None, notes: str | None = None) -> None:
        now = time.time()
        self.db.insert("calls", {
            "id": "C" + uuid.uuid4().hex[:8], "request_id": request_id, "target_type": ttype,
            "target_id": target["id"], "target_name": target["name"], "wave": wave, "status": status,
            "mode": mode, "distance_km": km, "portal_units": portal, "confirmed_units": 0, "alt_units": 0,
            "queued_at": now, "route": route, "dial_to": dial_to, "phone": phone, "notes": notes,
            "ended_at": now if status == "skipped" else None,
        })

    # ------------------------------------------------------------------ tool: approve_wave2
    async def approve_wave2(self, request_id: str, approved_by: str = "voice") -> dict:
        r = self.request(request_id)
        if r["status"] != "awaiting_wave2":
            return {"ok": False, "request_id": request_id, "error": f"not_awaiting_approval ({r['status']})",
                    "say": "There's nothing waiting for approval on this request right now."}
        return await self._start_wave2(r, approved_by)

    async def _start_wave2(self, r: dict, approved_by: str) -> dict:
        hospital = self.db.one("SELECT * FROM hospitals WHERE id=?", (r["hospital_id"],))
        banks = self._shortlist(r, hospital, r["wave2_radius_km"])
        dialled, demo = self._queue_banks(r, banks, wave=2)
        self.db.update("requests", r["id"], status="calling", wave=2, updated_at=time.time())
        say = ("Widening the search" + (" on autopilot" if approved_by == "autopilot" else "")
               + ". " + self._calling_say(banks, dialled, demo, 0))
        await self.emit(r["id"], "wave2_started", {"banks": len(banks), "approved_by": approved_by}, say)
        self._start_driver(r["id"])
        return {"ok": True, "request_id": r["id"], "say": say, "next_action": "Call get_status repeatedly."}

    async def cancel(self, request_id: str) -> dict:
        r = self.request(request_id)
        if r["status"] in ("resolved", "unresolved", "cancelled"):
            return {"ok": False, "say": "That request is already closed."}
        self.db.conn.execute("UPDATE calls SET status='skipped', notes='request cancelled', ended_at=? "
                             "WHERE request_id=? AND status='queued'", (time.time(), request_id))
        self.db.update("requests", request_id, status="cancelled", updated_at=time.time())
        await self.emit(request_id, "cancelled", {}, "Request cancelled. No further calls will be made.")
        self._poke(request_id)
        return {"ok": True, "say": "Request cancelled. No further calls will be made."}

    # ------------------------------------------------------------------ tool: get_status (long-poll)
    async def get_status(self, request_id: str, wait_s: float | None = None) -> dict:
        r = self.request(request_id)
        wait_s = settings.get_status_wait_s if wait_s is None else min(wait_s, settings.get_status_wait_s)
        deadline = time.monotonic() + wait_s
        cursor = r["agent_cursor"] or 0
        while True:
            events = self.db.events_after(request_id, cursor)
            speak = [e for e in events if e["type"] in SPEAK]
            if speak or time.monotonic() >= deadline:
                break
            remaining = deadline - time.monotonic()
            try:
                async with self.new_event:
                    await asyncio.wait_for(self.new_event.wait(), timeout=min(remaining, 2.0))
            except asyncio.TimeoutError:
                pass
        if events:
            self.db.conn.execute("UPDATE requests SET agent_cursor=? WHERE id=?", (events[-1]["seq"], request_id))
        st = self.state(request_id)
        say = self._narrate(events, st)
        if st["needs_approval"]:
            nxt = "Ask the user whether to widen the search. If they say yes, call approve_wave2."
        elif st["done"]:
            nxt = "Read the plan to the user. The request is finished; stop polling."
        else:
            nxt = "Call get_status again."
        p = st["plan"]
        return {"ok": True, "request_id": request_id, "status": st["request"]["status"],
                "wave": st["request"]["wave"], "confirmed_units": p["confirmed"], "needed_units": p["needed"],
                "confirmed_total": self.confirmed_units(request_id),
                "calls_in_progress": st["counts"].get("dialing", 0), "calls_queued": st["counts"].get("queued", 0),
                "needs_approval": st["needs_approval"], "done": st["done"], "say": say, "next_action": nxt,
                "plan": p if st["done"] else None}

    def _narrate(self, events: list[dict], st: dict) -> str:
        parts: list[str] = []
        misses = {"none": 0, "no_answer": 0}
        closing = None      # approval question or final plan: always spoken last
        had_total = False
        for e in events:
            t = e["type"]
            if t in ("resolved", "unresolved", "approval_needed"):
                closing = e["say"]
            elif t == "bank_result":
                if e["payload"].get("status") == "completed":
                    misses["none"] += 1
                else:
                    misses["no_answer"] += 1
            elif t == "wave2_started" and e["payload"].get("approved_by") != "autopilot":
                continue    # already said in the approve_wave2 response
            elif t in SPEAK and t != "calls_started" and e["say"]:
                parts.append(e["say"])
                had_total = had_total or t in ("bank_confirmed", "target_met")
        if misses["none"]:
            parts.append(f"{misses['none']} bank{'s' if misses['none'] != 1 else ''} had none.")
        if misses["no_answer"]:
            parts.append(f"{misses['no_answer']} didn't answer or the line failed.")
        if closing:
            parts.append(closing)
        elif st["request"]["status"] == "calling":
            p, c = st["plan"], st["counts"]
            active = c.get("dialing", 0) + c.get("queued", 0)
            if active:
                tail = f"{active} call{'s' if active != 1 else ''} still going."
                parts.append(tail if had_total else f"{p['confirmed']} of {p['needed']} confirmed so far; {tail}")
        elif st["needs_approval"]:
            r = st["request"]
            parts.append(f"Waiting for your go-ahead to widen the search to {r['wave2_radius_km']:g} km.")
        if not parts:
            parts.append("Still waiting.")
        return " ".join(parts)

    # ------------------------------------------------------------------ driver
    def _start_driver(self, request_id: str) -> None:
        t = self.drivers.get(request_id)
        if t and not t.done():
            self._poke(request_id)
            return
        self.drivers[request_id] = self._spawn(self._drive(request_id))

    async def _drive(self, request_id: str) -> None:
        ev = self.wake.setdefault(request_id, asyncio.Event())
        paused = False
        target_announced = False
        try:
            while True:
                ev.clear()
                r = self.request(request_id)
                if r["status"] != "calling":
                    return
                calls = self.calls(request_id)
                queued = [c for c in calls if c["status"] == "queued"]
                mine_inflight = [c for c in calls if c["status"] == "dialing"]

                confirmed = self.confirmed_units(request_id)
                if confirmed >= r["units"]:
                    # Target met: stop dialling further banks; donors continue (restock).
                    for c in queued:
                        if c["target_type"] == "bank":
                            self.db.update("calls", c["id"], status="skipped", notes="target already met",
                                           ended_at=time.time())
                    queued = [c for c in queued if c["target_type"] != "bank"]
                    if not target_announced and (queued or mine_inflight):
                        target_announced = True
                        await self.emit(request_id, "target_met", {"confirmed": confirmed},
                                        f"Target reached: {confirmed} of {r['units']} confirmed. "
                                        "Finishing the calls already in progress.")

                if not queued and not mine_inflight:
                    await self._wave_done(request_id)
                    target_announced = False
                    continue    # autopilot may have started wave 2; loop top exits otherwise

                if queued:
                    enabled = await flags.aget("outbound_calls_enabled")
                    if not enabled:
                        if not paused:
                            paused = True
                            await self.emit(request_id, "paused", {"queued": len(queued)},
                                            f"Outbound calls were paused by the operator. {len(queued)} calls are on hold.")
                    else:
                        if paused:
                            paused = False
                            await self.emit(request_id, "resumed", {}, "Outbound calls are re-enabled; continuing.")
                        max_par = int(await flags.aget("max_parallel_calls"))
                        free = max_par - len(self.inflight)
                        for c in queued[:max(free, 0)]:
                            # re-read the kill switch before EVERY dial
                            if not await flags.aget("outbound_calls_enabled"):
                                break
                            await self._dial(r, c)
                try:
                    await asyncio.wait_for(ev.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
        except Exception:
            log.exception("driver for %s crashed", request_id)
            raise

    async def _dial(self, r: dict, c: dict) -> None:
        live_ok = (await flags.aget("call_mode")) == "live" and settings.sarvam_ready() and self.live is not None
        if c["target_type"] == "bank":
            # Re-check routing at dial time: an operator may have switched things off since queueing.
            ok = live_ok and (c["route"] == "demo" or (c["route"] == "real" and await flags.aget("call_real_banks")))
            if not ok:
                self.db.update("calls", c["id"], status="skipped", mode="lead", route="lead", ended_at=time.time(),
                               notes=f"Not phoned (calling switched off before dial). Portal shows {c['portal_units']}.")
                self._poke(r["id"])
                return
            mode, phone = "live", c["dial_to"]
        else:
            phone = settings.live_targets.get(f"donor:{c['target_id']}")
            mode = "live" if live_ok and phone else "sim"
        self.inflight.add(c["id"])
        self.db.update("calls", c["id"], status="dialing", mode=mode, started_at=time.time())
        await self.emit(r["id"], "call_started", {"call_id": c["id"], "target": c["target_name"],
                                                   "target_type": c["target_type"], "mode": mode,
                                                   "route": c["route"]})
        self._spawn(self._run_call(r, c, mode, phone))

    def _phone_lock(self, phone: str) -> asyncio.Lock:
        # One phone can take one call: calls to the same number (e.g. the demo line) go one after another.
        return self.phone_locks.setdefault(re.sub(r"\D", "", phone)[-10:], asyncio.Lock())

    async def _run_call(self, r: dict, c: dict, mode: str, phone: str | None) -> None:
        try:
            if mode == "sim":
                donor = self.db.one("SELECT * FROM donors WHERE id=?", (c["target_id"],))
                res = await self.sim.call_donor(r, donor)
            else:
                async with self._phone_lock(phone):
                    fut = asyncio.get_running_loop().create_future()
                    self.live_waiters[c["id"]] = fut
                    attempt = await self.live.place(call_id=c["id"], target_type=c["target_type"], phone=phone,
                                                    agent_variables=self._agent_vars(r, c))
                    self.db.update("calls", c["id"], attempt_id=attempt)
                    res = await asyncio.wait_for(fut, timeout=settings.live_call_timeout_s)
        except asyncio.TimeoutError:
            res = CallResult(status="failed", notes="no result from telephony within timeout")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("call %s failed", c["id"])
            res = CallResult(status="failed", notes=str(e)[:200])
        finally:
            self.live_waiters.pop(c["id"], None)
        await self.on_call_result(c["id"], res)

    def _agent_vars(self, r: dict, c: dict) -> dict:
        hospital = self.db.one("SELECT * FROM hospitals WHERE id=?", (r["hospital_id"],))
        alts = compatible_groups(r["blood_group"], r["component"])[1:]
        v = {"hospital_name": hospital["name"], "blood_group": spoken_group(r["blood_group"]),
             "component": COMPONENTS[r["component"]], "units_needed": r["units"], "request_ref": r["id"],
             "target_name": c["target_name"],
             "compatible_alternatives": ", ".join(spoken_group(g) for g in alts) or "none"}
        if r["deadline_at"]:
            v["deadline_minutes"] = max(int((r["deadline_at"] - time.time()) / 60), 0)
        # Sarvam rejects (422) any variable the agent does not declare, so send each caller only its own.
        allowed = {"bank": ("blood_group", "component", "units_needed", "request_ref",
                            "target_name", "compatible_alternatives"),
                   "donor": ("blood_group", "request_ref", "target_name")}[c["target_type"]]
        return {k: v[k] for k in allowed if k in v}

    # ------------------------------------------------------------------ results
    async def on_webhook(self, call_id: str, payload: dict) -> dict:
        c = self.db.one("SELECT * FROM calls WHERE id=?", (call_id,))
        if not c:
            return {"ok": False, "error": "unknown call"}
        res = parse_sarvam_webhook(payload, c["target_type"])
        fut = self.live_waiters.get(call_id)
        if fut and not fut.done():
            fut.set_result(res)          # _run_call finishes it
        elif c["status"] == "dialing":
            await self.on_call_result(call_id, res)   # e.g. after a restart
        return {"ok": True}

    async def on_call_result(self, call_id: str, res: CallResult) -> None:
        c = self.db.one("SELECT * FROM calls WHERE id=?", (call_id,))
        self.inflight.discard(call_id)
        if not c or c["status"] in FINAL_CALL:
            return
        r = self.request(c["request_id"])
        self.db.update("calls", call_id, status=res.status, confirmed_units=res.confirmed_units,
                       alt_units=res.alt_units, alt_group=res.alt_group, hold_hours=res.hold_hours,
                       willing=res.willing, notes=res.notes, transcript=res.transcript, ended_at=time.time())
        tag = " (simulated)" if c["mode"] == "sim" else " (via demo line)" if c["route"] == "demo" else ""
        if c["target_type"] == "bank":
            total = self.confirmed_units(r["id"])
            got = res.confirmed_units + res.alt_units
            payload = {"call_id": call_id, "target": c["target_name"], "status": res.status,
                       "confirmed": res.confirmed_units, "alt_units": res.alt_units, "alt_group": res.alt_group,
                       "portal": c["portal_units"], "total_confirmed": total, "needed": r["units"], "mode": c["mode"]}
            if res.status == "completed" and got > 0:
                bits = []
                if res.confirmed_units:
                    bits.append(f"{res.confirmed_units} unit{'s' if res.confirmed_units != 1 else ''} of "
                                f"{spoken_group(r['blood_group'])}")
                if res.alt_units:
                    bits.append(f"{res.alt_units} of {spoken_group(res.alt_group)} as a compatible alternative")
                say = f"{c['target_name']}{tag} confirms " + " and ".join(bits)
                if c["portal_units"] is not None and c["portal_units"] != res.confirmed_units:
                    say += f", though the portal said {c['portal_units']}"
                say += (f". {total} of {r['units']} confirmed." if total < r["units"]
                        else f". That makes {total} confirmed against {r['units']} needed.")
                await self.emit(r["id"], "bank_confirmed", payload, say)
            else:
                if res.status == "completed" and c["portal_units"]:
                    payload["stale_portal"] = True
                await self.emit(r["id"], "bank_result", payload,
                                f"{c['target_name']}{tag}: " + ("none available" + (
                                    f" (portal said {c['portal_units']})" if c["portal_units"] else "")
                                    if res.status == "completed" else res.status.replace("_", " ")))
        else:
            payload = {"call_id": call_id, "target": c["target_name"], "status": res.status,
                       "willing": res.willing, "mode": c["mode"]}
            if res.status == "completed" and res.willing == "yes":
                say = (f"Donor {c['target_name']}{tag} agreed to donate to restock ({res.notes.lower() or 'soon'}). "
                       "That's for the bank's stock, not counted for this patient.")
            elif res.status == "completed":
                say = f"Donor {c['target_name']} can't donate right now."
            else:
                say = f"Donor {c['target_name']} didn't answer."
            await self.emit(r["id"], "donor_result", payload, say)
        self._poke(r["id"])

    async def _wave_done(self, request_id: str) -> None:
        r = self.request(request_id)
        confirmed = self.confirmed_units(request_id)
        if confirmed >= r["units"]:
            await self._finish(r, "resolved")
            return
        if r["wave"] == 1:
            hospital = self.db.one("SELECT * FROM hospitals WHERE id=?", (r["hospital_id"],))
            more = self._shortlist(r, hospital, r["wave2_radius_km"])
            if more:
                if await flags.aget("autopilot_mode"):
                    await self.emit(request_id, "wave1_done", {"confirmed": confirmed},
                                    f"{confirmed} of {r['units']} confirmed.")
                    await self._start_wave2(r, "autopilot")
                    return
                self.db.update("requests", request_id, status="awaiting_wave2", updated_at=time.time())
                await self.emit(request_id, "approval_needed",
                                {"confirmed": confirmed, "needed": r["units"], "more_banks": len(more),
                                 "radius_km": r["wave2_radius_km"]},
                                f"{confirmed} of {r['units']} confirmed so far. "
                                f"Shall I phone the next {len(more)} nearest bank{'s' if len(more) != 1 else ''}?")
                return
        await self._finish(r, "unresolved")

    async def _finish(self, r: dict, status: str) -> None:
        self.db.update("requests", r["id"], status=status, updated_at=time.time())
        st = self.state(r["id"])
        self.db.update("requests", r["id"], plan=st["plan"])
        say = ("Done. " if status == "resolved" else "Search finished, but we're short. ") + plan_say(st["plan"])
        await self.emit(r["id"], status, {"plan": st["plan"]}, say)

    # ------------------------------------------------------------------ restart recovery
    async def recover(self) -> int:
        """Called on startup: resume any request that was mid-calls when the process died."""
        resumed = 0
        for r in self.db.q("SELECT * FROM requests WHERE status='calling'"):
            reset = 0
            for c in self.db.q("SELECT * FROM calls WHERE request_id=? AND status='dialing'", (r["id"],)):
                if c["mode"] == "live" and c["attempt_id"]:
                    # Phone call is real and may still be going: wait for its webhook, don't re-dial a human.
                    self.inflight.add(c["id"])
                    self._spawn(self._await_orphan(c["id"]))
                elif c["mode"] == "live":
                    self.db.update("calls", c["id"], status="failed", notes="interrupted by restart (not re-dialled)",
                                   ended_at=time.time())
                else:
                    self.db.update("calls", c["id"], status="queued", mode=None, started_at=None)
                    reset += 1
            left = self.db.one("SELECT COUNT(*) AS n FROM calls WHERE request_id=? AND status IN ('queued','dialing')",
                               (r["id"],))["n"]
            await self.emit(r["id"], "resumed_after_restart", {"requeued": reset, "remaining": left},
                            f"I was restarted and have resumed request {r['id']}: "
                            f"{self.confirmed_units(r['id'])} of {r['units']} confirmed, {left} calls left.")
            self._start_driver(r["id"])
            resumed += 1
        return resumed

    async def _await_orphan(self, call_id: str) -> None:
        fut = asyncio.get_running_loop().create_future()
        self.live_waiters[call_id] = fut
        try:
            res = await asyncio.wait_for(fut, timeout=settings.live_call_timeout_s)
        except asyncio.TimeoutError:
            res = CallResult(status="failed", notes="no webhook after restart")
        finally:
            self.live_waiters.pop(call_id, None)
        await self.on_call_result(call_id, res)

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._http.aclose()
