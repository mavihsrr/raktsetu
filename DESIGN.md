---
name: RaktSetu
description: Voice-first blood unit finder; a calm near-black voice stage beside a precise live-status board.
colors:
  ground: "#0b0b0f"
  panel: "#111117"
  raised: "#17171f"
  hover: "#1d1d27"
  seam: "#23232e"
  seam-strong: "#2f2f3d"
  text: "#f2f2f5"
  muted: "#a3a6b8"
  faint: "#8a8da0"
  orb-highlight: "#b9c8ff"
  orb-periwinkle: "#7c9cff"
  orb-indigo: "#3b4bd8"
  confirmed-green: "#4ade80"
  dialing-blue: "#7cb4ff"
  approval-amber: "#f5b544"
  failure-red: "#ff6b6b"
  demo-violet: "#b79cff"
  live-red: "#c2334a"
  end-call-red: "#d93a4a"
typography:
  figure:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "40px"
    fontWeight: 650
    lineHeight: 1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    letterSpacing: "-0.015em"
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: "0.01em"
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  transcript:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "14.5px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  mono:
    fontFamily: "ui-monospace, 'SF Mono', 'JetBrains Mono', Menlo, monospace"
    fontSize: "0.92em"
rounded:
  xs: "4px"
  sm: "6px"
  md: "10px"
  lg: "14px"
  pill: "99px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
components:
  button:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "34px"
  button-hover:
    backgroundColor: "{colors.hover}"
  button-primary:
    backgroundColor: "{colors.text}"
    textColor: "{colors.ground}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "34px"
  button-ghost:
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "34px"
  button-ghost-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.text}"
  button-large:
    rounded: "{rounded.pill}"
    padding: "0 22px"
    height: "44px"
  round-control:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    size: "56px"
  round-control-on:
    backgroundColor: "{colors.text}"
    textColor: "{colors.ground}"
  round-control-end:
    backgroundColor: "{colors.end-call-red}"
    textColor: "{colors.text}"
  input:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 10px"
    height: "36px"
  chip:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  chip-live:
    backgroundColor: "{colors.live-red}"
    textColor: "{colors.text}"
  pill-status:
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  banner:
    rounded: "{rounded.md}"
    padding: "10px 12px"
  gate:
    rounded: "{rounded.md}"
    padding: "14px"
  user-bubble:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "9px 12px"
---

# Design System: RaktSetu

## Overview

**Creative North Star: "The Quiet Switchboard"**

RaktSetu plays the voice-assistant category standard straight: a near-black room, one living orb at its centre, and a precise live-status board beside it. The orb is the only object allowed to glow; everything else is flat, hairline-seamed, and set in the system sans at small, exact sizes. The screen exists to prove what the voice said, so the board reads like an instrument panel rather than a page.

Colour carries meaning, never mood. Five state hues (green, blue, amber, red, violet) appear only where a call, gate or line is in that state, almost always as a tinted wash with matching text. The deadline and the confirmed-unit count are the loudest typography on screen; nothing decorative competes with them.

