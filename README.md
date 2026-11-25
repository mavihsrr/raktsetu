# RaktSetu

**One spoken request finds blood: a parallel, phone-verified search across blood banks, plus donor recall for restock.**

Every year around Diwali and the year-end holidays, blood banks run short. Camps stop because colleges
and offices close, and donors travel. Maharashtra's State Blood Transfusion Council calls this an
annual shortage. Hospitals still find blood by phoning banks one by one. The national e-RaktKosh portal
is meant to show daily stock, but many banks don't update it (93 Maharashtra government banks were fined
for missing daily updates), so portal numbers are leads, not facts.

RaktSetu is a voice assistant for a **hospital blood-centre coordinator**:

> "Need 4 units of B-positive, I'm at City General, surgery in 3 hours."
> → "I found 9 banks within 8 km and 2 eligible donors. Shall I call them now?" → **"Yes"**
> → phones every bank in parallel, narrates: "Koramangala confirms 1 unit, though the portal said 0…"
> → "2 of 4 confirmed. Widen to 20 km?" → **"Yes"** → "Done. 4 confirmed. Nearest is Basavanagudi,
> ~17 min. Send the patient's sample and requisition there for crossmatch."

> ⚠️ **All banks, donors, hospitals and phone numbers in this repo are fictional.** It never dials a
> real blood bank. Live calls go only to allow-listed teammate phones; everything else is simulated
> and labelled **SIM**.

## Correctness rules (built into the code and covered by tests)

1. **Portal stock is an unverified lead.** Every bank in the radius is called, including banks listed at 0.
   Only units a bank **confirms on the phone** count. Portal-vs-phone mismatches are shown.
2. **Donors never count toward the patient's units.** Donated blood must be screened first. Donors are
   restock or replacement and are shown separately.
3. The plan always says: **send the patient's sample and requisition to the bank for crossmatch**. Final
   compatibility = crossmatch.
4. Whole blood and platelets: same group only. Packed red cells: red-cell compatibility table, with the
   exact group preferred.
5. Donor recall needs: opted in to recall (consent, DPDP), age 18–65, ≥90 days since the last donation
   (men) or ≥120 days (women).
6. Two human-in-the-loop gates: `start_calls` is refused unless `confirmed=true`, and wave 2 waits for
   approval (unless the Flagsmith `autopilot_mode` flag is on).

## Architecture

```
 Coordinator (laptop mic) ──► Sarvam intake voice agent (STT+LLM+TTS, tool calling)
                                   │  HTTP tools (X-Tool-Secret)
                                   ▼
                       FastAPI backend (deterministic Python, no agent framework)
        find_leads → start_calls → get_status (long-poll ≤25 s) → approve_wave2
        planner · parallel dispatcher (asyncio, max_parallel from Flagsmith) · waves
        SQLite (requests, calls, events) → resume after restart · SSE → dashboard
                │                                   ▲
                ▼ Sarvam Instant Outbound           │ webhook (HMAC-signed URL)
      bank_verifier / donor_recall agents ──► teammate phones (LIVE) | simulator (SIM)
      Flagsmith: kill switch, call_mode, parallelism, autopilot, radii
      NudgeBee: watches the K8s deployment (pod-kill → RCA → restart → calls resume)
```

| Sponsor | Used for |
|---|---|
| **Sarvam AI** | Intake voice agent (laptop), outbound `bank_verifier` and `donor_recall` agents, telephony |
| **Flagsmith** | `outbound_calls_enabled` (kill switch, re-read before every dial), `call_mode` simulated/live, `max_parallel_calls`, `autopilot_mode`, `bank_radius_km`, `donor_radius_km`, `wave2_radius_multiplier`. Safe defaults (SIM, autopilot off) if Flagsmith is unreachable |
| **NudgeBee** | SRE copilot on the Kubernetes deployment: pod-kill demo → RCA → restart; the app resumes in-flight calls from SQLite |

## Run locally (simulated, no keys needed)

```bash
cd raktsetu
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000. Create a request (City General, B+, 4 units), click **Yes, start calling**,
then **Approve wave 2**. Use the **kill** / **toggle** chips to test the kill switch and autopilot locally.

Rehearse the voice conversation with no Sarvam credits (it plays the agent's part):

```bash
python voice/rehearse.py            # you answer yes/no
python voice/rehearse.py --auto
```

Tests:

```bash
pytest -q
```

## Going live

1. Fill in `.env`: Sarvam keys and IDs, `FLAGSMITH_ENVIRONMENT_KEY`, and the demo phones:
   `DEMO_BANK_PHONES` (stands in for the bank) and `DEMO_DONOR_PHONES` (stands in for a registered donor).
2. Public URL for Sarvam's tool calls: a tunnel (`ngrok` / `cloudflared`) or the GKE deploy; set `PUBLIC_BASE_URL`.
3. Create the 3 Sarvam agents from `agents/*.md`. Add the HTTP tools in `agents/tools.json` to the intake agent.
4. In Flagsmith, create the flags (`scripts/flagsmith_setup.py`), then set `call_mode=live`.
5. Talk: `.venv/bin/python voice/intake_voice.py --barge-in` (`pip install -e ".[voice]"`, which needs PortAudio).

### Demo-safe calling (the default)

No real bank or donor is ever phoned by default. Who gets dialled is decided by Flagsmith:

| Flag | Default | What it does |
|---|---|---|
| `outbound_calls_enabled` | on | Kill switch. Off = nobody is dialled; re-read before every dial. |
| `call_mode` | `live` | `live` = ring the demo phones; `simulated` = ring no one. |
| `call_real_banks` | **off** | On = dial the REAL bank numbers from e-RaktKosh. Flagsmith-only: no local override can turn it on. |
| `call_donors` | on | On = also ring the demo donor line to restock the bank; off = banks only. |

With the defaults, the top bank in the shortlist is phoned on `DEMO_BANK_PHONES` (the agent still names the real
bank), the donor restock call goes to `DEMO_DONOR_PHONES`, and the other shortlisted banks are listed as leads
with their real numbers. The dashboard and the voice agent label every demo call "via demo line".

## API

| Endpoint | Purpose |
|---|---|
| `POST /tools/find_leads` | Plans the search and calls nobody. Returns `request_id` and `say` |
| `POST /tools/start_calls` | `{request_id, confirmed}`. Refused without `confirmed=true` |
| `POST /tools/get_status` | Long-poll ≤25 s. Returns `say`, `needs_approval`, `done`, `plan` |
| `POST /tools/approve_wave2` / `cancel_request` | Human-in-the-loop #2, or stop |
| `POST /webhooks/sarvam/{call_id}?sig=` | Sarvam outbound result |
| `GET /api/requests[/{id}]`, `GET /api/stream` (SSE), `GET /api/flags` | Dashboard |
| `GET /healthz` | Liveness/readiness |

## Data and stats used

- Mumbai consumes 500–1,000 units/day (SBTC).
- BMJ Global Health 2024: 8 states with 46% of India's population are effectively "blood deserts",
  with 0.68 units per 1,000 people reachable within 60 minutes.
- Pune and Chhatrapati Sambhajinagar reported post-Diwali shortages in Nov 2024.

## Roadmap

Contact-sync (a family's phonebook to find donors), real e-RaktKosh integration, SMS fallback, and
multi-hospital routing.
