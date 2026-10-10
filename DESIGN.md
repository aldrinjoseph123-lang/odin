---
name: Odin
description: Rollout lifecycle tracker read as a flow — accent-tinted ground, white cards with a quiet shadow, one pastel accent per user (blue by default), colour only as state.
colors:
  ground: "color-mix(in srgb, #CCDAFF 7%, #F6F6F9)"   # the accent at 7% over near-white; each accent re-tints it
  card: "#FFFFFF"
  ink: "#101114"
  accent-fill: "#CCDAFF"        # default accent (blue, 10 Oct 2026); each of the nine accents swaps these
  on-accent: "#1C3A8C"
  accent-text: "#2F47D6"
  accent-wash: "#EEF2FF"
  accent-ring: "#7090FF"
  paper: "#F7F7F8"
  muted-fill: "#F3F4F6"
  muted-text: "#5B6270"
  chrome-text: "#4B4F58"
  hairline: "#E9EAF0"
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
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.5
  secondary:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "13px"
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
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  micro:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "9.6px"
  md: "12.8px"
  lg: "16px"
  xl: "22.4px"
  full: "9999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent-fill}"
    textColor: "{colors.on-accent}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.lg}"
    padding: "0 12px"
    height: "32px"
  button-primary-hover:
    backgroundColor: "rgb(204 218 255 / 0.8)"
    textColor: "{colors.on-accent}"
  button-primary-sm:
    backgroundColor: "{colors.accent-fill}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "28px"
  button-outline:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "0 10px"
    height: "32px"
  button-outline-hover:
    backgroundColor: "{colors.muted-fill}"
    textColor: "{colors.ink}"
  filter-chip:
    backgroundColor: "{colors.card}"
    textColor: "{colors.chrome-text}"
    typography: "{typography.secondary}"
    rounded: "{rounded.full}"
    padding: "0 12px"
    height: "28px"
  filter-chip-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card}"
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
    padding: "4px 12px"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "4px 12px"
    height: "32px"
  input-search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "32px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
    padding: "16px"
  rail-panel:
    backgroundColor: "{colors.card}"
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
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.secondary}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
    height: "58px"
  stage-node-done:
    backgroundColor: "{colors.ok-soft}"
    textColor: "{colors.ink}"
  stage-node-next:
    backgroundColor: "{colors.card}"
    textColor: "{colors.chrome-text}"
  nav-link:
    backgroundColor: "transparent"
    textColor: "{colors.chrome-text}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.full}"
    padding: "0 16px"
    height: "36px"
  nav-link-current:
    backgroundColor: "{colors.accent-fill}"
    textColor: "{colors.on-accent}"
  tooltip:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card}"
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

A white-and-ink neutral system with one pastel accent per user (blue by default) and three state triplets; colour is reserved for meaning.

