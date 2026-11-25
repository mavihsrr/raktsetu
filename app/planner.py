"""Deterministic planning: who to call, and how to turn phone-confirmed units into a plan.

Correctness rules enforced here:
- Banks + portal stock come live from e-RaktKosh. Portal stock is an unverified LEAD: the shortlist\n  prefers banks listing compatible stock, then nearest, and a phone call confirms.
- Only phone-confirmed units count toward the patient's requirement.
- Donors never count toward the patient's units (they restock/replace, shown separately).
- The plan always says: send patient sample + requisition for crossmatch.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .db import DB
from .geo import eta_minutes, haversine_km
from .medical import COMPONENTS, InputError, compatible_groups, donor_eligibility, spoken_group


STALE_DAYS = 7


def rank_banks(db: DB, place: dict, group: str, component: str, near_km: float, districts: list[str],
               exclude_ids: set[str] | frozenset = frozenset()) -> list[dict]:
    """Real banks in the request's districts. Order: within near_km first, then banks listing compatible
    stock, then nearest. Banks we could not locate are kept (distance None) after located ones."""
    groups = compatible_groups(group, component)
    qs = ",".join("?" for _ in districts) or "''"
    out = []
    for b in db.q(f"SELECT * FROM banks WHERE district IN ({qs})", tuple(districts)):
        if b["id"] in exclude_ids:
            continue
        km = haversine_km(place["lat"], place["lng"], b["lat"], b["lng"]) if b["lat"] is not None else None
        portal_comp = (b["portal"] or {}).get(component, {})
        out.append({
            "bank": b, "distance_km": round(km, 1) if km is not None else None, "eta_min": eta_minutes(km),
            "portal_exact": int(portal_comp.get(group, 0)),
            "portal_compatible": int(sum(portal_comp.get(g, 0) for g in groups)),
        })
    # Stock last updated more than a week ago is too stale to rank on.
    cutoff = (datetime.now() - timedelta(days=STALE_DAYS)).isoformat()
    for x in out:
        upd = x["bank"].get("portal_updated_at")
        x["portal_stale"] = bool(upd and upd < cutoff)
    out.sort(key=lambda x: (x["distance_km"] is None or x["distance_km"] > near_km,
                            x["portal_compatible"] == 0 or x["portal_stale"],
                            x["distance_km"] is None, x["distance_km"] or 0))
    return out


def eligible_donors(db: DB, hospital: dict, group: str, radius_km: float,
                    today: date | None = None) -> tuple[list[dict], list[dict]]:
    """Donors of the patient's exact group within radius. Returns (eligible, excluded-with-reason)."""
    today = today or date.today()
    eligible, excluded = [], []
    for d in db.q("SELECT * FROM donors WHERE blood_group=?", (group,)):
        km = haversine_km(hospital["lat"], hospital["lng"], d["lat"], d["lng"])
        if km > radius_km:
            continue
        rec = {
            "recall_consent": bool(d["recall_consent"]),
            "dob": date.fromisoformat(d["dob"]),
            "gender": d["gender"],
            "last_donation": date.fromisoformat(d["last_donation"]) if d["last_donation"] else None,
        }
        ok, reason = donor_eligibility(rec, today)
        item = {"donor": d, "distance_km": round(km, 1), "reason": reason}
        (eligible if ok else excluded).append(item)
    eligible.sort(key=lambda x: x["distance_km"])
    return eligible, excluded


