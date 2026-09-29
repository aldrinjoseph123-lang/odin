---
name: Odin
description: Rollout lifecycle tracker read as a flow — white ground, ink text, one blue accent, colour only as state.
colors:
  ground: "#FFFFFF"
  ink: "#101114"
  accent-blue: "#3D5AFE"
  accent-blue-text: "#2F47D6"
  accent-wash: "#EEF1FF"
  on-accent: "#FFFFFF"
  paper: "#F7F7F8"
  muted-fill: "#F3F4F6"
  muted-text: "#6B7280"
  chrome-text: "#4B4F58"
  hairline: "#E4E6EB"
  stroke: "#D0D3DA"
  destructive: "#D6372F"
  ok: "#177A42"
  ok-soft: "#E6F6EC"
  ok-line: "#1F9D55"
  warn: "#8A5300"
  warn-soft: "#FFF4E0"
  warn-line: "#E39B1D"
  bad: "#B4231C"
  bad-soft: "#FDECEB"
  bad-line: "#E0463D"
  brand-red: "#E11D2E"
  brand-red-text-on-ink: "#F23D4D"
  brand-ink: "#0A0A0A"
  brand-muted: "#B8B8B4"
typography:
  brand-display-sm:
    fontFamily: "Chakra Petch, Inter, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.025em"
  brand-display-md:
    fontFamily: "Chakra Petch, Inter, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.025em"
  brand-display:
    fontFamily: "Chakra Petch, Inter, sans-serif"
    fontSize: "52px"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.025em"
  display:
    fontFamily: "Chakra Petch, Inter, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Chakra Petch, Inter, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.025em"
  byline:
    fontFamily: "Chakra Petch, Inter, sans-serif"
    fontSize: "10.5px"
    fontWeight: 600
    letterSpacing: "0.16em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  body-strong:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "13.5px"
    fontWeight: 500
    lineHeight: 1.5
  secondary:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "normal"
  caption:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.5
  micro:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "4.8px"
  md: "6.4px"
  lg: "8px"
  xl: "11.2px"
  full: "9999px"
spacing:
  "0.5": "2px"
  "1": "4px"
  "1.5": "6px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent-blue}"
    textColor: "{colors.on-accent}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: "0 10px"
    height: "32px"
  button-primary-hover:
    backgroundColor: "rgb(61 90 254 / 0.8)"
    textColor: "{colors.on-accent}"
  button-primary-sm:
    backgroundColor: "{colors.accent-blue}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "28px"
  button-outline:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "0 10px"
    height: "32px"
  button-outline-hover:
    backgroundColor: "{colors.muted-fill}"
    textColor: "{colors.ink}"
  filter-chip:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.chrome-text}"
    typography: "{typography.secondary}"
    rounded: "{rounded.full}"
    padding: "0 12px"
    height: "28px"
  filter-chip-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.full}"
    padding: "0 12px"
    height: "28px"
  state-chip-bad:
    backgroundColor: "{colors.bad-soft}"
    textColor: "{colors.bad}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "2px 8px"
  state-chip-warn:
    backgroundColor: "{colors.warn-soft}"
    textColor: "{colors.warn}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "2px 8px"
  state-chip-ok:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ok}"
    typography: "{typography.secondary}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  input-search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "32px"
  card:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "16px"
  rail-panel:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: "12px"
  rollout-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
  rollout-row-hover:
    backgroundColor: "{colors.muted-fill}"
  rollout-row-selected:
    backgroundColor: "{colors.accent-wash}"
    textColor: "{colors.ink}"
  stage-node:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.ink}"
    typography: "{typography.secondary}"
    rounded: "{rounded.lg}"
    padding: "8px 10px"
    height: "58px"
  stage-node-done:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ink}"
  stage-node-next:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.chrome-text}"
  nav-link:
    backgroundColor: "transparent"
    textColor: "{colors.chrome-text}"
    typography: "{typography.body}"
    height: "32px"
  nav-link-current:
    textColor: "{colors.ink}"
  tooltip:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  avatar-initials:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.chrome-text}"
    rounded: "{rounded.full}"
    size: "24px"
---

# Design System: Odin

