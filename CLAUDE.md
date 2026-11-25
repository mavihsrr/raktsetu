# RaktSetu: notes for Claude

Voice-first blood-unit finder (FastAPI + SQLite backend, Sarvam voice agents, Flagsmith flags, e-RaktKosh live data).

- **Frontend work:** read `FRONTEND.md` first. It has the API contract, the UI correctness rules, and how
  browser voice works (built: `frontend/` + `WS /api/voice/ws`; open issue: echo cancellation on laptop speakers).
- Never auto-dial real blood banks. Real bank calls happen only when Flagsmith `call_real_banks` is on.
- No mocks or fake data: banks and stock come live from e-RaktKosh on every request.
- Secrets live only in `.env` (never commit it, never print values, never send `SARVAM_API_KEY` to a browser).
- Portal stock is a lead; only phone-confirmed units count; donors never count toward the patient.
