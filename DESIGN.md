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
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "-0.025em"
  wordmark:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    letterSpacing: "-0.025em"
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

> **Scope.** This file describes the React front end in `frontend/` only (`frontend/src/index.css` is the normative token source; components are shadcn/ui **base-nova** on Base UI). The Jinja pages under `templates/` and their stylesheet `static/style.css` still carry the *retired* identity (dark nav, red `#E11D2E`, Chakra Petch, 2 px corners) until each page is ported. That stylesheet is frozen and is **not** part of this system; nothing here applies to it and nothing from it should be carried forward.

## Overview

**Creative North Star: "The Whiteboard Flowchart"**

Odin answers one question before anything is read: where is every rollout, and what is stuck. The built world is convention played straight, benchmarked against Linear and FigJam: a white ground, ink text, hairline borders, and stage nodes with arrows drawn between them. It has no metaphor and no atmosphere; the interface is the diagram. There is exactly one accent, a saturated blue, and it is spent only on selection, the primary action, focus and the "today" marker. Every other colour on the screen is a state (done, on track, due soon / over SLA, overdue) and means nothing else.

Density is high but scannable. The first screen is a resizable vertical split: a list of rollout rows above (stuck rows first, each carrying a 7-dot stepper), and the selected rollout below drawn as a left-to-right flowchart with its open tasks hung under the current node, a right rail for next-up / ETA / advance, and a time strip along the bottom. Type is small (13 px body) but never below 11 px, and nothing is uppercased. Surfaces are flat: no shadows anywhere, depth comes from hairlines and tonal fills.

The build rejected, by the user's explicit choice, the dark/industrial look, kanban-style SaaS boards and number-dense grids. Where the direction contract and the build differ, this file records the build.

**Key Characteristics:**
- White ground, ink text, one blue accent; state colours in matched text / soft-fill / line triplets
- Inter throughout with `cv11` + `ss01` features; sentence case, no tracked uppercase labels
- 8 px base radius (`--radius: 0.5rem`) scaled by shadcn's ratios; pills and dots are fully round
- Hairline 1 px borders (`#E4E6EB`); 1.5 px strokes only for flow geometry (nodes, dots, connectors)
- No box-shadows; focus and selection are 3 px translucent rings
- Master-detail vertical split; flowchart nodes with drawn arrows at `md` and up, stacked without arrows below

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

### Named Rules
**The One Accent Rule.** Blue appears only as selection (row border + wash, nav underline), the primary action, the focus ring and the today marker. It never labels a state, never decorates, and never appears as a heading colour.

**The Colour-Is-State Rule.** Green, amber and red mean done / warning / overdue and nothing else. `on_track` has *no* colour: an on-track row shows a plain grey duration and a transparent dot, so a coloured row is always a row needing attention.

**The Triplet Rule.** State text uses the base token, state fills use `-soft`, state strokes and dots use `-line`. Never put the text shade in a fill or the line shade under text.

**The Accent-as-Text Rule.** When the accent is text on white, use `--primary-text` (`#2F47D6`), not `--primary`.

## Typography

**Display Font:** Inter (with system-ui, -apple-system, sans-serif)
**Body Font:** Inter (same family)
**Label Font:** Inter (same family, no mono in use)

Loaded from Google Fonts at 400 / 500 / 600 / 700; `font-feature-settings: "cv11", "ss01"` (single-storey a, open digits) is set on `html`; text is antialiased.

**Character:** one family, a narrow weight range and a tight size ramp. Hierarchy is carried by weight (500 for names, 600 for titles and labels, 700 only for the wordmark and the login title) and by grey level, not by size. Headings are tracked tight (`-0.025em`); everything else is at normal tracking and sentence case.

### Hierarchy
- **Display** (700, 24 px, tight): the "Odin" title on the login card only.
- **Title** (600, 17 px, tracking tight): pane titles — "Active rollouts", the selected rollout's name.
- **Wordmark** (700, 15 px, tracking tight): "Odin" in the top bar.
- **Body** (400, 13 px, 1.5): nav links (500), rail copy, empty states, "Open project", search text. `text-sm` (14 px) is the shadcn default on buttons and inputs; the build overrides most inputs to 13 px.
- **Body strong** (500, 13.5 px): the rollout name in each row.
- **Secondary** (400, 12.5 px): rollout subtitles (client · vendor · product · owner), stage node names (600, `leading-tight`), task titles, filter chip labels (500), recent-note text.
- **Label** (500–600, 12 px, sentence case): state chips (500), rail section headers (600, chrome text), form error text.
- **Caption** (400, 11.5 px): column heads over the list, durations and SLA under node names, "2 open before moving on".
- **Micro** (400–600, 11 px): time-strip tick labels, nav count badges, nav avatar initials. Row/task avatar initials go to 10 px / 9 px semibold; nothing else does.

