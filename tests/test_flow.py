import time

from fastapi.testclient import TestClient

from app.config import settings
from app.dialer import webhook_signature
from app.flags import flags
from app.main import create_app

from .conftest import H, new_request, poll_until, tool


def calls_of(c, rid):
    return c.get(f"/api/requests/{rid}").json()["calls"]


def test_tool_secret_required(client):
    assert client.post("/tools/find_leads", json={}).status_code == 401
    assert client.post("/tools/find_leads", headers={"X-Tool-Secret": "nope"}, json={}).status_code == 401


def test_find_leads_calls_nobody_and_includes_zero_stock_banks(client):
    r = new_request(client)
    assert r["ok"] and r["hospital"] == "City General Hospital"
    assert r["blood_group"] == "B+" and r["component"] == "packed_red_cells" and r["component_assumed"]
    assert len(r["banks"]) == 9
    assert any(b["portal_units"] == 0 for b in r["banks"]), "banks listed at 0 must still be called"
    assert {d["id"] for d in r["donors_eligible"]} == {"D01", "D02"}
    reasons = " ".join(d["reason"] for d in r["donors_excluded"])
    assert "no recall consent" in reasons and "days ago" in reasons and "age" in reasons
    assert "Shall I start calling" in r["say"]
    assert calls_of(client, r["request_id"]) == []


def test_bad_input_is_speakable(client):
    r = new_request(client, blood_group="purple")
    assert r["ok"] is False and "blood group" in r["say"]
    r = new_request(client, location="Nowhere Clinic")
    assert r["ok"] is False and "hospital" in r["say"]


def test_start_calls_requires_explicit_confirmation(client):
    rid = new_request(client)["request_id"]
    for bad in (False, None, "no", "maybe"):
        r = tool(client, "start_calls", request_id=rid, confirmed=bad)
        assert r["ok"] is False and r["error"] == "confirmation_required"
    assert calls_of(client, rid) == []


def test_full_flow_with_wave2_approval(client):
    rid = new_request(client)["request_id"]
    assert tool(client, "start_calls", request_id=rid, confirmed=True)["ok"]

    s = poll_until(client, rid, lambda s: s["needs_approval"])
    assert s["status"] == "awaiting_wave2"
    assert s["confirmed_units"] == 2 and "widen" in s["say"].lower()
    # Human-in-the-loop #2: nothing beyond 8 km is dialled before approval
    assert all(c["wave"] == 1 for c in calls_of(client, rid))

    a = tool(client, "approve_wave2", request_id=rid)
    assert a["ok"] and "20 km" in a["say"]
    assert tool(client, "approve_wave2", request_id=rid)["ok"] is False   # not twice

    s = poll_until(client, rid, lambda s: s["done"])
    assert s["status"] == "resolved"
    plan = s["plan"]
    assert plan["confirmed"] == 4 and plan["short_by"] == 0
    assert sum(a["units"] for a in plan["allocation"]) == 4
    assert any("crossmatch" in step.lower() for step in plan["steps"])
    assert any("NOT counted" in step for step in plan["steps"])
    names = {m["bank_name"] for m in plan["portal_mismatches"]}
    assert "Koramangala Blood Centre" in names          # portal 0, phone 1
    assert "Jayanagar Lifeline Blood Bank" in names     # portal 3, phone 0
    assert plan["allocation"] == sorted(plan["allocation"], key=lambda a: a["eta_min"])


def test_donors_never_count_toward_patient_units(client):
    rid = new_request(client)["request_id"]
    tool(client, "start_calls", request_id=rid, confirmed=True)
    poll_until(client, rid, lambda s: s["needs_approval"])
    st = client.get(f"/api/requests/{rid}").json()
    donor_yes = [c for c in st["calls"] if c["target_type"] == "donor" and c["willing"] == "yes"]
    assert donor_yes, "seed has a willing donor"
    bank_units = sum(c["confirmed_units"] + c["alt_units"] for c in st["calls"]
                     if c["target_type"] == "bank" and c["status"] == "completed")
    assert st["plan"]["confirmed"] == bank_units == 2


