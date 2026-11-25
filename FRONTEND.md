# RaktSetu frontend guide

Everything a frontend needs from the backend. Interactive API docs: `GET /docs` on the backend.
The current single-file dashboard, `static/index.html`, is a working reference for every call below.

## What the product does

1. The user asks for blood by voice or typing: blood group, units, deadline, and where the patient is
   (any hospital + town/city in India).
2. **Find leads** (6–8 s): the backend resolves the place to a state/district, then fetches that
   district's **real** blood banks, phone numbers and **live stock** from e-RaktKosh (the national
   portal). It puts banks on the map on the fly and ranks them: near first, fresh stock first.
3. The user says **yes** and calls go out in parallel:
   - `route: "real"`: dials the bank's real number. Only happens when Flagsmith `call_real_banks` is on; it is **off**.
   - `route: "demo"`: a demo phone stands in for that bank (the agent still names the real bank).
   - `route: "lead"`: not phoned; shown with the bank's real number so a human can call it.
   - Donors: there is no real donor registry yet. When `DEMO_DONOR_PHONES` is set (default), one
     "Registered donor" call (`target_id` `DEMO-D1`, `route: "demo"`) goes to the demo donor phone to ask for a
     restock donation. Flagsmith `call_donors` off = no donor call.
4. Results stream in live. If short, the backend asks whether to try the next banks (wave 2).
5. The final **plan** contains confirmed units, banks ranked by ETA, crossmatch steps, backups and unverified leads.

## Rules the UI must respect (correctness, not style)

- Portal stock is a **lead**, never a fact. Only `confirmed_units` from a phone call count.
- Donors **never** count toward the patient's units; they restock the bank. Show them separately.
- Final compatibility = crossmatch at the bank. Never present the plan as "blood reserved".
- When `route == "demo"`, label it (e.g. "DEMO LINE"). Never imply a real bank was phoned.
- `distance_km`, `eta_min`, `lat`, `lng` can be `null` (bank not confidently located). Show "distance unknown"; never guess.
- `portal_stale: true` means the portal stock is more than 7 days old. Say so.

## API

Base URL comes from env (local `http://localhost:8000`; public tunnel or GCP URL in the demo). Don't hardcode it.
Auth: if the backend has `DASHBOARD_TOKEN` set, send header `X-Dashboard-Token: <token>`
(for SSE use `?token=<token>`). Currently unset, so the API is open.
CORS: allowed origins come from backend env `CORS_ORIGINS` (comma-separated; defaults cover
`localhost:5173` and `localhost:3000`). Add the deployed frontend origin there.

| Purpose | Call |
|---|---|
| New request (typed) | `POST /api/requests` `{blood_group: "B+", units: 2, location: "KIMS Hospital Hubli", deadline_hours?: 3, component?: "packed_red_cells"\|"whole_blood"\|"platelets"}` |
| List requests | `GET /api/requests` |
| One request: calls, plan, events | `GET /api/requests/{id}` |
| Start calls (user said yes) | `POST /api/requests/{id}/start` |
| Approve wave 2 (widen) | `POST /api/requests/{id}/approve` |
| Cancel | `POST /api/requests/{id}/cancel` |
| Live updates | `GET /api/stream?request_id={id}` (Server-Sent Events, event name `update`; each `data` is one event row) |
| Operator flags (read-only view) | `GET /api/flags` |
| Health | `GET /healthz` |

`POST /api/requests` returns `ok`, `request_id`, `say` (the sentence the voice agent speaks), and:
- `location`, `located_as`, `approx_location`, `state`, `district`, `lat`, `lng`: the patient's place.
- `banks_in_district`, `banks_in_radius`, `banks_with_stock`, `portal_units_total`.
- `shortlist[]`: the banks it will phone or list. Each has `id`, `name`, `address`, `phone`, `distance_km`, `lat`, `lng`, `portal_units`, `portal_exact`, `portal_updated_at`, `portal_stale`.
- `other_banks[]`: the next 10 banks.
- `donors_eligible[]` (each has `route`; `"demo"` = the demo donor line, `distance_km` null), `donors_excluded[]`.
- On bad input it returns `ok: false` with a `say` explaining what's missing.

`GET /api/requests/{id}` returns `request` (status: `planned → calling → awaiting_wave2 → resolved | unresolved | cancelled`),
`hospital` (the patient's place, with `lat`/`lng`), `calls[]` (`target_type`, `target_name`, `status`, `route`, `mode`,
`distance_km`, `lat`, `lng`, `portal_units`, `confirmed_units`, `alt_units`, `alt_group`, `hold_hours`, `phone`, `notes`, `transcript`),
`plan` (`allocation[]`, `backups[]`, `leads[]`, `steps[]`, `confirmed`, `needed`, `short_by`), `counts`, `needs_approval`, `done`, `events[]`.

Suggested map: pin the patient (`hospital.lat/lng`) and each bank with non-null `lat/lng`, colour by `route`/status.
List banks with null coordinates beside the map.
Two banks in the same hospital campus can share one coordinate, so offset or cluster overlapping pins.
A call's `distance_km` is fixed when the call is queued, while background locating may fill a bank's `lat/lng` later.
Trust `lat/lng` for the map and `distance_km` for the text.

## Voice in the browser (built)

The app in `frontend/` (Vite + React + TS) talks to the Sarvam intake agent through a backend WebSocket relay,
`WS /api/voice/ws` (`app/voice_bridge.py`). `SARVAM_API_KEY` stays on the server.

- Browser: `getUserMedia` with echo cancellation, an AudioWorklet (`frontend/public/pcm-worklet.js`) downsamples
  to 16 kHz PCM16 in 20 ms frames, sent as binary. Agent audio comes back as binary frames prefixed with a
  4-byte little-endian sample rate (Sarvam sends 8 kHz today). The mic stays open, so the user can talk over the agent.
- JSON frames: `state` (connecting / connected / ended / error), `greeting`, `transcript` (role + text),
  `speech` (user start/end, from Sarvam VAD), `interrupt` (stop buffered playback).
- Voice only: this intake app returns 404 for Sarvam's chat interaction, and a CALL closes on text input.
  Without a mic, the UI points to the typed request form (`POST /api/requests`), which is the same flow.
- `GET /api/flags` now also returns `voice_ready` (Sarvam + intake app configured).

## Run the frontend

```bash
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api and the voice socket to :8000
cd frontend && npm run build                   # FastAPI then serves frontend/dist at http://localhost:8000/
```

The old single-file dashboard is still at `/legacy`.

### Open issue: echo cancellation

The browser can only remove the agent's voice from the mic if it knows what is being played. Chrome reliably
cancels audio that arrives over WebRTC (an `RTCPeerConnection` remote track). The current relay plays agent audio
through the Web Audio API, which may not be cancelled on every OS/browser, so on laptop speakers the agent can
hear itself. Fixes, best first: (a) Sarvam's web SDK if it plays audio over WebRTC; (b) route the agent's audio
through a local loopback `RTCPeerConnection` pair into an `<audio>` element; (c) test on laptop speakers without
headphones in Chrome and Safari, and if echo remains, briefly duck the mic while agent audio plays.

## Run the backend locally

```bash
.venv/bin/uvicorn app.main:app --port 8000   # dev: add --reload --reload-dir app --timeout-graceful-shutdown 2
```

Real calls only. There are no mocks, and real banks are never dialled unless Flagsmith `call_real_banks` is on.
Clicking "start" on a request rings the demo bank and donor phones when Flagsmith `call_mode` is `live`.