Density is operator-grade: 12 to 14.5px text, 34px controls, tabular figures for every count and time. Motion is restrained and state-driven (a dialing ring, a confirmation flash, the orb's audio-driven deformation), and all of it collapses under reduced motion.

**Key Characteristics:**
- Near-black ground with two lifted surface steps and hairline seams; no shadows.
- One signature: the periwinkle-to-indigo orb that deforms from live audio.
- State colour only for meaning, as 12-14% tinted washes with full-strength text.
- System UI sans throughout; tabular numerals on every figure.
- Pills for status, small radii for controls, full circles for voice controls.

## Colors

A cold near-black neutral ladder, one periwinkle accent family that belongs to the voice, and a strict set of state hues.

### Primary
- **Orb Periwinkle** (`orb-periwinkle`): the voice's colour. Orb body, focus outlines, input caret, focused-field border and its 3px halo, selection tint, the brand drop mark.
- **Orb Highlight** (`orb-highlight`): the agent's name in the transcript, agent lines in call transcripts, and inline links. The pale voice of the agent in text.
- **Orb Indigo** (`orb-indigo`): the orb's depth stop. Not used on UI chrome.

### Secondary (state hues)
- **Confirmed Green** (`confirmed-green`): phone-confirmed units, met target, the units progress segments, the plan wash.
- **Dialing Blue** (`dialing-blue`): calls in progress, the dialing pulse, the blue approval gate.
- **Approval Amber** (`approval-amber`): approval needed, stock mismatch, late countdown, reconnecting.
- **Failure Red** (`failure-red`): failed or unanswered calls, errors, quiet destructive actions.
- **Demo Violet** (`demo-violet`): the DEMO LINE badge only.
- **Live Red** (`live-red`): solid fill for the LIVE chip and LIVE badge; real calls are happening.
- **End-call Red** (`end-call-red`): solid fill for the end-session round control (hover lifts to #e5485a).

Each state hue has a wash companion at the same RGB with 0.12 to 0.14 alpha (`--green-bg`, `--blue-bg`, `--amber-bg`, `--red-bg`, `--violet-bg`); gates add a border at 0.3 to 0.35 alpha.

### Neutral
- **Ground** (`ground`): page background, input fill, text on light buttons.
- **Panel** (`panel`): the transcript and live-status columns; the stage sits on ground between them.
- **Raised** (`raised`): buttons, chips, user bubble, empty progress segments.
- **Hover** (`hover`): hover fill for buttons, rows and round controls.
- **Seam / Seam Strong** (`seam`, `seam-strong`): hairline column and block dividers; control borders and scrollbar thumb.
- **Text** (`text`): primary copy and the inverted primary button fill.
- **Muted** (`muted`): secondary copy, column headings, labels.
- **Faint** (`faint`): timestamps, meta lines, placeholders, icon rest state.

### Named Rules
**The Meaning-Only Rule.** A state hue appears only where something is in that state. No hue is used for emphasis, decoration, or brand.

**The Wash-Not-Fill Rule.** State is shown as a tinted wash with full-strength text of the same hue. Solid state fills are reserved for LIVE and end-call, the two moments that touch the real world.

**The Voice Owns Periwinkle Rule.** Periwinkle marks the voice and keyboard focus. It is never a button fill.

## Typography

**Display Font:** none distinct; the system UI sans carries every role.
**Body Font:** ui-sans-serif / system-ui stack (with -apple-system, Segoe UI, Roboto)
**Label/Mono Font:** ui-monospace stack (SF Mono, JetBrains Mono, Menlo) for phone numbers and IDs.

**Character:** Native, quiet and exact, in the manner of the voice apps and dev dashboards this sits beside. Hierarchy comes from weight (450 to 650) and small size steps, not from a display face.

### Hierarchy
- **Figure** (650, 40px, line-height 1, -0.03em): the confirmed-units count. The one large number on screen; its denominator drops to 22px/500 muted.
- **Headline** (600, 20px, -0.015em): the stage state label. The request title runs one step smaller (650, 19px).
- **Title** (600, 13px, +0.01em): column headings (muted) and block titles (text).
- **Body** (400, 14px, 1.5): base UI copy, stage hint, gate questions.
- **Transcript** (400, 14.5px, 1.55): spoken lines, slightly larger for reading while listening.
- **Label** (400-600, 11.5-12px): chips, pills, field labels, meta lines, timestamps.

### Named Rules
**The Tabular Rule.** Every count, unit, time and countdown uses tabular figures.

**The Weight-Ladder Rule.** Hierarchy moves through weights 450, 550, 600, 650 at small size steps; do not introduce a display face or sizes above the 40px figure.

## Layout

Three full-height columns under a single top bar: conversation (300-360px, panel), stage (380px to fill, ground), live status (400-480px, panel). The page itself does not scroll on desktop; each side column scrolls internally beneath a 52px column head. Under 1100px the grid collapses to one column ordered stage, live status, conversation, the page scrolls, and column scroll areas cap at 70vh.

Spacing runs on a 4px base: 4/8/12/16/20/24 dominate. Column padding is 16px; status blocks separate by 20px plus a hairline; list gaps are 2 to 14px depending on density. The top bar is 12px by 20px with status chips pushed right.

### Named Rules
**The Seam Rule.** Regions are divided by 1px seams, never by gaps of colour or cards floating on ground.

## Elevation & Depth

Flat. Depth is tonal: ground, panel, raised, hover step up in lightness by a few points each, and hairline seams define edges. The only glow in the system is the orb's own radial gradient, drawn in canvas. Focused inputs get a 3px periwinkle halo (`0 0 0 3px rgba(124,156,255,0.18)`), which is a focus signal, not elevation.

### Named Rules
**The One Glow Rule.** Only the orb emits light. No box-shadows on panels, cards, buttons or popovers.

## Shapes

Soft but small. Controls and rows take 6px; banners and gates 10px; the user's transcript bubble 14px with a 4px tail corner at bottom right. Status chips and pills are fully rounded (99px); badges and tags are 4px. Voice controls (56px) and the orb's hit area are perfect circles. Progress segments are 6px bars with 3px ends.

## Components

### Buttons
Quiet, compact, native.
- **Shape:** gently rounded (6px), 34px tall; large variant is a 44px pill.
- **Default:** raised fill, seam-strong border, text colour, 550 weight at 13px.
- **Primary:** inverted, text-colour fill with ground-colour label; hover goes to pure white.
- **Ghost:** transparent, muted label; hover reveals the hover fill and text colour.
- **Danger (quiet):** transparent with failure-red label and a 35% red border; hover adds the red wash.
- **Hover / Disabled:** 150ms background and border transitions on the out-expo ease; disabled drops to 45% opacity.

### Round voice controls
56px circles in raised fill with seam-strong border. Active (mic on) inverts to text fill; end-call is solid end-call red. Press scales to 0.96.

### Chips, Pills, Badges
- **Chips** (top bar system status): 12px, pill radius, raised fill with seam border; warn and bad variants become washes; LIVE is solid live red.
- **Pills** (request status): 11.5px/600, pill radius, wash + hue text per state (planned, calling, awaiting approval, resolved, unresolved).
- **Badges** (route markers on call rows): 10px/700 uppercase, 4px radius; LIVE solid, DEMO violet wash, lead dashed border.

### Cards / Containers
There are no floating cards. Status is grouped into **blocks** separated by seams. **Gates** (approval prompts) are the one bordered container: 10px radius, 14px padding, state wash with a matching 30-35% border, actions right-aligned. The **plan** is a full-bleed green (or amber when short) wash band.

### Inputs / Fields
36px tall, 6px radius, ground fill, seam-strong border, faint placeholder. Focus swaps the border to periwinkle and adds the 3px halo. Labels sit above in 12px muted. On the stage the start fields go transparent with a lighter seam border.

### Call rows
The live board's core list. A four-column row (20px state icon, name and meta, result, chevron) at 9px by 8px, hover fill, expandable to show the call transcript. Dialing shows a blue dot with an expanding ring; a newly confirmed call flashes a green wash that fades over 1.6s and its units turn green.

### Transcript
User lines sit right-aligned in a raised bubble (max 88%); agent lines run unboxed with the agent name in orb highlight. Backend events interleave as faint 12.5px rows on a 2.5% white wash, with icon colour by event state; approval events take the amber wash.

### The Orb (signature)
A canvas blob roughly 320px across that deforms from real audio: the agent's playback swells it, the user's mic draws it in slightly and emits ripple rings. Each voice state has its own three-stop palette (highlight, body, depth) and the orb eases between them: idle and listening periwinkle-indigo, user cooler cyan, thinking violet with faster spin, connecting dimmed with a travelling arc, error red. Under reduced motion it holds still at its state colour.

## Do's and Don'ts

### Do:
- **Do** show state as a 12-14% wash of the state hue with full-strength text in that hue.
- **Do** divide regions with 1px seams (`seam` between regions, `seam-strong` on control borders).
- **Do** use tabular figures for every count, time and countdown.
- **Do** keep the orb the only glowing object, and let it respond to real audio levels.
- **Do** honour reduced motion: the orb stills and transitions collapse.
- **Do** keep controls at 34px (44px for the one large stage action, 56px for round voice controls).

### Don't:
- **Don't** use a state hue for emphasis or decoration; it must mean the state.
- **Don't** add box-shadows or floating cards on the ground; depth is tonal.
- **Don't** fill buttons with periwinkle; it belongs to the voice and focus.
- **Don't** use solid red fills anywhere except LIVE and end-call.
- **Don't** set any text larger than the 40px confirmed-units figure.