def test_autopilot_skips_wave2_approval(client):
    flags.overrides["autopilot_mode"] = True
    rid = new_request(client)["request_id"]
    tool(client, "start_calls", request_id=rid, confirmed=True)
    s = poll_until(client, rid, lambda s: s["done"] or s["needs_approval"])
    assert s["status"] == "resolved" and not s["needs_approval"]
    st = client.get(f"/api/requests/{rid}").json()
    assert any(e["type"] == "wave2_started" and e["payload"]["approved_by"] == "autopilot" for e in st["events"])


def test_kill_switch_holds_calls_until_reenabled(client):
    flags.overrides["outbound_calls_enabled"] = False
    rid = new_request(client)["request_id"]
    r = tool(client, "start_calls", request_id=rid, confirmed=True)
    assert "paused" in r["say"]
    s = tool(client, "get_status", request_id=rid)
    assert "paused" in s["say"].lower()
    time.sleep(1.5)
    assert all(c["status"] == "queued" for c in calls_of(client, rid))
    flags.overrides["outbound_calls_enabled"] = True
    s = poll_until(client, rid, lambda s: s["needs_approval"])
    assert s["confirmed_units"] == 2


def test_unresolved_when_nothing_left(client):
    # AB- whole blood: same-group only; nothing in stock anywhere nearby for this seed is likely
    flags.overrides["autopilot_mode"] = True
    rid = new_request(client, blood_group="AB-", units=20, component="whole blood")["request_id"]
    tool(client, "start_calls", request_id=rid, confirmed=True)
    s = poll_until(client, rid, lambda s: s["done"])
    assert s["status"] == "unresolved"
    assert s["plan"]["short_by"] > 0
    assert any("escalate" in step.lower() for step in s["plan"]["steps"])


def test_target_met_skips_remaining_banks(client):
    flags.overrides["max_parallel_calls"] = 1
    rid = new_request(client, units=1)["request_id"]
    tool(client, "start_calls", request_id=rid, confirmed=True)
    s = poll_until(client, rid, lambda s: s["done"])
    assert s["status"] == "resolved"
    statuses = [c["status"] for c in calls_of(client, rid) if c["target_type"] == "bank"]
    assert "skipped" in statuses


def test_webhook_signature_and_live_path(db_path, monkeypatch):
    """call_mode=live + allow-listed target -> SarvamDialer.place, result via webhook."""
    placed = []

    class FakeLive:
        async def place(self, *, call_id, target_type, phone, agent_variables):
            placed.append((call_id, target_type, phone, agent_variables))
            return "attempt-" + call_id

    monkeypatch.setattr(settings, "live_targets", {"bank:B05": "+910000000000"})
    monkeypatch.setattr(settings, "sarvam_api_key", "k")
    monkeypatch.setattr(settings, "sarvam_org_id", "o")
    monkeypatch.setattr(settings, "sarvam_workspace_id", "w")
    monkeypatch.setattr(settings, "sarvam_connection_id", "c")
    monkeypatch.setattr(settings, "sarvam_agent_phone", "+91")
    flags.overrides["call_mode"] = "live"
    app = create_app(db_path=db_path, sim_speed=0)
    with TestClient(app) as c:
        app.state.coord.live = FakeLive()
        rid = new_request(c)["request_id"]
        tool(c, "start_calls", request_id=rid, confirmed=True)
        end = time.time() + 10
        while time.time() < end and not placed:
            time.sleep(0.05)
        assert len(placed) == 1, "only the allow-listed target is dialled for real"
        call_id, ttype, phone, av = placed[0]
        assert ttype == "bank" and phone == "+910000000000"
        assert av["blood_group"] == "B positive" and av["hospital_name"] == "City General Hospital"
        others = [x for x in calls_of(c, rid) if x["id"] != call_id and x["status"] != "queued"]
        assert all(x["mode"] == "sim" for x in others)

        assert c.post(f"/webhooks/sarvam/{call_id}?sig=bad", json={}).status_code == 401
        payload = {"status": "connected", "duration": 42, "interaction_id": "i1",
                   "final_agent_variables": {"units_available": "3", "alt_units": "0", "hold_hours": "4"},
                   "interaction_transcript": [{"role": "agent", "en_text": "hi"}, {"role": "user", "en_text": "3"}]}
        r = c.post(f"/webhooks/sarvam/{call_id}?sig={webhook_signature(call_id)}", json=payload)
        assert r.status_code == 200 and r.json()["ok"]
        end = time.time() + 5
        while time.time() < end:
            row = [x for x in calls_of(c, rid) if x["id"] == call_id][0]
            if row["status"] == "completed":
                break
            time.sleep(0.05)
        assert row["status"] == "completed" and row["mode"] == "live" and row["confirmed_units"] == 3
        assert row["attempt_id"] == "attempt-" + call_id
        assert row["transcript"][1]["text"] == "3"