### Named Rules
**The Sentence-Case Rule.** No uppercase, no letter-spaced labels. A label is 12 px, weight 600, chrome text. The tracked-caps device belongs to the retired identity.

**The Thirteen Rule.** 13 px is body. Sizes step by half-pixels (13.5 / 12.5 / 11.5) to separate levels without visibly changing scale; do not add sizes above 17 px outside the login display.

## Layout

The app shell is a 52 px white top bar (`h-13`, hairline bottom border, 20 px side padding, 24 px gaps) over a `main` that fills the remaining viewport height (`min-h-svh` column flex). Page gutters are 20 px (`px-5`); vertical rhythm inside panes is 16 px top / 8–12 px between groups; rows are 2 px apart.

**First screen (Flow):** a `react-resizable-panels` vertical split. Top pane defaults to 48% (100% until a rollout is selected), minimum 20%; bottom pane 52%, minimum 25%; the handle is a 1 px hairline with a 24 × 4 px grip. Both panes scroll independently in `ScrollArea` (2.5 px-wide bar, hairline thumb).

- **Rollout list** (`md`+): a four-column grid `minmax(200px,1.2fr) 2fr 170px 36px` with 16 px gaps — name, stepper, in-stage chip, owner avatar. Column heads are captions in muted text. Below `md` the row collapses to two columns (name / chip) with the stepper spanning a second line; client name and avatar are hidden below `sm` / `md`.
- **Detail pane**: `lg`+ is `minmax(0,1fr) 280px` with 20 px gap (flow + time strip left, rail right); below `lg` the rail stacks under the flow.
- **Flowchart**: an `<ol>` with one equal column per stage (`repeat(n, minmax(0,1fr))`) at `md`+, nodes 6 px apart with a 16 px arrow slot drawn between them; below `md` a single column with 8 px gaps and no arrows. The open-task list under the current node is allowed to spill to twice its column width (`calc(200% + 0.75rem)`).
- **Time strip**: 68 px tall, hairline top border, 16 px above; tick labels on two rows (`top-1` / `top-5`) when closer than 12% of the span; 6 px tracks at `top-10`.

Breakpoints are Tailwind defaults as used: `sm` 640 px, `md` 768 px, `lg` 1024 px. Login is a single centred `max-w-sm` (384 px) card with 24 px page padding.

**The Stuck-First Rule.** The list is ordered by state severity, and on load it opens at the top; the deep-linked row is scrolled into view only after a click so the stuck rows are never hidden.

## Elevation & Depth

No box-shadows anywhere in the built app. Depth is conveyed by hairlines and tonal layering: panels are white bounded by a 1 px `#E4E6EB` border; cards use a 1 px ring of ink at 10% instead of a border; hover raises a surface to Muted Fill; selection raises it to Accent Wash with an accent border. The one "floating" surface, the tooltip, is inverted (ink on white) rather than lifted, and animates in with a 95% zoom + fade. Focus is a 3 px ring of the accent at 50% (`ring-ring/50`) with the border switched to the accent; the search field uses the same at 30%.

**The Flat Rule.** Surfaces are flat at rest and under interaction. Do not add `shadow-*` to a panel, popover or button; use a border, a ring, or a fill step.

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

### Table (projects list)
- Hairline-bordered container (`rounded-lg`), sticky white header row of 11.5 px muted captions; sortable heads are plain buttons that turn ink + medium with a 12 px arrow when active (`aria-sort` carries state). Body 13 px, 8 px vertical / 12 px side cell padding, hairline row dividers, Muted Fill on hover. The project name is a 500-weight link; the Stage cell draws the row's own 7-dot stepper (on-track styling, 96 px) before the stage name and links to the flow. Columns drop from the right as the viewport narrows (`xl` → `lg` → `md` → `sm`); the client folds under the name below `sm`. Filters sit above as filter chips plus two native selects styled as 28 px outline chips and a 28 px search field with an icon submit.

### Cards / Containers
- **Rail panel** (Next up / ETA / Advance): white, 1 px hairline, 8 px radius, 12 px padding, 13 px body, 12 px semibold chrome-text header with a 14 px icon; panels stack with 16 px gaps.
- **Card** (login): white, `ring-1` ink/10 instead of a border, 11.2 px radius, 16 px internal spacing, `max-w-sm`.
- **Empty state:** dashed hairline box, 8 px radius, 40 px vertical padding, centred 13 px muted text.
- **Alert (destructive):** white, hairline, 8 px radius, 10 px / 8 px padding, destructive text.

