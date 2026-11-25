---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: []
---

Scope: frontend/ voice console (single screen). Mode: Operate.
Audience: hospital blood-centre coordinator at a desk; also a projector demo. Task: speak a request, approve calls, watch phone-verified results, act on the plan.
Quality bar (user-named): ChatGPT Voice Mode, Linear, Vercel dashboard, Perplexity / Claude app.
User addition: live status of what is going on must be first-class (calls ongoing, each call's status).

## Direction contract
THESIS: The category standard, played straight: a calm near-black voice stage with one living orb, beside a precise live-status board. Refuses decoration that competes with the deadline.
OWN-WORLD: Near-black ground (#0b0b0f), raised panels #121218 / #1d1d26 with hairline seams, periwinkle-to-indigo orb (#7c9cff → #3b4bd8), white text, muted #9aa0b4. State colours only for meaning: green confirmed, blue dialing, amber mismatch/approval, red failure/LIVE. System UI sans, tabular figures.
STORY: Coordinator sees the agent is listening, speaks, watches the transcript stream, sees calls fan out live, approves gates with one click or one word, leaves with a ranked plan and the crossmatch instruction.
FIRST VIEWPORT: Three full-height columns (amended from stage + rail because the user asked for the chat window and live status to be visible at once, each first-class): left 300-360px conversation (voice transcript interleaved with backend call events); centre stage with the orb (~320px), state label and hint, mic/end controls, idle: Start talking + name + language; right 400-480px live status (request summary, deadline countdown, phone-confirmed units, approval gate, bank calls by wave, donors). Status chips sit top-right in the top bar. Under 1100px: stage, then live status, then conversation. Primary action: start/stop voice session at the orb.
FORM: canon (standing exit), seed:2ab6fd601c38573f. Signature move: the orb deforms from real audio levels, agent playback vs mic distinguished.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
