# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Vite + React + TypeScript, in its own `frontend/` folder, built to static files the FastAPI backend can serve. Voice reaches the browser through a new FastAPI WebSocket that bridges the browser mic/speaker to the Sarvam intake agent (custom `AsyncAudioInterface`), so the Sarvam key stays server-side.

## Users

A hospital blood-centre coordinator who needs blood units for a patient, often with surgery hours away. They speak the request ("4 units of B-positive, City General, surgery in 3 hours"), approve the calling, and act on the final plan. Secondary audience: hackathon judges watching a live demo (WeMakeDevs Festive Hacks).

## Product Purpose

RaktSetu turns one spoken request into a parallel, phone-verified search across nearby blood banks, plus donor recall for restock. Success: the coordinator knows within minutes which banks have confirmed units, how far they are, and where to send the sample for crossmatch.

## Positioning

The national e-RaktKosh portal stock is treated as an unverified lead; RaktSetu phones every bank in parallel and only counts units a bank confirms on the phone, showing portal-vs-phone mismatches. A voice agent runs the whole loop with human approval gates.

## Operating Context

Used at a desk in a bright hospital office under time pressure, and equally on a projector for demos. The voice agent (Sarvam STT + LLM + TTS) calls backend tools: find_leads, start_calls (needs confirmed=true), get_status, approve_wave2, cancel_request. The backend emits live events over SSE: leads_found, calls_started, call_started, bank_result, bank_confirmed, donor_result, wave1_done, approval_needed, wave2_started, target_met, paused, resumed, cancelled, resumed_after_restart. Operator flags come from Flagsmith (kill switch, call_mode simulated/live, parallelism, autopilot, radii).

## Capabilities and Constraints

- Only phone-confirmed bank units count toward the patient's need. Donors never count; they are restock only and shown separately.
- The plan always ends with: send the patient's sample and requisition to the bank for crossmatch.
- Two human gates: starting calls, and widening to wave 2 (unless autopilot is on).
- Calls are labelled by route: SIM (simulated), LIVE, DEMO LINE, LEAD.
- Half-duplex voice was a laptop-speaker workaround; browser echo cancellation should allow barge-in.

## Brand Commitments

Name: RaktSetu ("blood bridge").

## Evidence on Hand

Banks, phone numbers and stock come live from e-RaktKosh on every request (any hospital + town in India); no mock data. Donors are placeholder data today. Real banks are dialled only when Flagsmith `call_real_banks` is on; otherwise a demo phone stands in (route "demo", labelled DEMO LINE). No real testimonials, partners or metrics; none may be invented. API contract and UI rules: `FRONTEND.md`.

## Product Principles

1. Verified over reported: show what was confirmed on the phone, and where the portal was wrong.
2. The human stays in charge: every irreversible step is an explicit, visible approval.
3. Voice leads, the screen proves: anything said aloud is visible and checkable on screen.
4. Calm under urgency: the deadline is always visible, nothing decorative competes with it.

## Accessibility & Inclusion

Voice-first but never voice-only: every action is also a visible control, and every utterance is transcribed. Must respect reduced motion.
