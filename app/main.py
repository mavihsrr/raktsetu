"""HTTP surface.

/tools/*        Sarvam intake-agent HTTP tools (header X-Tool-Secret)
/webhooks/*     Sarvam outbound call results (HMAC sig in URL)
/api/*          Dashboard (optional DASHBOARD_TOKEN via X-Dashboard-Token)
/healthz        Liveness/readiness for Kubernetes + NudgeBee
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .coordinator import Coordinator
from .db import DB
from .dialer import SarvamDialer, webhook_signature
from .flags import DEFAULTS, flags
from .medical import InputError
from .voice_bridge import run_session as run_voice_session
from .voice_bridge import voice_ready

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("raktsetu")
STATIC = Path(__file__).resolve().parent.parent / "static"
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(db_path: str | None = None, sim_speed: float | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = DB(db_path or settings.db_path)
        db.seed_if_empty()
        from .dialer import SimulatedDialer

        coord = Coordinator(db, sim=SimulatedDialer(speed=sim_speed),
                            live=SarvamDialer() if settings.sarvam_ready() else None)
        app.state.db, app.state.coord = db, coord
        app.state.started_at = time.time()
        n = await coord.recover()
        if n:
            log.info("resumed %d in-flight request(s) after restart", n)
        yield
        await coord.shutdown()

    app = FastAPI(title="RaktSetu", version="0.1.0", lifespan=lifespan)

    # CORS for a separately hosted frontend. Auth is header/query-token based (no cookies),
    # so credentials are only enabled for an explicit allow-list, never with "*".
    allow_any = "*" in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_any else settings.cors_origins,
        allow_credentials=not allow_any,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Dashboard-Token"],
    )

    # ---------------------------------------------------------------- auth helpers
    def tool_auth(x_tool_secret: str = Header(default="")) -> None:
        if not hmac.compare_digest(x_tool_secret, settings.tool_secret):
            raise HTTPException(401, "bad tool secret")

    def dash_auth(x_dashboard_token: str = Header(default=""), token: str = "") -> None:
        if settings.dashboard_token and not hmac.compare_digest(x_dashboard_token or token, settings.dashboard_token):
            raise HTTPException(401, "dashboard token required")

    def coord(req: Request) -> Coordinator:
        return req.app.state.coord

    async def safe(fn, *a, **kw) -> JSONResponse:
        """Tool errors become a speakable `say`, never a stack trace."""
        try:
            res = fn(*a, **kw)
            if asyncio.iscoroutine(res):
                res = await res
            return JSONResponse(res)
        except InputError as e:
            return JSONResponse({"ok": False, "error": "input", "say": str(e)})
        except Exception:
            log.exception("tool error")
            return JSONResponse({"ok": False, "error": "internal",
                                 "say": "Something went wrong on my side. Please try again."})

    def _get(body: dict, *names: str, default: Any = None) -> Any:
        for n in names:
            if n in body and body[n] not in (None, ""):
                return body[n]
        return default

    # ---------------------------------------------------------------- health
    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def healthz(req: Request):
        req.app.state.db.one("SELECT 1 AS ok")
        return {"ok": True, "uptime_s": round(time.time() - req.app.state.started_at, 1)}

    # ---------------------------------------------------------------- intake tools
    @app.post("/tools/find_leads", dependencies=[Depends(tool_auth)])
    async def t_find_leads(req: Request, body: dict = Body(default={})):
        return await safe(coord(req).find_leads,
                          blood_group=_get(body, "blood_group", "group", default=""),
                          units=_get(body, "units", "units_needed"),
                          location=_get(body, "location", "hospital", "hospital_name"),
                          deadline_hours=_get(body, "deadline_hours", "hours"),
                          component=_get(body, "component"),
                          requested_by=str(_get(body, "requested_by", default="voice")))

    @app.post("/tools/start_calls", dependencies=[Depends(tool_auth)])
    async def t_start_calls(req: Request, body: dict = Body(default={})):
        return await safe(coord(req).start_calls, str(_get(body, "request_id", default="")),
                          _get(body, "confirmed", default=False))

    @app.post("/tools/get_status", dependencies=[Depends(tool_auth)])
    async def t_get_status(req: Request, body: dict = Body(default={})):
        return await safe(coord(req).get_status, str(_get(body, "request_id", default="")))

    @app.post("/tools/approve_wave2", dependencies=[Depends(tool_auth)])
    async def t_approve(req: Request, body: dict = Body(default={})):
        return await safe(coord(req).approve_wave2, str(_get(body, "request_id", default="")), "voice")

    @app.post("/tools/cancel_request", dependencies=[Depends(tool_auth)])
    async def t_cancel(req: Request, body: dict = Body(default={})):
        return await safe(coord(req).cancel, str(_get(body, "request_id", default="")))

    # ---------------------------------------------------------------- Sarvam webhook
    @app.post("/webhooks/sarvam/{call_id}")
    async def sarvam_webhook(call_id: str, req: Request, sig: str = ""):
        if not hmac.compare_digest(sig, webhook_signature(call_id)):
            raise HTTPException(401, "bad signature")
        try:
            payload = await req.json()
        except Exception:
            raise HTTPException(400, "json body required")
        log.info("webhook %s status=%s", call_id, payload.get("status"))
        return await coord(req).on_webhook(call_id, payload)

    # ---------------------------------------------------------------- dashboard API
    @app.get("/")
    async def index():
        if (DIST / "index.html").exists():
            return FileResponse(DIST / "index.html")
        return FileResponse(STATIC / "index.html")

    @app.get("/legacy")
    async def legacy_index():
        return FileResponse(STATIC / "index.html")

    @app.get("/pcm-worklet.js")
    async def pcm_worklet():
        if not (DIST / "pcm-worklet.js").exists():
            raise HTTPException(404, "frontend not built")
        return FileResponse(DIST / "pcm-worklet.js", media_type="text/javascript")

    @app.get("/favicon.svg")
    async def favicon():
        if not (DIST / "favicon.svg").exists():
            raise HTTPException(404, "frontend not built")
        return FileResponse(DIST / "favicon.svg", media_type="image/svg+xml")

    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/api/requests", dependencies=[Depends(dash_auth)])
    async def list_requests(req: Request):
        rows = req.app.state.db.q("SELECT r.*, h.name AS hospital_name FROM requests r "
                                  "JOIN hospitals h ON h.id=r.hospital_id ORDER BY created_at DESC LIMIT 50")
        for r in rows:
            r["confirmed_units"] = coord(req).confirmed_units(r["id"])
            r.pop("plan", None)
        return rows

    @app.get("/api/requests/{rid}", dependencies=[Depends(dash_auth)])
    async def get_request(rid: str, req: Request):
        try:
            st = coord(req).state(rid)
        except InputError as e:
            raise HTTPException(404, str(e))
        st["events"] = req.app.state.db.q("SELECT * FROM events WHERE request_id=? ORDER BY seq", (rid,))
        return st

    @app.post("/api/requests", dependencies=[Depends(dash_auth)])
    async def new_request(req: Request, body: dict = Body(default={})):
        return await safe(coord(req).find_leads, blood_group=body.get("blood_group", ""), units=body.get("units"),
                          location=body.get("location"), deadline_hours=body.get("deadline_hours"),
                          component=body.get("component"), requested_by="dashboard")

    @app.post("/api/requests/{rid}/start", dependencies=[Depends(dash_auth)])
    async def d_start(rid: str, req: Request):
        return await safe(coord(req).start_calls, rid, True)

    @app.post("/api/requests/{rid}/approve", dependencies=[Depends(dash_auth)])
    async def d_approve(rid: str, req: Request):
        return await safe(coord(req).approve_wave2, rid, "dashboard")

    @app.post("/api/requests/{rid}/cancel", dependencies=[Depends(dash_auth)])
    async def d_cancel(rid: str, req: Request):
        return await safe(coord(req).cancel, rid)

    @app.get("/api/flags", dependencies=[Depends(dash_auth)])
    async def get_flags():
        snap = await asyncio.to_thread(flags.snapshot)
        snap["sarvam_configured"] = settings.sarvam_ready()
        snap["voice_ready"] = voice_ready()
        snap["live_targets"] = sorted(settings.live_targets)   # keys only, never numbers
        snap["demo_lines"] = {"banks": len(settings.demo_bank_phones), "donors": len(settings.demo_donor_phones)}  # counts only
        return snap

    @app.post("/api/flags/override", dependencies=[Depends(dash_auth)])
    async def set_override(body: dict = Body(default={})):
        """Local testing without Flagsmith. {"name": ..., "value": ...}; value null clears."""
        name = body.get("name")
        if name not in DEFAULTS:
            raise HTTPException(400, "unknown flag")
        if body.get("value") is None:
            flags.overrides.pop(name, None)
        else:
            flags.overrides[name] = body["value"]
        return flags.snapshot()

    @app.get("/api/intake/context", dependencies=[Depends(dash_auth)])
    async def intake_context(req: Request, coordinator_name: str = "", hospital: str = ""):
        """agent_variables + greeting for the voice intake agent."""
        return build_intake_context(coordinator_name, hospital)

    @app.websocket("/api/voice/ws")
    async def ws_voice(ws: WebSocket, token: str = ""):
        if settings.dashboard_token and not hmac.compare_digest(token, settings.dashboard_token):
            await ws.close(code=4401)
            return
        await run_voice_session(ws, build_intake_context)

    def build_intake_context(coordinator_name: str = "", hospital: str = "") -> dict:
        # Anyone can use the assistant (family, friends, hospital staff), so never read out other
        # people's requests or ids. Keep the greeting short and human.
        name = coordinator_name.strip()
        greet = (f"Hi {name}, I'm RaktSetu." if name and name.lower() != "there" else "Hi, I'm RaktSetu.")
        greet += (" I'll help you find blood quickly. Which blood group do you need, how many units, "
                  "and where is the patient?")
        ctx = {"coordinator_name": name or "there", "default_hospital": hospital or "",
               "active_requests": "[]", "today": time.strftime("%d %b %Y")}
        return {"agent_variables": ctx, "initial_bot_message": greet}

    @app.get("/api/stream")
    async def stream(req: Request, since: int = -1, request_id: str = "", token: str = ""):
        if settings.dashboard_token and not hmac.compare_digest(token, settings.dashboard_token):
            raise HTTPException(401, "dashboard token required")
        db, c = req.app.state.db, coord(req)
        if since < 0:
            row = db.one("SELECT COALESCE(MAX(seq),0) AS s FROM events")
            since = row["s"]

        async def gen():
            cursor = since
            yield "retry: 2000\n\n"
            while True:
                if await req.is_disconnected():
                    return
                evs = db.events_after(request_id or None, cursor)
                for e in evs:
                    cursor = e["seq"]
                    yield f"id: {e['seq']}\nevent: update\ndata: {json.dumps(e)}\n\n"
                if not evs:
                    try:
                        async with c.new_event:
                            await asyncio.wait_for(c.new_event.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


app = create_app()


def run() -> None:  # pragma: no cover
    import os

    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
