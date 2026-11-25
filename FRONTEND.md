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

## TODO: voice in the browser (not built yet)

**Today:** voice runs only from a laptop Python script, `voice/intake_voice.py`. It uses the Sarvam SDK
(`sarvam_conv_ai_sdk.AsyncSamvaadAgent`, `InteractionType.CALL`) with the laptop mic/speaker.
The Sarvam agent itself calls our backend's `/tools/*` endpoints, so a voice-made request shows up in
`/api/requests` and `/api/stream` like a typed one.

**Problem:** the SDK's default audio has no echo cancellation. On laptop speakers the agent hears
itself, so the script gates the mic while the agent speaks and you can't interrupt it.
A browser mic with WebRTC echo cancellation fixes that and gives "ChatGPT voice mode" barge-in.

**Rule:** `SARVAM_API_KEY` must never reach the browser. Keep it in the backend.

How to build it, preferred first:
1. **Sarvam web SDK / widget** (check Sarvam's docs for a browser SDK or embeddable agent for
   Samvaad/Voice Agents). If one exists, add a backend endpoint, e.g. `POST /api/voice/session`, that
   creates a short-lived session or token server-side and returns only that. The browser connects with it.
   Pass the same `agent_variables` + `initial_bot_message` the script gets from `GET /api/intake/context?coordinator_name=..`.
   App id and version: `SARVAM_INTAKE_APP_ID` / `SARVAM_INTAKE_APP_VERSION` in backend env.
2. **Otherwise, a WebSocket audio relay through the backend:**
   - Browser: `getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}})`,
     convert to 16 kHz mono PCM16 in an AudioWorklet, and send binary frames to a new `WS /api/voice/ws`.
     Play agent audio from the server's binary frames. Its sample rate can change, so the server should announce it.
   - Backend: per connection, run `AsyncSamvaadAgent` with a **custom audio interface** that reads mic
     frames from the WebSocket and writes agent audio back to it. See how `voice/intake_voice.py`
     subclasses `AsyncDefaultAudioInterface` (`_pyaudio_input_callback`, `output_queue`, `_output_task`,
     `current_output_sample_rate`) and the SDK source in `.venv/lib/python3.12/site-packages/sarvam_conv_ai_sdk/`.
     Forward `transcript_callback` messages (role + text) as JSON text frames for live captions.
   - With browser echo cancellation on, keep the mic open while the agent talks, so barge-in works.
     Drop the half-duplex gating used by the laptop script.
   - **Echo-cancellation catch:** the browser can only remove the agent's voice from the mic if it knows
     what is being played. Chrome reliably cancels audio that arrives over WebRTC (an `RTCPeerConnection`
     remote track). Audio played through the Web Audio API, or an `<audio>` element fed from a WebSocket,
     may not be cancelled on every OS/browser, and then the agent hears itself again on laptop speakers.
     Fixes, best first:
     (a) use Sarvam's web SDK if it plays audio over WebRTC;
     (b) route the agent's audio through a local loopback `RTCPeerConnection` pair, then into an `<audio>` element;
     (c) at minimum, test on laptop speakers without headphones in Chrome and Safari.
     If echo remains, briefly duck/mute the mic while agent audio is playing.
3. Keep the typed flow (`POST /api/requests` → `start` → `/api/stream`) as the fallback when the mic is unavailable.

## Run the backend locally

```bash
.venv/bin/uvicorn app.main:app --port 8000
```

Real calls only. There are no mocks, and real banks are never dialled unless Flagsmith `call_real_banks` is on.
Clicking "start" on a request rings the demo bank and donor phones when Flagsmith `call_mode` is `live`.