### Primary
- **Blue Accent Fill** (`--primary`, `#CCDAFF`, with `--primary-foreground` `#1C3A8C`): the default of nine pastel accents (blue again since 10 Oct 2026; red was the default 9–10 Oct). Fills the primary button ("New project", "Advance to …") and the current nav pill, always with the deep foreground as its text, never white. The other accents swap the same five tokens (see Themes and accents).
- **Blue Accent Text** (`--primary-text`, `#2F47D6`): the accent whenever it is *text* or a thin mark on white (links, the selected settings item's bar, chart marks). The pastel fill itself does not clear AA as text or as a line on white; this step does.
- **Accent Wash** (`--accent`, `#EEF2FF`, with `--accent-foreground` `#2F47D6`): the selected rollout row's fill and the nav avatar's fill. Selection is always wash + accent border, never a solid block.
- **Accent Ring** (`--ring`, `#7090FF`): the focus ring, at 50%.

### Neutral
- **Ground** (`--background`, the accent at 7% over `#F6F6F9`): the page behind the cards; each accent re-tints it.
- **Card** (`--card` / `--popover`, `#FFFFFF`): panes, nodes, cards, menus.
- **Ink** (`--foreground`, `#101114`): all primary text; also the *inverted* surfaces — tooltips and the selected filter chip are ink with white text.
- **Paper** (`--secondary`, `#F7F7F8`): the quietest fill; search field background, avatar initials background.
- **Muted Text** (`--muted-foreground`, `#5B6270`, 30 Sep 2026): the secondary text shade, chosen by measurement — the darkest tinted ground (the ink accent at 7%) and every soft fill hold it at 4.9:1 or better, where the earlier `#6B7280` fell to 3.9. Dark keeps `#9AA0AB` (5.7:1 at worst). The UI suite's axe tier enforces this on every page in both themes.
- **Muted Fill** (`--muted`, `#F3F4F6`): hover fill on rows, chips and ghost/outline buttons; the planned-span track on the time strip; the on-track stepper ring.
- **Chrome Text** (`--nav-fg`, `#4B4F58`): a darker grey for UI chrome that must read but not compete: nav links at rest, unselected filter chips, rail section labels ("Next up", "ETA", "Recent"), upcoming stage names, avatar initials.
- **Hairline** (`--border`, `#E9EAF0`): every 1 px divider, panel border, header bottom border, resizable handle, task-list dividers, the card ring is ink at 10% which reads the same.
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

**Figures (dashboard; on the six sizes since 9 Oct 2026).** Numbers that are the point of a card are Inter semibold, tight tracking, `leading-none`: **24 px** for a tile's headline and the hero figures (the six counts, tasks completed, the progress gauge, Time on Odin; 17 px on a phone), **17 px** inside a donut and on small tonal tiles, **14 px** for a legend's counts. Chart marks are Chrome Text (`--nav-fg`) at stepped opacity, never the accent: a chart is grey until it counts trouble, when a tile's trend takes its state's `-line` colour (10 Oct 2026, the critique). Labels beside them stay on the text ramp (11–12 px muted); nothing on the page goes below 11 px, avatars on the timeline included (22 px, 11 px initials).

### Named Rules
**The One Accent Rule.** The accent appears only as selection (row border + wash, the current nav pill), the primary action and the focus ring; charts are grey. It never labels a state, never decorates, never appears as a heading colour, and never marks today (today is ink, so a red accent never reads as overdue).

**The Colour-Is-State Rule.** Green, amber and red mean done / warning / overdue and nothing else. `on_track` has *no* colour: an on-track row shows a plain grey duration and a transparent dot, so a coloured row is always a row needing attention.

**The Triplet Rule.** State text uses the base token, state fills use `-soft`, state strokes and dots use `-line`. Never put the text shade in a fill or the line shade under text.

**The Accent-as-Text Rule.** When the accent is text or a thin mark on white, use `--primary-text` (`#2F47D6` for blue), not `--primary`; the pastel fill carries only `--primary-foreground`.

## Typography

**Brand Font:** Chakra Petch 600/700 (served by Odin, `static/fonts`): page titles (`h1`), the brand panel, byline, eyebrows and panel numbers. Nothing else.
**Display Font:** Inter (with system-ui, -apple-system, sans-serif)
**Body Font:** Inter (same family)
**Label Font:** Inter (same family). The system monospace appears only on values a person copies exactly (URLs, keys, tokens), never on prose or dates.

Served by Odin itself since 10 Oct 2026 (`static/fonts/fonts.css`: Inter variable 100–900 and Chakra Petch 400–700, latin, OFL; no third-party request, so the CSP allows fonts from 'self' only), used at 400 / 500 / 600 / 700; `font-feature-settings: "cv11", "ss01"` (single-storey a, open digits) is set on `html`; text is antialiased.

**Character:** one family, a narrow weight range and a tight size ramp. Hierarchy is carried by weight (500 for names, 600 for titles and labels, 700 only for card titles on the sign-in pages and the brand tagline) and by grey level, not by size. Headings are tracked tight (`-0.025em`); everything else is at normal tracking and sentence case.

### Hierarchy
- **Display** (Chakra Petch 600, 24 px, tight): the h1 on the sign-in, reset and email-link pages ("Sign in to Odin", "Reset your password").
- **Title** (Chakra Petch 600, 17 px, tracking tight): pane titles — "Active rollouts", the selected rollout's name.
- **Wordmark**: the SVG ODIN wordmark, 15 px high in the top bar (see Brand surfaces); it is drawn, not set in a font.
- **Byline** (Chakra Petch 600, 10.5 px, tracked 0.16em, uppercase): "by Protect24x7" on brand surfaces only.
- **Body** (400, 13 px, 1.5): nav links (500), rail copy, empty states, "Open project", search text. `text-sm` (14 px) is the shadcn default on buttons and inputs; the build overrides most inputs to 13 px.
- **Body strong** (500, 14 px): the rollout name in each row, buttons.
- **Secondary** (400, 13 px): rollout subtitles (client · vendor · product · owner), stage node names (600, `leading-tight`), task titles, filter chip labels (500), recent-note text.
- **Label** (500–600, 12 px, sentence case): state chips (500), rail section headers (600, chrome text), form error text.
- **Caption** (400, 12 px): column heads over the list, durations and SLA under node names, "2 open before moving on".
- **Micro** (400–600, 11 px): time-strip tick labels, nav count badges, nav avatar initials. Row/task avatar initials are 11 px / 10 px semibold; nothing else goes below 11 px.

### Named Rules
**The Sentence-Case Rule.** No uppercase, no letter-spaced labels in the UI. A label is 12 px, weight 600, chrome text. Tracked caps belong to the brand surfaces only (panel, byline, eyebrows, print header, email).

**The Six-Size Rule (9 Oct 2026, replaces the Thirteen Rule).** The app uses six sizes: 11 (micro), 12 (captions, labels, chips), 13 (body), 14 (names, buttons), 17 (page and pane titles) and 24 (display titles and figures). Nothing in the app goes above 24 px or below 11 px; the half-pixel steps are gone. Hierarchy beyond that is carried by weight and by grey level (muted text), never by another size. Brand surfaces keep their own sizes (the 52 px tagline, the 10.5 px byline), and phone inputs stay 16 px so iOS does not zoom.

## Layout

The app shell is a 72 px top bar on the page ground (`h-18`, 20 px side padding, 16 px gaps; see Navigation) over a `main` that fills the remaining viewport height (`min-h-svh` column flex). Page gutters are 20 px (`px-5`); vertical rhythm inside panes is 16 px top / 8–12 px between groups; rows are 2 px apart.

**First screen (Flow):** a `react-resizable-panels` vertical split. Top pane defaults to 48% (100% until a rollout is selected), minimum 20%; bottom pane 52%, minimum 25%; the handle is a 1 px hairline with a 24 × 4 px grip. Both panes scroll independently in `ScrollArea` (2.5 px-wide bar, hairline thumb).

- **Rollout list** (`md`+): a four-column grid `minmax(240px,1.6fr) minmax(120px,1fr) 210px 76px` with 16 px gaps and two lines per row — name + client over the **next line** ("Next: task · who · 4 d late · 1 of 2 done · idle 40 d", the same pick as the rail's Next up; the tally only from `lg`, so the task name keeps its room); the stepper; stage over its state and approval chips; the team minus the viewer. Column heads are 12 px muted captions. Order is state, then the worst case inside it: overdue and due soon by target date, over SLA by days over, on track by last touched. On-track rows fold into one "n on track · show" line while anything else is listed; a Group select (stage / client / owner, in the URL) lists them under count headers instead. Below `md` a row is three short lines: name + state chip; stage + a 48 px progress bar + approval; the next line. Selecting a row there opens the rollout as its own screen with an "All rollouts" back button (and the browser's Back), not the split.
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

Three levels. The **ground** is the tinted page (`--background`). A **card** (`panel` utility: `bg-card`, 1 px `--border`, `rounded-lg`, `shadow-card` = `0 1px 2px ink/4% + 0 10px 28px -14px ink/14%`) is where content lives. A **popover** (menus, the phone nav sheet, dialogs, toasts) uses `shadow-pop`. **No card inside a card (9 Oct 2026):** a `panel` inside another loses its border and shadow and becomes a 3% tone step (`index.css`, `.panel .panel`), so settings sections, the flow rail and AI drafts read by alignment and tone; floating surfaces (listbox, dialog, menu, `shadow-pop`) keep their box. Inner boxes are never hand-drawn with a border: use a tone (`bg-muted/60`, a state's `-soft`). **Dark has no drop shadows:** depth is tone — ground `#0E1014`, card `#171A21`, popover `#1D2129`, hover `#252A34` — each with a faint 1 px light edge. Hover raises a surface to Muted Fill; selection raises it to Accent Wash with an accent border. Tooltips and toasts stay inverted (ink on white). Focus is a 3 px ring of the accent at 50% with the border switched to the accent.

**The Card Rule.** Content sits on a `panel`, and a panel never sits inside another one (it becomes a tone step). Never hand-roll `border border-border rounded-lg`; use `panel` or a tone. Never invent a shadow value; the two tokens are the scale.

**The Grid Rule (9 Oct 2026).** Every padding, margin and gap is a multiple of 4 px (4, 8, 12, 16, 24, 32…): no 2, 6, 10 or 14 px steps (`*-0.5`, `*-1.5`, `*-2.5`, `*-3.5`) in spacing. Icon sizes are not spacing and keep their steps.

## Shapes

Radius base is 16 px (`--radius: 1rem`, 29 Sep 2026), mapped through shadcn's scale: `lg` 16 px on cards (`panel`), buttons, inputs, stage nodes, rollout rows, rail panels, alerts; `md` 12.8 px on small buttons, state chips, tooltips, the search field, menu items; `sm` 9.6 px on the smallest controls; `xl` 22.4 px on the command palette and dialogs. Filter chips, avatars, stepper dots, count badges and time-strip tracks are fully round.

Borders are 1 px hairlines by default. Flow geometry uses **1.5 px**: stage node borders, stepper dot borders, the connectors between dots and nodes, the today marker. Upcoming stage nodes are **dashed** in Stroke grey; done nodes are solid `ok-line` on `ok-soft`; the current node carries a 3 px ring in its state's soft colour over a state-line border (ink border over Muted Fill ring when on track). Arrows between nodes are a 1.5 px line ending in a 12 px `ArrowRight` glyph, green once the stage before them is done, stroke-grey otherwise. Task checkboxes are 14 px squares with a 3 px radius.

## Components

Components are shadcn/ui **base-nova** (Base UI primitives, not Radix). Composition uses the `render` prop (`<TooltipTrigger render={<span />} />`), never `asChild`. Icons are Lucide at 14 px (`h-3.5 w-3.5`) inline in text and 16 px in buttons.

### Buttons
Quiet, small, and rarely blue: one primary per view.
- **Shape:** 16 px radius (`rounded-lg`); size `sm` drops to 12 px (`min(--radius-md, 12px)`).
- **Primary (default):** the pastel accent fill with its deep foreground text, 32 px tall, 12 px side padding, 14 px medium (`sm`: 28 px, 13 px text). Used for "New project" (nav, `sm`) and "Advance to {stage}" (rail, `sm`, full width, trailing arrow). Login uses the default size full-width.
- **Five states (9 Oct 2026):** default; hover (the fill at 80%, only while enabled); pressed (scale 0.98); disabled (40% opacity, not-allowed cursor); **loading** (`<Button loading>`: same size, label hidden behind a spinner, `aria-busy`, no second click). Focus-visible = accent border + 3 px ring at 50%. Every form's submit button and a panel's single primary action use `loading`; a big form never greys out its button until complete, it explains instead (below).
- **Outline:** hairline border, white fill, ink text, hover Muted Fill — "Open project" with an external-link icon. `buttonVariants()` is applied to plain `<a>` when the target is a Jinja page.
- **Ghost:** the quiet action beside a primary one (Cancel, Discard). **Destructive** (`--destructive`, not the overdue `--bad`): deleting, removing, revoking — red that means "this destroys", always behind the app's one confirm dialog (`lib/confirm.ts`). Errors are written in `--destructive` too; `--bad` is kept for overdue.

### Chips
- **Filter chip** (list header): 28 px pill, hairline border, 12 px medium chrome text, count in muted text; hover Muted Fill. Selected: ink fill, white text, count at 70% white. `aria-pressed` carries state.
- **State chip** (rows, detail header): `rounded-md` (12.8 px) or a full pill, 8 px side / 2 px vertical padding, 12 px medium, `-soft` fill with base-state text (`bad`, `warn`). On-track rows render no chip: plain 12 px muted duration, no fill, no padding. A visually-hidden state label precedes the text so the colour is never the only channel.
- **Count badge** (nav "Alerts 7", "My work"): 20 px round badge, `bad-soft` fill, `bad` text, 11 px.
- **Success notice** (after a stage move): `ok-soft` bar, `ok` text, 13 px, `rounded-md`, with a plain "×" dismiss.

### Projects list: table or cards (29 Sep 2026)
A two-button group (`List` / `LayoutGrid` icons, `aria-pressed`) in the header switches the projects list between the table below and a card grid (1 / 2 / 3 columns at base / `sm` / `xl`), remembered per browser in `localStorage` (`odin.projects.layout`). A card is a hairline panel, 16 px padding: name (link) over client · owner, the team stack at the right; the row's own stepper over "Stage · stage n of m", linking to the flow; a 64 px `ok-line` bar with "d of t tasks done" and the target date. Sorting moves into a select plus a direction button on the filter row while cards are showing, since cards have no column heads.

### Table (projects list)
- Hairline-bordered container (`rounded-lg`), sticky white header row of 12 px muted captions; sortable heads are plain buttons that turn ink + medium with a 12 px arrow when active (`aria-sort` carries state). Body 13 px, 8 px vertical / 12 px side cell padding, hairline row dividers, Muted Fill on hover. The project name is a 500-weight link; the Stage cell draws the row's own 7-dot stepper (on-track styling, 96 px) before the stage name and links to the flow. Columns drop from the right as the viewport narrows (`xl` → `lg` → `md` → `sm`); the client folds under the name below `sm`. Filters sit above as filter chips plus two native selects styled as 28 px outline chips and a 28 px search field with an icon submit.

### Project page panels
- The project page reuses the flow screen's detail (flowchart, tasks per stage, rail) under a breadcrumb row (Projects / name, with ghost "On the flow" and "Report" links and outline "Duplicate" / "Edit" actions on the right), then a two-column `lg` grid of hairline panels (`rounded-lg border p-4`): Details (a `dl` with 120 px muted labels), Notes (28 px input + Add, entries divided by hairlines), Team (avatar rows, trash icon on hover-less rows, add/invite forms below a hairline), This project's stages (reorder arrows as 28 px ghost icon buttons, inline rename inputs that reveal a Rename button only when changed, an SLA row of 64 px number inputs), Documents, Sharing (guest links with a copy icon; rotate and delete as outline buttons, delete in `bad` text). Activity is a plain list: a 112 px muted timestamp, then the actor in 500 weight, the action in words, and the detail in muted text after a middle dot. Panel titles are 12 px semibold chrome text with a muted hint after them. Flask's flash messages come back as a muted status bar with an inline Undo link when one is offered.

### Plan, RAID and the reports (30 Sep 2026)
- **Plan panel** (project page, full width, first): the RAG pill (`RagPill`: state-soft ground, state text, a dot) with its reasons in muted text; four tiles on `bg-muted/50` (forecast, target, against baseline, complete); the `PlanGantt`; then the editable table (native date inputs, 12.5 px, the current row on `bg-accent/40`, slip in `bad` only when late). Actions below: outline "Fill the gaps from SLAs", a cascade checkbox, the reason input (only once a baseline exists and something moved), primary "Save plan", outline "Re-baseline" (dialog with a required reason). The change log folds behind a muted History toggle.
- **PlanGantt**: one row per stage — baseline a 3 px `bg-input` line under the row, plan an outlined `primary/70` pill, actual a solid 8 px bar (`foreground/70` done, `primary` current, `warn-line` when the current stage runs past its plan), forecast `primary/30`; today a 1.5 px `primary/60` rule, target a dashed `bad-line` rule. Every row is a focusable `role="img"` with the whole story in its label and tooltip. The legend shows Baseline only when baseline dates are present (never on the customer copy).
- **RAID panel**: counts as pills (blockers `bad-soft`, issues `warn-soft`), Open/All segmented toggle, rows with a kind icon (open blocker icon in `bad`), impact pill, due date turning `bad` with "n d late"; an Eye icon marks customer-visible items. One dialog adds and edits.
- **Rollout report**: `max-w-6xl` page; toolbar with the Internal / Customer copy segmented control, the version select, outline PDF and Print pills, primary "Save as version". Header 24 px project name, meta line, RAG pill. Tiles are `panel` cards (22 px figures). Sections are `Section` cards (`components/ReportParts.tsx`, `break-inside-avoid`) with numbered `h2`s. The words are textareas for the editor with a "Use the suggestion" link, plain text in print and for readers.
- **Portfolio report**: health mix as one 12 px stacked bar (2 px gaps) with a counted legend; KPI tiles with 26 px figures; the roadmap is one row per rollout — health dot and name linking to its report, a bar from start to today in the health's `-line` colour, the forecast remainder in the health's `-soft` fill with a `-line` border, the baseline finish a 2 px `foreground/50` tick, the target a dashed `bad-line` tick. Marks wear the `-line` tokens; text wears the state colour.
- **PDFs** (`services/report_pdf.py`): A4, Helvetica, the ink brand band with the red bar (a brand surface), number boxes on a faint ground, the same Gantt/roadmap drawn as vectors with the same colour roles, hairline tables with late cells in `bad`.

### Dashboard, people, sign-up and templates (30 Sep 2026)
- **Dashboard**: the widget header carries a ⋯ button beside expand (the KPI strip: a corner button on hover/focus); it opens a popover (`shadow-pop`, `rounded-xl`, hairline ring) with the widget's settings, a ⅓/⅔/Full segmented control, Earlier/Later and a `bad` "Remove from my dashboard". The header has an outline "Add widget" pill (a popover list of widgets with their blurbs) and a ⋯ layout menu. A grip appears on hover for dragging. Saves report in the status line with an Undo link.
- **Time on Odin panel**: three tiles on `muted/50`, a 30-bar strip in `primary/70` (empty days a hairline at 25%), last seen and last sign-in in muted text.
- **Join page**: the sign-in layout (brand panel + form); two large radio tiles for Email / Microsoft Teams; a success state with a check.
- **Sign-up links panel** (Users page, right column under Add user): a compact form of selects and a list with state and uses; the new link shown once in a mono field with Copy.
- **Documents settings**: per kind a panel of templates (accent dot, name, Default chip, Make default, duplicate, delete); the editor in two columns — cards for template, brand (accent swatches in the PDF's own colours, logo uploads with thumbnails), sections (checkbox, name, up/down) and wording (textareas, placeholder chips) — and a sticky preview panel framing the rendered PDF.
- **PDFs with a template**: the logo replaces the ODIN wordmark on the ink band; a customer logo sits in a white box at the band's right; the accent drives plan outlines, current bars, forecast fills and the today line; the company line sits under the title; the template footer precedes the page footer.

### Scope and sign-off (30 Sep 2026)
- **Scope and sign-off panel** (project page, full width after RAID): a status bar on top (FileSignature icon, "Sign-off vN: <state in words>", a pill link that is the primary button while the project sits in the Sign-off stage, outline otherwise; `ok-soft` ground once signed), then count pills per scope status, then a numbered list — title, detail and note in muted text, a status pill (delivered `ok-soft`, partly `warn-soft`, agreed and descoped `muted`, descoped titles struck through), up/down arrows for the editor. One dialog adds and edits, with a segmented status control.
- **Flow rail**: when the next stage is the terminal one and the sign-off is not complete, the Advance panel is replaced by "Sign-off before <stage>" with the state in words and one full-width button to the sign-off page; a signatory whose signature is awaited sees a `warn-soft` "Your signature" card instead.
- **Sign-off page**: `max-w-6xl`, toolbar (back link, version select, outline PDF / Print pills, admin's "Close without signatures"), a 24 px "Sign-off" title, a state pill. Composing (the project manager, nothing open): numbered `Section` cards with textareas (summary, delivered or the read-only scope list, outstanding, handover), the acceptance statement on `muted/60`, and a sticky 320 px rail to pick the signatory and countersigner and send (two-step confirm). Reading: the same cards as the document, two signature blocks side by side (card-white boxes, drawn signatures as `currentColor` strokes, typed ones in 28 px italic), and the signing record with the fingerprint in mono and an `ok`/`bad` integrity line; the rail holds the sign form (name, title, Draw/Type segmented control, a dashed pad with a baseline, the accept checkbox, the primary Sign button, a quiet "I can't sign this yet" link) or the paper-copy and withdraw actions.
- **Sign-off PDF**: the report PDF's page builder — brand band "Project sign-off · version N", facts in two columns, a state pill, the scope table, bullets, the acceptance statement on a faint box, two ruled signature blocks, the signing record, and the fingerprint in the footer.

### Admin pages (users, audit log, settings)
- Same page frame as the projects list: 17 px title, muted count, right-aligned outline/ghost actions, then content. Users (9 Oct 2026) is a list of receipt rows, not a table: avatar, name and "username · email" (once, when they are the same) on the left; the role select (plain "External" text for partner accounts); how they sign in and when they last did, as two muted lines; one outline Manage button. Manage opens a dialog for the rarely used controls — email, sign-in options, set a password, reset two-step, and Deactivate last as the destructive action. On phones Manage sits beside the name and role and state share one line. The add-member form and sign-up links sit beside the list from 2xl and below it otherwise. Audit log is filter selects and two date fields over a dense table with the action in a muted `font-mono` chip. Settings is a two-column grid of the same bordered panels as the project page: stage templates (the shared stage-list editor, one per template), document categories, alert types as a small table of number inputs, selects and `accent-primary` checkboxes, Microsoft 365 (a credentials form until configured, then a connect button, then the connected line with team and channel selects), integrations as checkbox rows. Every save posts to the Jinja form route and shows Flask's flash in the muted status bar.

### Project form
- Two bordered panels side by side at `lg` (Project; Commercial route and delivery), 12 px muted labels over 32 px inputs and native selects, the three dates in a 3-column row, the PO document as a native file input, one primary "Create project" / "Save changes" under the grid. Cascading choices (Via → partner → manager; Delivery mode → vendor/product or outsourcer) swap the fields in place; derived emails are read-only muted inputs. Validation messages from Flask show in an amber `warn-soft` bar above the form.

### Settings (28 Sep 2026)
- One page, a 208 px left menu grouped Workspace / People / Delivery / Connections / Compliance (12 px muted group labels, 13 px medium items; the current one a white block with the card shadow, bold ink text and a 4 px accent bar, see the 9 Oct refresh). Below `md` the menu becomes one horizontally scrolling row of the same items above the content.
- Each area opens with its 17 px title and a one-line muted lede, then numbered panels. Policy fields are drawn from the server's list: label (13 px medium), control, then 12 px muted help ending with the allowed range. Multi-choices are chips (accent wash + border when on). Save stays disabled until something changes.

### Themes and accents (added 27 Sep 2026 at the user's request)
- **Three themes, per user:** light (the world above), dark, and follow the OS. Dark keeps the world's grammar and inverts the ground: background `#0F1115`, surfaces `#15181E`, hairlines `#262B34`, ink `#E7E8EC`, muted text `#9AA0AB`. State colours keep their meaning with lighter text shades (`ok #4FD08A`, `warn #F2B84B`, `bad #F58C86`) on deep soft fills so chips stay at AA.
- **Nine pastel accents (9 Oct 2026, supersedes the 27 Sep set):** blue (the default again from 10 Oct 2026: fill `#CCDAFF` / text on fill `#1C3A8C` / accent text `#2F47D6`), red, indigo, violet, teal, green, sky, plum, ink. Each sets `--primary` (pastel fill), `--primary-foreground` (deep text on the fill, never white), `--primary-text`, `--accent`, `--accent-foreground` and `--ring`; in dark the text shade lifts (e.g. red `#FDA4B4`) and the wash deepens. **The State-Safe Accent Rule** (10 Oct 2026, replaces the Rose-Not-Alarm Rule): an accent whose text or wash could pass for a state keeps its hue only in the pastel fill. Red (overdue) and green (done) are offered, but their accent text, wash and ring fall back to ink and neutral (`index.css`, the state-safe block), so a selected row or a link never reads as late or finished. Blue is the default because the 10 Oct critique found the red accent's text (`#B4143C`) matched overdue (`#B4231C`). Today is drawn in ink.
- **Where it is chosen:** Account → Appearance (theme chips, accent swatches with a hairline ring so ink shows on dark); the header's sun / moon / monitor button cycles the theme in one click. Applied before first paint, so there is no flash.
- **Avatars:** a picture replaces the initials wherever a person appears (header, rollout team stack, task assignee, team rail and panel, users table); initials remain the fallback. Account → Picture uploads PNG / JPG / GIF / WebP up to 2 MB.

### Command palette, relative time, recovery (27 Sep 2026)
- **Command palette:** Ctrl/⌘ K anywhere, or "/" when not typing, or the header's search button (which shows the shortcut). A native `<dialog>` centred at 12 vh, 560 px wide, popover surface, `rounded-xl` (22.4 px), flat like everything else: a hairline border and a dimmed backdrop separate it from the page (no shadow; the notification popover is the same). One 44 px input, then a listbox: matching projects, then tasks, then pages, then "Search all projects for …". The active row takes the accent wash; arrows move, Enter opens, Esc closes.
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
**Needs attention (10 Oct 2026, the critique).** The default layout opens with a "Needs attention" widget top-left beside the Timeline: one row per rollout in trouble, worst first (overdue, over SLA, due soon, waiting on the customer, idle), each with its reasons as small state pills in words ("40 d late", "6 d over SLA in Deployment"); empty, it says nothing is stuck. Headline numbers follow, labelled as rollout counts. Rollouts per stage defaults to the stage flow (dots on a connector, count, "n late · n slipping"), not a donut. Timeline rows carry name over client · stage, a state word on every row in trouble, and the team in its own column.

`/dashboard`, the home page: widgets on a three-column grid (`md` two, base one), each a `panel` with a 14 px semibold title, a muted subtitle and, at the right, one pill link (`buttonVariants outline sm` made `rounded-full`, 28 px) to the page that holds the full thing. The grid draws the **layout** the server sends — an ordered list of `{id, w, settings}`, `w` in thirds, packed into rows without holes by `pack()` in `lib/dashboard.ts` (a row pulls up the next widget that fits; its last widget stretches) — from the widget catalogue in `services/dashboard.py`: headline numbers (six tiles: icon + label, a 26 px value in the state's text shade only while in that state, a delta pill — `ok-soft` when a worse-when-up count fell, `bad-soft` when it rose, muted otherwise — "since 22 Sep", and a 36 px accent area sparkline of the last 14 snapshots), timeline (every active rollout as a 10 px `bg-muted` track from start to target, the done share filled in the accent, or the state's line colour when stuck, the team's 20 px avatars just past the bar's end, a 1.5 px accent "today" line, month ticks thinned to the track's width), portfolio progress (a 210°→−30° accent radial on a muted track, the percentage as a 34 px hero, three tonal tiles for done / in progress / pending), schedule (a date tile — day number over weekday, or "n d late" in `bad-soft` — title, project · person, an "Open" pill; then approvals waiting on the customer), tasks completed (hero total with a `+69%` pill against the window before, an accent bar chart with the peak bar solid and labelled, the rest at 45%), team (32 px avatar, name, "n rollouts · k open · j late", the account role as a muted chip), rollouts per stage (an accent donut whose slices darken with stage order — an ordered, not categorical, scale — the total in the middle, a clickable legend beside), recent activity (a muted icon disc per kind, "who verb project", the text, relative time), open alerts (severity dot, title, project, age), my work (two-column task list with due dates), cycle time (three tonal tiles and a six-month bar chart). Chart chrome: Recharts, no gridlines, axis ticks 11 px muted, tooltips styled as popovers (`--popover`, `shadow-pop`, 12 px radius), fills always `var(--primary)` so every accent and both themes follow; animations off. Rows of the grid stretch to their tallest widget, so every list is capped with a "n more" link. A **tile** is a button: it opens a pop-up (`Dialog`, `sm:max-w-lg`) listing the rollouts behind the number, each a link with its state text at the right. Every other widget carries a 28 px **expand** button (`Maximize2`) in its header opening a `sm:max-w-4xl` pop-up: the widget at full size (lists uncapped, charts taller), then its data as a plain table (11.5 px muted heads, tabular numbers). Chart type is a setting where it makes sense (donut / bars, bars / line, area / bars / none, radial / bar, list / bars). A **custom metric** widget (dashed pill in the picker, repeatable) shows any aggregate as a hero number, thin bars, a donut or a list, under a title of the user's own. The page is **live**: a green dot and "updated n s ago" in the title row; the version endpoint is polled every 15 s and on focus, never while the tab is hidden.

### Cards / Containers
- **Rail panel** (Next up / ETA / Advance): white, 1 px hairline, 16 px radius (a tone step when inside a card), 12 px padding, 13 px body, 12 px semibold chrome-text header with a 14 px icon; panels stack with 16 px gaps.
- **Card** (`panel`): white, 1 px hairline, 16 px radius, `shadow-card`, 16 px internal padding; the sign-in form sits on the ground with no card (see Brand surfaces).
- **Empty state:** dashed hairline box, 16 px radius, 40 px vertical padding, centred 13 px muted text.
- **Alert (destructive):** white, hairline, 16 px radius, 12 px / 8 px padding, destructive text.

### Inputs / Fields
- **Style:** 32 px tall, Stroke-grey 1 px border, transparent fill, 16 px radius, 12 px side padding, 14 px text (13 px where the build overrides); placeholder in muted text.
- **Focus:** border becomes the accent ring colour plus a 3 px ring at 50%.
- **Search (nav):** the quieter variant — Paper fill, hairline border, `rounded-md` (12.8 px), ring at 30%.
- **Label:** 14 px medium, 8 px above the field. Invalid: destructive border + 20% destructive ring. Disabled: 50% opacity, Stroke at 50% fill.

### Navigation
72 px bar on the page ground (9 Oct 2026; 36 px pills, Log out in the avatar menu — see the refresh), no border: the logo left (28 px raven mark + 15 px wordmark), then the section links as a white pill bar (`rounded-full bg-card p-1 shadow-card`) of 32 px pills — "Dashboard · Flow · My work · Projects · Cycle time · Alerts · Settings" in 13 px medium Chrome Text, hover to Muted Fill, the current one filled in the accent with white text. Right cluster: the search as a 36 px white pill with `shadow-card`, "New project" (primary `sm`) or a "Read-only" secondary badge for Viewers, bell, theme button, a 28 px avatar (Accent Wash fill, accent-text initials), "Log out" as a text button. Below `lg` (1024 px) the links collapse behind a 36 px menu icon button, while bell, theme button and avatar stay visible, and drop down as a white `rounded-2xl` sheet with `shadow-pop`, 12 px inset from the edges, links stacked as pills. A skip link becomes a primary pill at the top-left on focus.

### My work and People (30 Sep 2026)
**My work**: four tiles (open tasks, overdue in `bad`, done this week, my rollouts in `warn` when any is stuck), then a 1.6 : 1 split — tasks grouped under 12 px semibold group heads (Overdue in `bad`, Today in `warn`, then This week, Later, No date), each row a 20 px tick square that finishes the task in place, title over rollout · stage, the date or "n d late" chip at the right, a select to narrow to one rollout; beside it a 14-day done strip (accent bars, muted when zero) and the person's rollouts with role chip, stepper, stage and state. **People**: cards on a 1 / 2 / 3 / 4 column grid — 44 px avatar, name and role, four tonal figure tiles (rollouts, open, late in `bad`, done 30 d), a 6 px on-time / late bar — the whole card a link. **A person**: 56 px avatar with name, role, email and last seen, a primary "Notify" pill; four tiles; then contribution (eight weekly accent bars, the peak labelled), active rollouts, pending, upcoming (date tiles), and "Recently" across two columns. Notify is a `Dialog` with a textarea and an optional rollout select; the confirmation is a status line.

### Flow views: Calendar and Kibana (29 Sep 2026)
The Flow page's title row carries a segmented control (`rounded-full bg-muted p-0.5`, 28 px pills, the current one lifted `bg-card shadow-card`): **Rollouts · Calendar · Kibana**, kept in the URL as `?view=`. The other two views replace the split with one full-height card.

**Calendar.** A toolbar (previous / next / Today pills, the month as a 14 px semibold title, and four toggle chips — Rollouts, Targets, Tasks, Moves & approvals), a Mon–Sun head row on hairlines, then six weeks of at least 112 px, days outside the month on Muted Fill at 40%, today's number a 24 px accent disc. Active rollouts run as 14 px bars across their days at the top of each week (three lanes, longest first; what does not fit becomes "+n rollouts" in the day): the accent with white text when on track; when stuck, the state's soft fill and text ringed in its line colour (white on amber is 2.3:1, so the name would vanish), square-cornered where they continue past the week. Under them each day lists up to three 11.5 px chips — a 12 px glyph (check square = task, target = target date, arrow = stage move, shield = approval) in the item's tone, then the text — and "+n more", which opens the day below the grid as a three-column list. Every chip and bar links into the flow. Below `md` the month is an agenda: a heading per day that has anything, today's in the accent text.

**Kibana.** Dashboard names as pills (`role="tablist"`), a "Rollout" select when any address carries `{project}`, `{client}` or `{po}` (the flow's own `?rollout=`, so a dashboard opened from a rollout shows it; without one, a centred line asks for a pick), "Open in Kibana" at the right, and the chosen dashboard in a sandboxed iframe on a hairline. The list comes from the `kibana_dashboards` policy (Settings → Integrations, one "Name | address" per line, drawn as a monospace textarea); the Flow page's CSP allows exactly those origins in `frame-src`. Empty state: a line for staff, a line plus an "Open Integrations" pill for admins.

### Stepper (signature)
12 px dots joined by 1.5 px lines, one per stage of that project. **The Same-Column Rule.** Every row places its dots on one shared column order (the union of all rows' stage lists, each list keeping its own order), so a stage sits in the same column on every row and the lead can read down a column; a stage a project doesn't have leaves a gap on its line. Above the list, on every width, a scrolling strip of named stage pills ("PO Received 13") counts the rollouts in each stage under the current filter; a pill filters the list to that stage (lit ink with ×, kept in the URL). Pills and filter chips are 32 px, 40 px under a coarse pointer; a filter that would change nothing ("Mine" when you are on every rollout) is not offered. Done: `ok-line` fill and border, green connector. Current: white dot, state-line border, 3 px state-soft ring (ink border + Muted Fill ring when on track); scales to 110% when the row is selected. Upcoming: Stroke-grey border, white fill, grey connector. Each dot is a tooltip trigger ("Scoping · done"); the whole stepper carries an `aria-label` naming the current stage.

### Stage node and flow (signature)
One node per stage, minimum 58 px tall, 16 px radius, 1.5 px border, 12 px / 8 px padding: a 13 px semibold name (two-line clamp) over a 12 px muted line (`0 d` for done, `1 d · SLA 30` for current, `SLA 30 d` for upcoming). Done nodes add a 14 px green check; the current node carries the state ring; upcoming nodes are dashed with chrome-text names. Arrows are drawn between nodes at `md`+. The current node's open tasks hang beneath it as a hairline-divided list (checkbox square, title, 20 px assignee avatar, max four then "+n more") with a caption "n open before moving on".

### Time strip (signature)
Flow pane only (the project page has the full plan chart instead; 9 Oct 2026, the user could not read the bare strip). It opens with a titled line in words, "Timeline · Started 16 Aug · day 55 · target 23 Aug, 47 days late" (`timelineSummary`), and a small legend (stage done, current stage, today). The bar is drawn only when the span is two days or more: a 6 px `foreground/10` track from the start to the target (to today when there is none), each visited stage a segment at least 6 px wide (green `ok-line` done, ink current, amber `warn-line` when over SLA or overdue) with its duration as a tooltip. Tick labels are 11 px muted ("Aug 16", "target Aug 23"); "today" is 11 px semibold ink with a 1.5 × 24 px ink marker.

### Tooltip
Ink fill, white 12 px text, `rounded-md` (12.8 px), 12 px / 4 px padding, 10 px rotated-square arrow, 4 px offset, zero delay; enters with fade + 95% zoom.

### Avatar
A round picture when the person uploaded one, otherwise initials: 24 px in rows and 20 px under tasks with Paper fill and 11 px / 10 px semibold chrome-text initials; 28 px in the nav with Accent Wash fill and accent-text initials. A hairline ring is drawn inside the circle.

### Feedback: toasts and inline errors (9 Oct 2026)
- **Toast** (`toast()` in `lib/toast.ts`, `Toaster` in the shell): an action that changed something and shows nothing else answers with one short line, bottom centre, ink with a green check (red alert icon for `tone: "bad"`), leaving after 4 s (8 s with an action such as Undo); at most three. The region is a polite live region without a status role, so page notices keep `role="status"`. Errors that need reading stay inline, next to their field or panel.
- **Inline errors** (`lib/fieldErrors.ts`, installed once in `main.tsx`): on submit the first invalid field gets `aria-invalid`, focus, a red border and ring, and the browser's own explanation right under it (`role="alert"`, 12 px, `--destructive`); every other invalid field is outlined (`:user-invalid`). Both clear the moment the value is valid. Forms rely on `required` / `minLength` / `type` for this; one-field quick adds (a task, a note) may stay disabled until typed.

### Lists: receipts and chunks (9 Oct 2026)
- **Receipt rows:** what the row is about on the left (title, its context under it); its weight, age, state and actions on the right, right-aligned. The default state is quiet grey text (an alert's "Open", a passed AI feature); only exceptions carry a fill.
- **Chunks:** a long list reads in groups that match its sort, under a 12 px semibold `rowgroup` header on a muted tone: the audit log by day (`dayBucket`: Today, Yesterday, then the date), alerts by severity (a state dot) with resolved last, My work by Overdue / Today / This week / Later.
- **Faces for names:** a person in a row or rail is an avatar beside the name (20–24 px).
- **Copy:** a heading is about seven words at most, its subtext about fourteen; detail moves to the point of action (a hint by the field, a confirmation).

### The 9 Oct 2026 refresh (the user's calls)
- **Pastel accents (blue the default again since 10 Oct).** Every accent is a soft pastel fill with deep text (`--primary` pastel, `--primary-foreground` deep, `--primary-text` for accent-as-text, `--ring` a mid tone); nothing white sits on the fill. Red was the default from 9 to 10 Oct (`migrated.accent_red`), then blue again (`migrated.accent_blue`) after the critique found red read as overdue; the choices are Red, Blue, Indigo, Violet, Teal, Green, Sky, Plum, Ink on the Account page. This reverses the earlier retirement of rose: the user chose red. To keep it apart from the overdue state, the accent red is a rose-leaning pastel fill (#FFD3DA / #8E1230) while overdue stays the solid `--bad` triplet with its word ("Overdue 9 d").
- **Progress is a straight line.** The stepper is a row of 6 px rounded segments, one per stage, 4 px apart: done green (`ok-line`), the current one in its state (ink on track, amber due soon / over SLA, red overdue), upcoming a quiet grey; shared columns keep stages aligned across rows; each segment has its tooltip.
- **Header.** 72 px tall; pills 36 px with 16 px sides in a 6 px-padded white pill bar; Log out and Account settings live in the avatar menu ("Your account"), so the bar fits 1,280 px.
- **Tooltips everywhere.** `TitleTips` turns any `title` and any icon-only control's aria-label into one styled ink tooltip (12 px, after 450 ms hover, at once on keyboard focus, gone on leave, scroll or Esc); the Tooltip component stays for richer content.
- **Settings menu.** The open area is a white block with the card shadow, bold ink text and a 4 px accent bar on its left.
- **Today is ink.** The today line and label on the plan chart, the dashboard timeline, the flow's time strip and the portfolio roadmap are ink (foreground), not the accent: with a red accent an accent line read as an overdue warning.
- **Widget handle.** Dashboard widgets are dragged by a small horizontal handle centred in the card's top margin, shown on hover; it never covers a title.
- **Settings in small cards.** Each settings area is a two-column masonry of small titled cards, one topic each (Projects & workflow: Defaults, Stage timing, Health colours, Sign-off, Customer approval), each with its own Save; a card posts only its own keys and its switches as "on"/"0", so saving one never touches another. Under each setting one plain 12 px line with an example (`hint` in `policies.py`); the longer explanation sits behind a "What is this?" link that opens a popover.
- **Contacts & partners in tabs.** One tab per pick-list (Account managers, Partners, Vendors, Products, Outsourcers, each with its count), one card per tab: a plain-language line and an example on top, "Add …" as the primary button, then a table with "Used in N projects" (a popover listing them) and a ⋯ menu (Edit, Delete). Adding and editing happen in a dialog; a rename carries into every project that names the entry. Products are grouped under their vendor, with "Any vendor" last; partners expand to their account managers on a tone row.

### shadcn components in use (9 Oct 2026)
Reach for these before hand-building: **Calendar** behind `DatePicker` for every date (weeks start Monday, month/year dropdowns, Today/Clear); **Progress + Spinner** behind `AIProgress` for every AI draft (queue place, then a bar towards the feature's usual time); **Switch** for on/off settings; **Native Select** look for every `<select>` (one global CSS rule in index.css); **Kbd** (⌘K, Esc), **Empty** (empty lists with an icon), **Breadcrumb** (Projects › name), **Skeleton** (page loading), **Pagination** behind `Pager`; plus the existing Button, Dialog, Popover, Tooltip, Badge, Avatar, Alert. **Tabs** (Contacts & partners) and **DropdownMenu** (row ⋯ menus). Candidates when their screens are next touched: Select (searchable), Sheet (phone menu), ToggleGroup (segmented controls), Command (palette), HoverCard (people).

## Do's and Don'ts

### Do:
- **Do** keep the accent to selection, the single primary action and focus; charts are grey and today is ink (The One Accent Rule).
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