def build_plan(request: dict, hospital: dict, calls: list[dict], now: float) -> dict:
    """Allocate phone-confirmed units, nearest first, exact group before compatible alternatives."""
    need = request["units"]
    group, component = request["blood_group"], request["component"]
    confirmed_banks = [c for c in calls if c["target_type"] == "bank" and c["status"] == "completed"
                       and ((c["confirmed_units"] or 0) + (c["alt_units"] or 0)) > 0]
    pool = []
    for c in confirmed_banks:
        if c["confirmed_units"]:
            pool.append((0, c["distance_km"], c, group, c["confirmed_units"]))
        if c["alt_units"]:
            pool.append((1, c["distance_km"], c, c["alt_group"] or "?", c["alt_units"]))
    pool.sort(key=lambda x: (x[0], x[1]))

    allocation, backups, remaining = [], [], need
    for _, km, c, g, n in pool:
        take = min(n, max(remaining, 0))
        if take < n:
            backups.append({"bank_name": c["target_name"], "units": n - take, "group": g,
                            "exact_match": g == group, "distance_km": km, "eta_min": eta_minutes(km),
                            "lat": c.get("lat"), "lng": c.get("lng")})
        if take <= 0:
            continue
        remaining -= take
        allocation.append({
            "bank_id": c["target_id"], "bank_name": c["target_name"], "units": take, "group": g,
            "exact_match": g == group, "distance_km": km, "eta_min": eta_minutes(km),
            "hold_hours": c["hold_hours"], "mode": c["mode"], "route": c.get("route"),
            "lat": c.get("lat"), "lng": c.get("lng"),
        })
    allocation.sort(key=lambda a: (a["eta_min"] is None, a["eta_min"] or 0))
    got = need - max(remaining, 0)

    deadline_min = (request["deadline_at"] - now) / 60 if request["deadline_at"] else None
    late = [a for a in allocation if deadline_min is not None and a["eta_min"] is not None
            and a["eta_min"] > deadline_min]

    donors = [{"donor_id": c["target_id"], "name": c["target_name"], "willing": c["willing"],
               "notes": c["notes"], "distance_km": c["distance_km"], "mode": c["mode"]}
              for c in calls if c["target_type"] == "donor" and c["status"] == "completed"]

    mismatches = [{"bank_name": c["target_name"], "portal": c["portal_units"], "phone": c["confirmed_units"]}
                  for c in calls if c["target_type"] == "bank" and c["status"] == "completed"
                  and c["portal_units"] != c["confirmed_units"]]

    leads = [{"bank_name": c["target_name"], "portal": c["portal_units"], "distance_km": c["distance_km"],
              "phone": c.get("phone"), "why": c["notes"], "lat": c.get("lat"), "lng": c.get("lng")}
             for c in calls if c["target_type"] == "bank" and c.get("route") == "lead"]

    steps = []
    if allocation:
        first = allocation[0]
        steps.append(f"Send the patient's blood sample and signed requisition to {first['bank_name']} "
                     f"for crossmatch now" + (f" (approx {first['eta_min']} min away)." if first["eta_min"] else "."))
        if len(allocation) > 1:
            others = ", ".join(a["bank_name"] for a in allocation[1:])
            steps.append(f"Also send sample + requisition to {others}; each bank crossmatches before issue.")
        if any(not a["exact_match"] for a in allocation):
            steps.append(f"Some units are a compatible group, not {group}; the blood bank officer confirms by crossmatch.")
        steps.append("Ask each bank to hold the units until crossmatch completes; hold times are listed.")
    steps.append("Final compatibility is decided only by the crossmatch at the issuing bank.")
    if backups:
        steps.append("Backup units (confirmed, not yet allocated): " + ", ".join(
            f"{b['bank_name']} {b['units']} {b['group']}" for b in backups) + ". Release them if not needed.")
    if got < need:
        steps.append(f"Still short by {need - got} unit(s): escalate to the regional blood transfusion officer and keep calling.")
    if leads and got < need:
        steps.append("Unverified portal leads (not phoned by RaktSetu): " + "; ".join(
            f"{l['bank_name']} ({str(l['distance_km']) + ' km, ' if l['distance_km'] is not None else ''}portal {l['portal']}, phone {l['phone'] or 'n/a'})" for l in leads) + ".")
    if donors:
        steps.append("Willing donors replace/restock bank stock; their blood is screened first and is NOT counted for this patient.")

    return {
        "needed": need, "confirmed": got, "short_by": max(need - got, 0),
        "group": group, "component": component, "component_label": COMPONENTS[component],
        "allocation": allocation, "backups": backups, "late_vs_deadline": [a["bank_name"] for a in late],
        "deadline_minutes_left": int(deadline_min) if deadline_min is not None else None,
        "donors_restock": donors, "portal_mismatches": mismatches, "leads": leads, "steps": steps,
        "group_spoken": spoken_group(group),
    }


def plan_say(plan: dict) -> str:
    if not plan["allocation"]:
        msg = (f"No bank has confirmed {plan['group_spoken']} {plan['component_label']} yet. "
               "Escalate to the regional blood transfusion officer.")
        if plan["leads"]:
            msg += " Other banks' numbers are on screen to phone directly."
        return msg
    first = plan["allocation"][0]
    head = (f"{plan['confirmed']} of {plan['needed']} units confirmed." if plan["short_by"] == 0
            else f"Only {plan['confirmed']} of {plan['needed']} units confirmed.")
    parts = [head, f"Nearest is {first['bank_name']}" + (f", about {first['eta_min']} minutes" if first["eta_min"] else "")
             + ". Send the patient's sample and requisition there for crossmatch."]
    if len(plan["allocation"]) > 1:
        parts.append("Other units: " + "; ".join(
            f"{a['bank_name']} {a['units']}" + ("" if a["exact_match"] else f" ({spoken_group(a['group'])}, compatible)")
            for a in plan["allocation"][1:]) + ".")
    if plan["short_by"] and plan["leads"]:
        parts.append("Other banks' numbers are on screen to phone directly.")
    if plan["late_vs_deadline"]:
        parts.append("Warning: " + ", ".join(plan["late_vs_deadline"]) + " may not arrive before the deadline.")
    return " ".join(parts)