> **Brand (27 Sep 2026, the user's call).** Odin is a sub-brand: **Odin by Protect24x7**. The parent's black, red `#E11D2E` and Chakra Petch come back *as the brand*, not as the UI: on the logo, the sign-in/reset/email-link panel, the print header, emails, the favicon and the link preview. Inside the app the light/dark flowchart world below still rules; the only brand marks there are the header logo, Chakra Petch page titles and the numbered panel labels. Red stays off the UI because in the app it means "overdue". Full guide: `docs/BRAND.md`.

> **Scope.** This file describes the React front end in `frontend/` only (`frontend/src/index.css` is the normative token source; components are shadcn/ui **base-nova** on Base UI). The Jinja pages under `templates/` and their stylesheet `static/style.css` still carry the *retired* identity (dark nav, red `#E11D2E`, Chakra Petch, 2 px corners) until each page is ported. That stylesheet is frozen and is **not** part of this system; nothing here applies to it and nothing from it should be carried forward.

## Overview

**Creative North Star: "Cards on a tinted ground" (29 Sep 2026, the user's call, from a TaskFlux reference)**

Odin answers one question before anything is read: where is every rollout, and what is stuck. The built world is the soft card dashboard: a ground faintly tinted with the user's accent (`color-mix(in srgb, var(--primary) 7%, #F6F6F9)`), white cards with 16 px corners lifted by a quiet two-layer shadow, pill navigation with the current tab filled in the accent, and inside the cards the same ink text, hairlines and drawn flowchart as before. There is exactly one accent per user (eight to choose from), spent on selection, the primary action, focus, the current nav pill and the "today" marker. Every other colour on the screen is a state (done, on track, due soon / over SLA, overdue) and means nothing else. This replaces the 8 Sep "whiteboard flowchart" world (white ground, no shadows, 8 px corners); what follows records the build.

Density is high but scannable. The first screen is a resizable vertical split: a list of rollout rows above (stuck rows first, each carrying a 7-dot stepper), and the selected rollout below drawn as a left-to-right flowchart with its open tasks hung under the current node, a right rail for next-up / ETA / advance, a time strip along the bottom, and the team and recent notes under it (after the rail below `xl`). Type is small (13 px body) but never below 11 px, and nothing is uppercased. Every piece of content sits on a card (`panel`): the two flow panes, each settings section, every table, tile and widget.

The build rejected, by the user's explicit choice, the dark/industrial look, kanban-style SaaS boards and number-dense grids. Where the direction contract and the build differ, this file records the build.

**Key Characteristics:**
- Accent-tinted ground, white cards, ink text, one accent per user; state colours in matched text / soft-fill / line triplets
- Inter for everything read or typed, with `cv11` + `ss01`; Chakra Petch for page titles and brand surfaces only; sentence case in the UI, tracked caps only on brand surfaces
- 16 px base radius (`--radius: 1rem`) scaled by shadcn's ratios; pills and dots are fully round
- Hairline 1 px borders (`#E9EAF0`); 1.5 px strokes only for flow geometry (nodes, dots, connectors)
- Two shadow tokens, `shadow-card` (cards at rest) and `shadow-pop` (menus, the phone nav); focus and selection are 3 px translucent rings
- Master-detail vertical split; flowchart nodes with drawn arrows at `md` and up, stacked without arrows below

## Brand surfaces

Built in `frontend/src/components/Brand.tsx`; tokens `--brand-red`, `--brand-red-text`, `--brand-ink`, `--brand-paper`, `--brand-muted`, `--brand-edge` (all themes; the edge only shows in dark).

**The Red-Text Rule.** The parent red (`#E11D2E`) is 4.2:1 on brand ink: fine for the logo, the eye, the dot and the 30 px+ tagline, not for small text. Small red text (eyebrow numbers, the byline's "24x7") uses `--brand-red-text`, which is the parent red on white (4.75:1) and lifts to `#F23D4D` inside `.brand-panel` (5.2:1).

- **Logo** = the raven mark (a perched white raven with a red eye on a black tile, corners at 16% of its size) + the ODIN wordmark (chamfered letters drawn as SVG, the O struck through in red: Ø), then, where the byline is shown, a thin rule and "by Protect24x7" on the same line. Header: 28 px mark, 15 px wordmark, letters in `currentColor`.
- **Sign-in pages** (`AuthLayout` + `AuthHeading`; sign-in, reset, email link, Continue): from `lg` the black brand panel fills the left half (eyebrow, the tagline in Chakra Petch 700 uppercase at 52 px with the second line red, supporting line, live "· On watch" clock); below `lg` it shrinks to a band (logo + tagline at 22–28 px) so the form is the first screen on a phone, even at 320×568. The form sits on the page ground with no card, in a 400 px column: a 24 px h1 and a one-line muted lede, then 44 px fields (16 px text, so iOS doesn't zoom) with visible labels. Buttons stay enabled; a missing field is named under it and focused. The password has a show/hide toggle and a Caps Lock warning; "Forgot password?" sits beside its label. Staff see "Sign in with Microsoft" first when it's set up; partners get a full-width "Partner or customer?" row to the email link, not a footnote. A muted "Trouble signing in? Ask your Odin admin." closes the column.
- **Print header** (`PrintBrand`): logo + byline left, tagline right, 2 px ink rule; print only.
- **Numbered labels**: panel titles with `data-n` get "01 / " from a CSS counter on `main`, Chakra Petch, muted ink (never red in the app). Used on the project page, settings, account and the project form.
- **Emails**: `graph.EMAIL_SHELL` wraps every send: black band with the text wordmark (red Ø) and byline, white body, tagline footer. Text, not images.
- **Error page** and **loading splash** carry the mark; `og.png` (1200×630) and `apple-touch-icon.png` (180) live in `frontend/public`.

## Colors

A white-and-ink neutral system with one blue accent and three state triplets; colour is reserved for meaning.

### Primary
- **Accent Blue** (`--primary`, `#3D5AFE`): the only accent. Fills the primary button ("New project", "Advance to …"), the selected-row border, the 2 px underline under the current nav item, the focus ring (`--ring`) and the 1.5 px "today" marker on the time strip.
- **Accent Blue Text** (`--primary-text`, `#2F47D6`): the accent whenever it is *text* on white (the "today" tick label, avatar initials in the nav). `#3D5AFE` itself does not clear AA as text; this step does (6.1:1).
- **Accent Wash** (`--accent`, `#EEF1FF`, with `--accent-foreground` `#2F47D6`): the selected rollout row's fill and the nav avatar's fill. Selection is always wash + blue border, never a solid blue block.

### Neutral
- **Ground** (`--background` / `--card` / `--popover`, `#FFFFFF`): page, panes, nodes, cards. There is no off-white page tint.
- **Ink** (`--foreground`, `#101114`): all primary text; also the *inverted* surfaces — tooltips and the selected filter chip are ink with white text.
- **Paper** (`--secondary`, `#F7F7F8`): the quietest fill; search field background, avatar initials background.
- **Muted Fill** (`--muted`, `#F3F4F6`): hover fill on rows, chips and ghost/outline buttons; the planned-span track on the time strip; the on-track stepper ring.
- **Muted Text** (`--muted-foreground`, `#6B7280`): secondary copy — client names, column heads, durations, empty states, placeholders. 4.8:1 on white.
- **Chrome Text** (`--nav-fg`, `#4B4F58`): a darker grey for UI chrome that must read but not compete: nav links at rest, unselected filter chips, rail section labels ("Next up", "ETA", "Recent"), upcoming stage names, avatar initials.
- **Hairline** (`--border`, `#E4E6EB`): every 1 px divider, panel border, header bottom border, resizable handle, task-list dividers, the card ring is ink at 10% which reads the same.
- **Stroke** (`--input`, `#D0D3DA`): a step darker for geometry that must be visible at 1.5 px on white — input borders, upcoming stepper dots and connectors, dashed "next" stage nodes, task checkboxes.
- **Destructive** (`--destructive`, `#D6372F`): form-error text in `Alert` and the destructive button/badge variants. Not a rollout state; rollout lateness uses `--bad`.

### State triplets
Each rollout state owns three tokens: a **text** shade (AA on white and on its own soft fill), a **soft** fill, and a **line** shade for strokes, dots and bars. The build uses them strictly by role.

| state (`FlowState`) | text | soft fill | line | where |
|---|---|---|---|---|
| done (stage status) | `--ok` `#177A42` | `--ok-soft` `#E6F6EC` | `--ok-line` `#1F9D55` | done stage nodes (soft fill + line border + check), done stepper dots and connectors, success notice |
| `on_track` | — | — | `--ok-line` | no chip, no row dot, no colour; the stepper's current dot is ink-ringed with muted; `ok-line` is only the class mapping for the dot, rendered transparent on rows |
| `due_soon` | `--warn` `#8A5300` | `--warn-soft` `#FFF4E0` | `--warn-line` `#E39B1D` | amber chip "Due 30 Nov", amber row dot, amber ring on the current node/dot |
| `over_sla` | `--warn` | `--warn-soft` | `--warn-line` | same amber triplet as `due_soon`; the chip text ("12 d · 3 over SLA") and the amber bar on the time strip distinguish it |
| `overdue` | `--bad` `#B4231C` | `--bad-soft` `#FDECEB` | `--bad-line` `#E0463D` | red chip "Overdue 237 d", red row dot, red ring on current node/dot, red count badge in the nav, "83 d late" in ETA |

**Figures (dashboard, 29 Sep 2026).** Numbers that are the point of a card use a short ramp of their own, Inter semibold, tight tracking, `leading-none`: **34 px** for the one hero figure on the page (the progress gauge), **26 px** for a tile's headline (the six counts, tasks completed), **22 px** inside a donut, **18 px** for the small tonal tiles (cycle time), **15 px** for a legend's counts. Labels beside them stay on the text ramp (11–12 px muted); nothing on the page goes below 11 px, avatars on the timeline included (22 px, 11 px initials).

### Named Rules
**The One Accent Rule.** Blue appears only as selection (row border + wash, nav underline), the primary action, the focus ring and the today marker. It never labels a state, never decorates, and never appears as a heading colour.

**The Colour-Is-State Rule.** Green, amber and red mean done / warning / overdue and nothing else. `on_track` has *no* colour: an on-track row shows a plain grey duration and a transparent dot, so a coloured row is always a row needing attention.

**The Triplet Rule.** State text uses the base token, state fills use `-soft`, state strokes and dots use `-line`. Never put the text shade in a fill or the line shade under text.

**The Accent-as-Text Rule.** When the accent is text on white, use `--primary-text` (`#2F47D6`), not `--primary`.

## Typography

**Brand Font:** Chakra Petch 600/700 (Google Fonts): page titles (`h1`), the brand panel, byline, eyebrows and panel numbers. Nothing else.
**Display Font:** Inter (with system-ui, -apple-system, sans-serif)
**Body Font:** Inter (same family)
**Label Font:** Inter (same family, no mono in use)

Loaded from Google Fonts at 400 / 500 / 600 / 700; `font-feature-settings: "cv11", "ss01"` (single-storey a, open digits) is set on `html`; text is antialiased.

**Character:** one family, a narrow weight range and a tight size ramp. Hierarchy is carried by weight (500 for names, 600 for titles and labels, 700 only for card titles on the sign-in pages and the brand tagline) and by grey level, not by size. Headings are tracked tight (`-0.025em`); everything else is at normal tracking and sentence case.

### Hierarchy
- **Display** (Chakra Petch 600, 24 px, tight): the h1 on the sign-in, reset and email-link pages ("Sign in to Odin", "Reset your password").
- **Title** (Chakra Petch 600, 17 px, tracking tight): pane titles — "Active rollouts", the selected rollout's name.
- **Wordmark**: the SVG ODIN wordmark, 15 px high in the top bar (see Brand surfaces); it is drawn, not set in a font.
- **Byline** (Chakra Petch 600, 10.5 px, tracked 0.16em, uppercase): "by Protect24x7" on brand surfaces only.
- **Body** (400, 13 px, 1.5): nav links (500), rail copy, empty states, "Open project", search text. `text-sm` (14 px) is the shadcn default on buttons and inputs; the build overrides most inputs to 13 px.
- **Body strong** (500, 13.5 px): the rollout name in each row.
- **Secondary** (400, 12.5 px): rollout subtitles (client · vendor · product · owner), stage node names (600, `leading-tight`), task titles, filter chip labels (500), recent-note text.
- **Label** (500–600, 12 px, sentence case): state chips (500), rail section headers (600, chrome text), form error text.
- **Caption** (400, 11.5 px): column heads over the list, durations and SLA under node names, "2 open before moving on".
- **Micro** (400–600, 11 px): time-strip tick labels, nav count badges, nav avatar initials. Row/task avatar initials are 11 px / 10 px semibold; nothing else goes below 11 px.

### Named Rules
**The Sentence-Case Rule.** No uppercase, no letter-spaced labels in the UI. A label is 12 px, weight 600, chrome text. Tracked caps belong to the brand surfaces only (panel, byline, eyebrows, print header, email).

**The Thirteen Rule.** 13 px is body. Sizes step by half-pixels (13.5 / 12.5 / 11.5) to separate levels without visibly changing scale; do not add sizes above 17 px outside the sign-in card titles and the brand tagline.

## Layout

The app shell is a 52 px white top bar (`h-13`, hairline bottom border, 20 px side padding, 24 px gaps) over a `main` that fills the remaining viewport height (`min-h-svh` column flex). Page gutters are 20 px (`px-5`); vertical rhythm inside panes is 16 px top / 8–12 px between groups; rows are 2 px apart.

**First screen (Flow):** a `react-resizable-panels` vertical split. Top pane defaults to 48% (100% until a rollout is selected), minimum 20%; bottom pane 52%, minimum 25%; the handle is a 1 px hairline with a 24 × 4 px grip. Both panes scroll independently in `ScrollArea` (2.5 px-wide bar, hairline thumb).

- **Rollout list** (`md`+): a four-column grid `minmax(240px,1.6fr) minmax(120px,1fr) 210px 76px` with 16 px gaps and two lines per row — name + client over the **next line** ("Next: task · who · 4 d late · 1 of 2 done · idle 40 d", the same pick as the rail's Next up; the tally only from `lg`, so the task name keeps its room); the stepper; stage over its state and approval chips; the team minus the viewer. Column heads are 11.5 px muted captions. Order is state, then the worst case inside it: overdue and due soon by target date, over SLA by days over, on track by last touched. On-track rows fold into one "n on track · show" line while anything else is listed; a Group select (stage / client / owner, in the URL) lists them under count headers instead. Below `md` a row is three short lines: name + state chip; stage + a 48 px progress bar + approval; the next line. Selecting a row there opens the rollout as its own screen with an "All rollouts" back button (and the browser's Back), not the split.
- **Detail pane**: `xl`+ is `minmax(0,1fr) 280px` with 20 px gap (flow + time strip left, rail right); below `xl` the rail stacks under the flow in two columns (one below `md`), so a laptop shows every stage node without a sideways scroll. When the stages still don't fit (about 112 px each), the flowchart folds: finished stages become one green "✓ n done" node, then stages beyond the next few become one dashed "+n later" node, and the last stage always keeps its own column so the flow visibly ends. A folded node opens the full row on click ("Fold stages to fit" folds it back); phones stack the stages and never fold.
- **Keys**: the rollout list is one tab stop; ↑/↓ or j/k move between rows, Home/End jump, Enter opens. Esc closes the selected rollout (a ghost × in the detail header does the same); inside the Advance confirm, Esc cancels first.
- **Undo a move**: the success notice after Advance carries Undo for five minutes, for the person who moved it, while it is still the latest move. It puts the stage and its clock back, removes the move's history note, restores a superseded approval, is audited, and tells the team it was undone.
- **Finished stages** keep their tasks but lose the "+ Task" link.
- **Advance**: the rail section lists what the move will do before the button (open tasks left in the stage and a pending customer approval in warn text, then how many people are told), and the button asks once more in place ("Move to Deployment now" / Cancel). No modal.
- **Due dates** sit under each task title (11 px muted, "2 d late · due 25 Sep" in bad when past). Next up is the current stage's task with the earliest due date.
- **Flowchart**: an `<ol>` with one equal column per stage (`repeat(n, minmax(0,1fr))`) at `md`+, nodes 6 px apart with a 16 px arrow slot drawn between them; below `md` a single column with 8 px gaps and no arrows. The open-task list under the current node is allowed to spill to twice its column width (`calc(200% + 0.75rem)`).
- **Time strip**: 68 px tall, hairline top border, 16 px above; tick labels on two rows (`top-1` / `top-5`) when closer than 12% of the span; 6 px tracks at `top-10`.

Breakpoints are Tailwind defaults as used: `sm` 640 px, `md` 768 px, `lg` 1024 px. The sign-in, reset and email-link pages are a two-column grid from `lg` (brand panel left, form right); below `lg` the brand panel is a top band. The form is a centred `max-w-sm` (384 px) card.

**The Stuck-First Rule.** The list is ordered by state severity, and on load it opens at the top; the deep-linked row is scrolled into view only after a click so the stuck rows are never hidden.

## Elevation & Depth

Three levels. The **ground** is the tinted page (`--background`). A **card** (`panel` utility: `bg-card`, 1 px `--border`, `rounded-lg`, `shadow-card` = `0 1px 2px ink/4% + 0 10px 28px -14px ink/14%`) is where content lives; cards may nest (a stage node inside the flow card) and the inner card keeps the same shadow. A **popover** (menus, the phone nav sheet, dialogs) uses `shadow-pop` (`0 2px 6px ink/6% + 0 16px 40px -12px ink/22%`). In dark both shadows become a 1 px white-at-3–5% ring plus a deep black drop, since a shadow alone vanishes on ink. Hover raises a surface to Muted Fill; selection raises it to Accent Wash with an accent border. Tooltips stay inverted (ink on white). Focus is a 3 px ring of the accent at 50% (`ring-ring/50`) with the border switched to the accent.

**The Card Rule.** Nothing sits bare on the ground: a page's content is one or more `panel`s. Never hand-roll `border border-border rounded-lg`; use `panel`. Never invent a shadow value; the two tokens are the scale.

## Shapes

Radius base is 8 px (`--radius: 0.5rem`), mapped through shadcn's scale: `lg` 8 px on buttons, inputs, stage nodes, rollout rows, rail panels, alerts; `md` 6.4 px on small buttons, state chips, tooltips, the search field, the menu button; `xl` 11.2 px on the login `Card` (shadcn's card default; the only surface above 8 px). Filter chips, avatars, stepper dots, count badges and time-strip tracks are fully round.

Borders are 1 px hairlines by default. Flow geometry uses **1.5 px**: stage node borders, stepper dot borders, the connectors between dots and nodes, the today marker. Upcoming stage nodes are **dashed** in Stroke grey; done nodes are solid `ok-line` on `ok-soft`; the current node carries a 3 px ring in its state's soft colour over a state-line border (ink border over Muted Fill ring when on track). Arrows between nodes are a 1.5 px line ending in a 12 px `ArrowRight` glyph, green once the stage before them is done, stroke-grey otherwise. Task checkboxes are 14 px squares with a 3 px radius.

## Components

Components are shadcn/ui **base-nova** (Base UI primitives, not Radix). Composition uses the `render` prop (`<TooltipTrigger render={<span />} />`), never `asChild`. Icons are Lucide at 14 px (`h-3.5 w-3.5`) inline in text and 16 px in buttons.

### Buttons
Quiet, small, and rarely blue: one primary per view.
- **Shape:** 8 px radius (`rounded-lg`); size `sm` drops to 6.4 px.
- **Primary (default):** Accent Blue fill, white text, 32 px tall, 10 px side padding, 14 px medium (`sm`: 28 px, 12.8 px text). Used for "New project" (nav, `sm`) and "Advance to {stage}" (rail, `sm`, full width, trailing arrow). Login uses the default size full-width.
- **Hover / Focus / Active:** hover to blue at 80%; focus-visible = accent border + 3 px ring at 50%; active nudges 1 px down; disabled at 50% opacity.
- **Outline:** hairline border, white fill, ink text, hover Muted Fill — "Open project" with an external-link icon. `buttonVariants()` is applied to plain `<a>` when the target is a Jinja page.
- **Secondary / Ghost / Destructive / Link:** present in `button.tsx` but not yet used on a built screen.

### Chips
- **Filter chip** (list header): 28 px pill, hairline border, 12.5 px medium chrome text, count in muted text; hover Muted Fill. Selected: ink fill, white text, count at 70% white. `aria-pressed` carries state.
- **State chip** (rows, detail header): 6.4 px radius, 8 px side / 2 px vertical padding, 12 px medium, `-soft` fill with base-state text (`bad`, `warn`). On-track rows render no chip: plain 12 px muted duration, no fill, no padding. A visually-hidden state label precedes the text so the colour is never the only channel.
- **Count badge** (nav "Alerts 7", "My work"): 20 px round badge, `bad-soft` fill, `bad` text, 11 px.
- **Success notice** (after a stage move): `ok-soft` bar, `ok` text, 12.5 px, 6.4 px radius, with a plain "×" dismiss.

### Projects list: table or cards (29 Sep 2026)
A two-button group (`List` / `LayoutGrid` icons, `aria-pressed`) in the header switches the projects list between the table below and a card grid (1 / 2 / 3 columns at base / `sm` / `xl`), remembered per browser in `localStorage` (`odin.projects.layout`). A card is a hairline panel, 16 px padding: name (link) over client · owner, the team stack at the right; the row's own stepper over "Stage · stage n of m", linking to the flow; a 64 px `ok-line` bar with "d of t tasks done" and the target date. Sorting moves into a select plus a direction button on the filter row while cards are showing, since cards have no column heads.

### Table (projects list)
- Hairline-bordered container (`rounded-lg`), sticky white header row of 11.5 px muted captions; sortable heads are plain buttons that turn ink + medium with a 12 px arrow when active (`aria-sort` carries state). Body 13 px, 8 px vertical / 12 px side cell padding, hairline row dividers, Muted Fill on hover. The project name is a 500-weight link; the Stage cell draws the row's own 7-dot stepper (on-track styling, 96 px) before the stage name and links to the flow. Columns drop from the right as the viewport narrows (`xl` → `lg` → `md` → `sm`); the client folds under the name below `sm`. Filters sit above as filter chips plus two native selects styled as 28 px outline chips and a 28 px search field with an icon submit.

### Project page panels
- The project page reuses the flow screen's detail (flowchart, tasks per stage, rail) under a breadcrumb row (Projects / name, with ghost "On the flow" and "Report" links and outline "Duplicate" / "Edit" actions on the right), then a two-column `lg` grid of hairline panels (`rounded-lg border p-4`): Details (a `dl` with 120 px muted labels), Notes (28 px input + Add, entries divided by hairlines), Team (avatar rows, trash icon on hover-less rows, add/invite forms below a hairline), This project's stages (reorder arrows as 28 px ghost icon buttons, inline rename inputs that reveal a Rename button only when changed, an SLA row of 64 px number inputs), Documents, Sharing (guest links with a copy icon; rotate and delete as outline buttons, delete in `bad` text). Activity is a plain list: a 112 px muted timestamp, then the actor in 500 weight, the action in words, and the detail in muted text after a middle dot. Panel titles are 12 px semibold chrome text with a muted hint after them. Flask's flash messages come back as a muted status bar with an inline Undo link when one is offered.

### Admin pages (users, audit log, settings)
- Same page frame as the projects list: 17 px title, muted count, right-aligned outline/ghost actions, then content. Users is a table (sticky captions, 28 px inline email field that reveals Save only when changed, role as a native select disabled for yourself and for external accounts, outline Deactivate / ghost Reset password) with the add-member form as a bordered card beside it. Audit log is filter selects and two date fields over a dense table with the action in a muted `font-mono` chip. Settings is a two-column grid of the same bordered panels as the project page: stage templates (the shared stage-list editor, one per template), document categories, alert types as a small table of number inputs, selects and `accent-primary` checkboxes, Microsoft 365 (a credentials form until configured, then a connect button, then the connected line with team and channel selects), integrations as checkbox rows. Every save posts to the Jinja form route and shows Flask's flash in the muted status bar.

### Project form
- Two bordered panels side by side at `lg` (Project; Commercial route and delivery), 12 px muted labels over 32 px inputs and native selects, the three dates in a 3-column row, the PO document as a native file input, one primary "Create project" / "Save changes" under the grid. Cascading choices (Via → partner → manager; Delivery mode → vendor/product or outsourcer) swap the fields in place; derived emails are read-only muted inputs. Validation messages from Flask show in an amber `warn-soft` bar above the form.

### Settings (28 Sep 2026)
- One page, a 208 px left menu grouped Workspace / People / Delivery / Connections / Compliance (11.5 px muted group labels, 13 px medium items, the current one on the accent wash). Below `md` the menu becomes one horizontally scrolling row of the same items above the content.
- Each area opens with its 17 px title and a one-line muted lede, then numbered panels. Policy fields are drawn from the server's list: label (13 px medium), control, then 12 px muted help ending with the allowed range. Multi-choices are chips (accent wash + border when on). Save stays disabled until something changes.

### Themes and accents (added 27 Sep 2026 at the user's request)
- **Three themes, per user:** light (the world above), dark, and follow the OS. Dark keeps the world's grammar and inverts the ground: background `#0F1115`, surfaces `#15181E`, hairlines `#262B34`, ink `#E7E8EC`, muted text `#9AA0AB`. State colours keep their meaning with lighter text shades (`ok #4FD08A`, `warn #F2B84B`, `bad #F58C86`) on deep soft fills so chips stay at AA.
- **Eight accents:** blue (default `#3D5AFE`), indigo, violet, teal (`#0F766E`), green (`#15803D`), sky (`#0369A1`), plum (`#A21CAF`), ink. Each sets `--primary`, `--primary-text`, `--accent`, `--accent-foreground` and `--ring`; in dark the text shade lifts (e.g. blue text `#9DB0FF`) and the wash deepens. Every accent carries white button text at 4.5:1 or better. **The No-Alarm-Accent Rule.** There is no red or amber accent: those hues mean overdue and warning, and a red selection or primary button reads as trouble. Rose and amber were retired on 27 Sep 2026 (stored choices moved to plum and sky); green stays because selection is always wash + border, never a state chip.
- **Where it is chosen:** Account → Appearance (theme chips, accent swatches with a hairline ring so ink shows on dark); the header's sun / moon / monitor button cycles the theme in one click. Applied before first paint, so there is no flash.
- **Avatars:** a picture replaces the initials wherever a person appears (header, rollout team stack, task assignee, team rail and panel, users table); initials remain the fallback. Account → Picture uploads PNG / JPG / GIF / WebP up to 2 MB.

### Command palette, relative time, recovery (27 Sep 2026)
- **Command palette:** Ctrl/⌘ K anywhere, or "/" when not typing, or the header's search button (which shows the shortcut). A native `<dialog>` centred at 12 vh, 560 px wide, popover surface, 11.2 px radius, flat like everything else: a hairline border and a dimmed backdrop separate it from the page (no shadow; the notification popover is the same). One 44 px input, then a listbox: matching projects, then tasks, then pages, then "Search all projects for …". The active row takes the accent wash; arrows move, Enter opens, Esc closes.
- **Relative time:** notes, activity, the Recent rail and last sign-in read "just now / 20 min ago / 3 h ago / yesterday / 4 d ago", then a date; the exact local time is the `<time>` title. The audit log stays absolute: it is evidence.
- **Recovery screen:** a render error inside any page shows a centred card with Reload (primary) and Back to the flow, never a blank app. The server's error page is the same card, standalone, following the saved theme.
- **Reduce motion:** under the OS setting every transition and animation is effectively off.
- **Header cluster:** bell, theme button and avatar sit outside the collapsible links, visible at every width; "Log out" moves into the menu below 1024 px.
- **Bell:** a 32 px icon button with the unread count as an accent pill (99+ cap). Its panel drops from the right edge: popover surface, 380 px, a hairline title row with "Mark all read", then entries with an accent dot for unread, the title (500 weight when unread), two muted lines of detail and "2 min ago · who". Unread rows carry a faint accent wash. Click marks read and opens the rollout; Escape or an outside click closes.
- **Mentions:** typing "@" plus letters in the note box offers up to six team members in a small popover list; Enter or click writes "@Full Name ".
- **Own notes:** on hover or focus a note you wrote shows muted "Edit" and "Delete" at the right of its meta line; editing swaps the text for a 3-row textarea with Save / Cancel (Esc cancels). An edited note shows "· edited". A note that records a stage change offers Edit only, with a one-line reason.
- **Upload zone:** the Documents panel is a dashed drop zone (accent border and wash while dragging): category select, "Choose files" link, "or drop them here", and an outline "Upload N files" button; the chosen names show beneath.
- **Loading:** pages show a skeleton (a title bar and fading rows in Muted Fill, pulsing unless reduce-motion is on) instead of "Loading…".

### Dashboard (29 Sep 2026, rebuilt to the TaskFlux reference the same day)
`/dashboard`, the home page: widgets on a three-column grid (`md` two, base one), each a `panel` with a 13.5 px semibold title, a muted subtitle and, at the right, one pill link (`buttonVariants outline sm` made `rounded-full`, 28 px) to the page that holds the full thing. The grid draws the **layout** the server sends — an ordered list of `{id, w, settings}`, `w` in thirds (`WIDTH_CLASS` in `lib/dashboard.ts`) — from the widget catalogue in `services/dashboard.py`: headline numbers (six tiles: icon + label, a 26 px value in the state's text shade only while in that state, a delta pill — `ok-soft` when a worse-when-up count fell, `bad-soft` when it rose, muted otherwise — "since 22 Sep", and a 36 px accent area sparkline of the last 14 snapshots), timeline (every active rollout as a 10 px `bg-muted` track from start to target, the done share filled in the accent, or the state's line colour when stuck, the team's 20 px avatars just past the bar's end, a 1.5 px accent "today" line, month ticks thinned to the track's width), portfolio progress (a 210°→−30° accent radial on a muted track, the percentage as a 34 px hero, three tonal tiles for done / in progress / pending), schedule (a date tile — day number over weekday, or "n d late" in `bad-soft` — title, project · person, an "Open" pill; then approvals waiting on the customer), tasks completed (hero total with a `+69%` pill against the window before, an accent bar chart with the peak bar solid and labelled, the rest at 45%), team (32 px avatar, name, "n rollouts · k open · j late", the account role as a muted chip), rollouts per stage (an accent donut whose slices darken with stage order — an ordered, not categorical, scale — the total in the middle, a clickable legend beside), recent activity (a muted icon disc per kind, "who verb project", the text, relative time), open alerts (severity dot, title, project, age), my work (two-column task list with due dates), cycle time (three tonal tiles and a six-month bar chart). Chart chrome: Recharts, no gridlines, axis ticks 11 px muted, tooltips styled as popovers (`--popover`, `shadow-pop`, 12 px radius), fills always `var(--primary)` so every accent and both themes follow; animations off. Rows of the grid stretch to their tallest widget, so every list is capped with a "n more" link.

### Cards / Containers
- **Rail panel** (Next up / ETA / Advance): white, 1 px hairline, 8 px radius, 12 px padding, 13 px body, 12 px semibold chrome-text header with a 14 px icon; panels stack with 16 px gaps.
- **Card** (sign-in pages): white, `ring-1` ink/10 instead of a border, 11.2 px radius, 16 px internal spacing, `max-w-sm`.
- **Empty state:** dashed hairline box, 8 px radius, 40 px vertical padding, centred 13 px muted text.
- **Alert (destructive):** white, hairline, 8 px radius, 10 px / 8 px padding, destructive text.

### Inputs / Fields
- **Style:** 32 px tall, Stroke-grey 1 px border, transparent fill, 8 px radius, 10 px side padding, 14 px text (13 px where the build overrides); placeholder in muted text.
- **Focus:** border becomes Accent Blue plus a 3 px accent ring at 50%.
- **Search (nav):** the quieter variant — Paper fill, hairline border, 6.4 px radius, ring at 30%.
- **Label:** 14 px medium, 8 px above the field. Invalid: destructive border + 20% destructive ring. Disabled: 50% opacity, Stroke at 50% fill.

### Navigation
56 px bar on the page ground, no border: the logo left (28 px raven mark + 15 px wordmark), then the section links as a white pill bar (`rounded-full bg-card p-1 shadow-card`) of 32 px pills — "Dashboard · Flow · My work · Projects · Cycle time · Alerts · Settings" in 13 px medium Chrome Text, hover to Muted Fill, the current one filled in the accent with white text. Right cluster: the search as a 36 px white pill with `shadow-card`, "New project" (primary `sm`) or a "Read-only" secondary badge for Viewers, bell, theme button, a 28 px avatar (Accent Wash fill, accent-text initials), "Log out" as a text button. Below `lg` (1024 px) the links collapse behind a 36 px menu icon button, while bell, theme button and avatar stay visible, and drop down as a white `rounded-2xl` sheet with `shadow-pop`, 12 px inset from the edges, links stacked as pills. A skip link becomes a primary pill at the top-left on focus.

### Stepper (signature)
12 px dots joined by 1.5 px lines, one per stage of that project. **The Same-Column Rule.** Every row places its dots on one shared column order (the union of all rows' stage lists, each list keeping its own order), so a stage sits in the same column on every row and the lead can read down a column; a stage a project doesn't have leaves a gap on its line. Above the list, on every width, a scrolling strip of named stage pills ("PO Received 13") counts the rollouts in each stage under the current filter; a pill filters the list to that stage (lit ink with ×, kept in the URL). Pills and filter chips are 32 px, 40 px under a coarse pointer; a filter that would change nothing ("Mine" when you are on every rollout) is not offered. Done: `ok-line` fill and border, green connector. Current: white dot, state-line border, 3 px state-soft ring (ink border + Muted Fill ring when on track); scales to 110% when the row is selected. Upcoming: Stroke-grey border, white fill, grey connector. Each dot is a tooltip trigger ("Scoping · done"); the whole stepper carries an `aria-label` naming the current stage.

### Stage node and flow (signature)
One node per stage, minimum 58 px tall, 8 px radius, 1.5 px border, 10 px / 8 px padding: a 12.5 px semibold name (two-line clamp) over an 11.5 px muted line (`0 d` for done, `1 d · SLA 30` for current, `SLA 30 d` for upcoming). Done nodes add a 14 px green check; the current node carries the state ring; upcoming nodes are dashed with chrome-text names. Arrows are drawn between nodes at `md`+. The current node's open tasks hang beneath it as a hairline-divided list (checkbox square, title, 20 px assignee avatar, max four then "+n more") with a caption "n open before moving on".

### Time strip (signature)
A 6 px Muted Fill track spans start → target; each visited stage lays a 6 px ink segment over it (amber `warn-line` when the current stage is over SLA or the rollout is overdue), each a tooltip with its duration. Tick labels are 11 px muted ("Sep 7", "target Nov 30"); "today" is 11 px semibold in Accent Blue Text with a 1.5 × 24 px accent marker.

### Tooltip
Ink fill, white 12 px text, 6.4 px radius, 12 px / 6 px padding, 10 px rotated-square arrow, 4 px offset, zero delay; enters with fade + 95% zoom.

### Avatar
A round picture when the person uploaded one, otherwise initials: 24 px in rows and 20 px under tasks with Paper fill and 11 px / 10 px semibold chrome-text initials; 28 px in the nav with Accent Wash fill and accent-text initials. A hairline ring is drawn inside the circle.

## Do's and Don'ts

### Do:
- **Do** keep Accent Blue to selection, the single primary action, focus and the today marker (The One Accent Rule).
- **Do** map rollout state to its triplet exactly: `overdue` → `bad`, `due_soon` and `over_sla` → `warn`, done stages → `ok`; `on_track` gets no colour.
- **Do** pair every state colour with a second channel — the chip text, a visually-hidden label, the check glyph, dashed vs solid borders.
- **Do** use `--primary-text` for accent-coloured text on white.
- **Do** build on the base-nova components with the `render` prop; apply `buttonVariants()` to anchors that navigate to un-ported Jinja pages.
- **Do** keep chrome at 12–13 px, sentence case, weight 500–600, in Chrome Text or Muted Text.
- **Do** use 1 px hairlines for structure and 1.5 px strokes only for flow geometry (nodes, dots, connectors, today marker).
- **Do** put every piece of content on a `panel`; convey depth inside a card with fill steps (Card → Muted Fill → Accent Wash).

### Don't:
- **Don't** add a third shadow value or a gradient; the ground tint is the accent at 7% and never a second hue.
- **Don't** uppercase or letter-space UI labels, or bring back the retired dark nav, 2 px corners, or the 8 Sep flat white ground. Brand red and Chakra Petch are allowed only where "Brand surfaces" lists them; red never marks anything in the UI except `--bad` state.
- **Don't** use green for "on track" rows or amber/red for anything that is not a lateness state; don't use `--destructive` for rollout state.
- **Don't** put a state's text shade in a fill or its line shade under text.
- **Don't** invent tokens: use the `:root` block in `frontend/src/index.css` and its `@theme inline` aliases (`ok-*`, `warn-*`, `bad-*`, `primary-text`, `nav-fg`). Dark and the accents are whole-token overrides (`:root[data-theme="dark"]`, `:root[data-accent=…]`); a component never branches on the theme.
- **Don't** render the flow as a kanban board or a numeric table; the stepper and the node row are the read.
