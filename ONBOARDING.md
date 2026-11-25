# Getting started on RaktSetu (frontend)

RaktSetu finds blood for a patient. Someone asks by voice or by typing. The backend pulls real blood banks
and live stock from e-RaktKosh, phones the best banks in parallel with Sarvam AI voice agents, and builds a
crossmatch plan from the units the banks confirm on the phone. Your job is the UI on top of that.

## Links

| What | Where |
|---|---|
| Code (private) | https://github.com/mavihsrr/raktsetu |
| Live backend + current dashboard | https://considered-iconographic-setsuko.ngrok-free.dev |
| Live interactive API docs | https://considered-iconographic-setsuko.ngrok-free.dev/docs |
| **API contract + UI rules (read first)** | [`FRONTEND.md`](FRONTEND.md) |
| Current dashboard source (working reference) | [`static/index.html`](static/index.html) |

## 1. Run it locally (10 minutes)

You need Python 3.12 and git. You do **not** need Sarvam, Flagsmith or GCP accounts.

```bash
git clone https://github.com/mavihsrr/raktsetu.git && cd raktsetu
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env        # leave Sarvam, LIVE_TARGETS, DEMO_BANK_PHONES, DEMO_DONOR_PHONES EMPTY
.venv/bin/uvicorn app.main:app --port 8000
```

Then open http://localhost:8000 for the dashboard and http://localhost:8000/docs for the API.

With those lines empty, your local backend **never places a phone call**. Flagsmith is unset, so it falls
back to safe defaults (`call_mode=simulated`). Everything else is real: finding leads hits live e-RaktKosh
and geocoding, so you get real bank names, phones, distances and stock for any Indian city.

Your frontend dev server on `localhost:5173` (Vite) or `localhost:3000` (Next.js) is already allowed by
CORS. For any other origin, add it to `CORS_ORIGINS` in your `.env`.

## 2. Point at the live backend (optional)

Set your frontend's API base URL to `https://considered-iconographic-setsuko.ngrok-free.dev`. Keep the
base URL configurable; never hardcode it.

> ⚠️ The live backend makes **real phone calls**, but only when someone triggers them: clicking **start**
> on a request (or saying "yes" to the voice agent), or approving wave 2. That rings the demo phone (Shivam's).
> Develop against your **local** backend, and use the live one only for a final check or the demo.

## 3. How we work in git

- **Never push to `main`.** Work on a branch and open a pull request:
  ```bash
  git checkout -b frontend/<what-youre-doing>
  git push -u origin frontend/<what-youre-doing>
  ```
  Then open a PR on GitHub. Merge after a quick look from the other person.
- **Stay in your lane to avoid conflicts.** Put new frontend work in `frontend/`, or edit `static/` if you're
  improving the current dashboard. The backend (`app/`), agents (`agents/`, `voice/`) and deploy files
  (`deploy/`, `Dockerfile`) belong to Shivam. If you need a backend change, such as a new endpoint or
  field, ask, or put it in its own small PR.
- **Never commit `.env`** or any key. It's in `.gitignore`; keep it that way.
- Pull often: `git pull --rebase origin main`.

## 4. How it goes live

The backend runs on Google Kubernetes Engine (Mumbai) behind the ngrok URL above. After a PR is merged,
Shivam runs `deploy/deploy.sh`. It builds **only committed code**, deploys it and keeps the same URL
(about 2 minutes).

- If your UI stays inside `static/`, it ships with the backend automatically, at the same URL.
- If it's a separate app (React, Next.js), agree with Shivam on hosting. It can be built into the
  backend image or hosted separately, and then its origin has to be added to `CORS_ORIGINS` on the server.

## 5. Things the UI must get right

These matter for correctness, not style; see `FRONTEND.md` for the full list.

- Portal stock is a **lead**, never a fact. Only `confirmed_units` from a phone call count.
- Donors **never** count toward the patient's units. Show them separately as restock.
- Label `route: "demo"` calls clearly (e.g. "DEMO LINE"). Never imply a real bank was phoned.
- `distance_km` / `lat` / `lng` can be `null`. Show "distance unknown"; never guess.
- The plan ends in a crossmatch at the bank. Never say "blood reserved".

## 6. What's open to build

- **A better dashboard:** request form, live call board (SSE `GET /api/stream?request_id=…`), map
  (patient + banks, coloured by call route/status), and the final plan.
- **Voice in the browser** (ChatGPT-voice-mode style, with interruptions): the plan and the hard parts
  (echo cancellation, keeping the Sarvam key server-side) are in `FRONTEND.md` → "TODO: voice in the browser".

## Who to ask

Shivam: backend, voice agents, deployment, accounts (Sarvam, Flagsmith, GCP, NudgeBee).