### Inputs / Fields
- **Style:** 32 px tall, Stroke-grey 1 px border, transparent fill, 8 px radius, 10 px side padding, 14 px text (13 px where the build overrides); placeholder in muted text.
- **Focus:** border becomes Accent Blue plus a 3 px accent ring at 50%.
- **Search (nav):** the quieter variant — Paper fill, hairline border, 6.4 px radius, ring at 30%.
- **Label:** 14 px medium, 8 px above the field. Invalid: destructive border + 20% destructive ring. Disabled: 50% opacity, Stroke at 50% fill.

### Navigation
White 52 px bar: wordmark left, then "Flow · My work · Projects · Cycle time · Alerts · Settings" as 13 px medium links in Chrome Text, hover to ink. The current section is ink with a 2 px Accent Blue bar sitting on the header's bottom edge (`after:-bottom-[15px]`). Right cluster: search, "New project" (primary `sm`) or a "Read-only" secondary badge for Viewers, a 28 px avatar (Accent Wash fill, accent-text initials), "Log out" as a text button. Below `md` the links collapse behind a 36 px menu icon button and drop down as a full-width white sheet with a hairline bottom border and 12 px gaps. A skip link becomes a primary-blue pill at the top-left on focus.

### Stepper (signature)
Seven 12 px dots joined by 1.5 px lines, one per configured stage, filling the row's middle column. Done: `ok-line` fill and border, green connector. Current: white dot, state-line border, 3 px state-soft ring (ink border + Muted Fill ring when on track); scales to 110% when the row is selected. Upcoming: Stroke-grey border, white fill, grey connector. Each dot is a tooltip trigger ("Scoping · done"); the whole stepper carries an `aria-label` naming the current stage.

### Stage node and flow (signature)
One node per stage, minimum 58 px tall, 8 px radius, 1.5 px border, 10 px / 8 px padding: a 12.5 px semibold name (two-line clamp) over an 11.5 px muted line (`0 d` for done, `1 d · SLA 30` for current, `SLA 30 d` for upcoming). Done nodes add a 14 px green check; the current node carries the state ring; upcoming nodes are dashed with chrome-text names. Arrows are drawn between nodes at `md`+. The current node's open tasks hang beneath it as a hairline-divided list (checkbox square, title, 20 px assignee avatar, max four then "+n more") with a caption "n open before moving on".

### Time strip (signature)
A 6 px Muted Fill track spans start → target; each visited stage lays a 6 px ink segment over it (amber `warn-line` when the current stage is over SLA or the rollout is overdue), each a tooltip with its duration. Tick labels are 11 px muted ("Sep 7", "target Nov 30"); "today" is 11 px semibold in Accent Blue Text with a 1.5 × 24 px accent marker.

### Tooltip
Ink fill, white 12 px text, 6.4 px radius, 12 px / 6 px padding, 10 px rotated-square arrow, 4 px offset, zero delay; enters with fade + 95% zoom.

### Avatar
Round initials only (no images in use): 24 px in rows and 20 px under tasks with Paper fill and 10 px / 9 px semibold chrome-text initials; 28 px in the nav with Accent Wash fill and accent-text initials. A hairline ring is drawn inside the circle.

## Do's and Don'ts

### Do:
- **Do** keep Accent Blue to selection, the single primary action, focus and the today marker (The One Accent Rule).
- **Do** map rollout state to its triplet exactly: `overdue` → `bad`, `due_soon` and `over_sla` → `warn`, done stages → `ok`; `on_track` gets no colour.
- **Do** pair every state colour with a second channel — the chip text, a visually-hidden label, the check glyph, dashed vs solid borders.
- **Do** use `--primary-text` for accent-coloured text on white.
- **Do** build on the base-nova components with the `render` prop; apply `buttonVariants()` to anchors that navigate to un-ported Jinja pages.
- **Do** keep chrome at 12–13 px, sentence case, weight 500–600, in Chrome Text or Muted Text.
- **Do** use 1 px hairlines for structure and 1.5 px strokes only for flow geometry (nodes, dots, connectors, today marker).
- **Do** convey depth with borders, rings and fill steps (Paper → Muted Fill → Accent Wash).

### Don't:
- **Don't** add box-shadows, gradients, or an off-white page tint; the ground is `#FFFFFF` and surfaces are flat.
- **Don't** uppercase or letter-space labels, or reintroduce the retired identity's dark nav, brand red, Chakra Petch or 2 px corners — those live only in the frozen `static/style.css`.
- **Don't** use green for "on track" rows or amber/red for anything that is not a lateness state; don't use `--destructive` for rollout state.
- **Don't** put a state's text shade in a fill or its line shade under text.
- **Don't** invent tokens: use the `:root` block in `frontend/src/index.css` and its `@theme inline` aliases (`ok-*`, `warn-*`, `bad-*`, `primary-text`, `nav-fg`); there is no `.dark` block and none should be added ad hoc.
- **Don't** render the flow as a kanban board or a numeric table; the stepper and the node row are the read.