def test_resume_after_restart(db_path):
    """Kill the process mid-calls; a new process on the same DB resumes and finishes."""
    app = create_app(db_path=db_path, sim_speed=0)
    with TestClient(app) as c:
        flags.overrides["outbound_calls_enabled"] = False   # freeze with everything queued
        rid = new_request(c)["request_id"]
        tool(c, "start_calls", request_id=rid, confirmed=True)
    # simulate a call that was mid-dial when the pod died
    from app.db import DB
    db = DB(db_path)
    first = db.q("SELECT id FROM calls WHERE request_id=? LIMIT 1", (rid,))[0]["id"]
    db.update("calls", first, status="dialing", mode="sim")
    db.conn.close()

    flags.overrides["outbound_calls_enabled"] = True
    app2 = create_app(db_path=db_path, sim_speed=0)
    with TestClient(app2) as c2:
        s = poll_until(c2, rid, lambda s: s["needs_approval"])
        assert s["confirmed_units"] == 2
        ev = c2.get(f"/api/requests/{rid}").json()["events"]
        assert any(e["type"] == "resumed_after_restart" for e in ev)


def test_healthz_and_flags(client):
    assert client.get("/healthz").json()["ok"]
    assert client.head("/healthz").status_code == 200
    f = client.get("/api/flags").json()
    assert f["values"]["call_mode"] == "simulated" and f["values"]["autopilot_mode"] is False


def test_bad_flag_values_fall_back_to_safe_defaults(client):
    flags.overrides["call_mode"] = "yolo"
    flags.overrides["max_parallel_calls"] = 999
    v = client.get("/api/flags").json()["values"]
    assert v["call_mode"] == "simulated" and v["max_parallel_calls"] == 5


def test_max_parallel_calls_is_respected(db_path):
    import asyncio

    from app.dialer import SimulatedDialer

    peak = {"now": 0, "max": 0}

    class CountingSim(SimulatedDialer):
        async def _track(self, coro):
            peak["now"] += 1
            peak["max"] = max(peak["max"], peak["now"])
            try:
                await asyncio.sleep(0.05)
                return await coro
            finally:
                peak["now"] -= 1

        async def call_bank(self, request, bank):
            return await self._track(super().call_bank(request, bank))

        async def call_donor(self, request, donor):
            return await self._track(super().call_donor(request, donor))

    flags.overrides["max_parallel_calls"] = 2
    flags.overrides["autopilot_mode"] = True
    app = create_app(db_path=db_path, sim_speed=0)
    with TestClient(app) as c:
        app.state.coord.sim = CountingSim(speed=0)
        rid = new_request(c)["request_id"]
        tool(c, "start_calls", request_id=rid, confirmed=True)
        poll_until(c, rid, lambda s: s["done"])
    assert peak["max"] == 2
