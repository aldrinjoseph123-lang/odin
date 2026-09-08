---
target: the Board
total_score: 17
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-07-28T05-38-17Z
slug: templates-board-html
---
Method: dual-agent (A: design review, isolated · B: detector + browser evidence, isolated)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | No "data as of" timestamp on a screen of day-counting countdowns; nav has no active-page state |
| 2 | Match System / Real World | 2 | Money renders as `210500` — no currency, no separators; vendor status reads "N/A (9)" |
| 3 | User Control and Freedom | 2 | Drag-drop commits a stage change instantly — no undo, no confirm, including onto always-empty "Closed" |
| 4 | Consistency and Standards | 2 | Three unrelated colour encodings on one screen; two `<h1>`s ("Board", "Pipeline") |
| 5 | Error Prevention | 1 | Alert dismiss `×` measures 7×17px, adjacent to the link it destroys; drag-drop has no drop-target feedback |
| 6 | Recognition Rather Than Recall | 2 | Stage bars max-normalised with no axis — counts of 2 vs 3 read as "roughly the same" |
| 7 | Flexibility and Efficiency | 2 | Pre-filtered deep links are a real accelerator, but no sort, no search, and zero keyboard path to any card or row |
| 8 | Aesthetic and Minimalist Design | 1 | Recent Activity is 571px of `df`, `sent`, and "Stage changed to Kickoff" ×3 |
| 9 | Error Recovery | 2 | Countdown pills diagnose well, but nothing on the screen lets you act on late money |
| 10 | Help and Documentation | 1 | All explanation lives in `title=` tooltips — invisible to touch, keyboard and screen readers |
| **Total** | | **17/40** | **Poor — core experience is compromised for keyboard users and for the money task** |

## Design Specificity Verdict

**LLM assessment (unanchored): generic, with one specific instinct buried inside it.**

Swap the words and this composition is the default admin template: alert stack, six KPI tiles, two bar charts, two stacked bars, two tables, activity feed. Nothing in the *layout* knows this is a security integrator earning margin between a client and a subcontractor. The single most product-specific fact in the domain — money in and money out are two independent clocks that can each bite you — is expressed only by duplicating the same widget twice, four times over. Mirroring is not authoring; it is the absence of a decision.

The proof is in the numbers: this is a cash-flow tracker whose numbers are not formatted as money. `{{ '%.0f'|format(...) }}` renders `210500`. No currency, no separator, no unit — across six tiles, two chart values and two table columns. Meanwhile "Net Position 180500" (an accounting abstraction including invoices nobody has paid) sits in a hero tile in green, while the number the team actually acts on — how much cash is *late* — appears nowhere and must be summed by hand across two tables.

The one genuinely authored idea: every aggregate is a pre-filtered link. That's a real Operate-surface instinct wearing a template.

**Deterministic scan.** Detector run over `templates/` + `static/style.css`: 7 findings, all `warning`, zero `error`. Board-relevant: `side-tab` (`style.css:124`, `.note` left accent border — used by Recent Activity on this page) and `layout-transition` (`style.css:229`, `.hbar-fill { transition: width }` — used by the stage and cash-flow bars). `flat-type-hierarchy` and `em-dash-overuse` land in the print reports, not the board.

**False positives:** `single-font` ×3 (Chakra Petch). CLAUDE.md pins the theme — "always use, no exceptions". The brief wins; not a defect.

**Where the two assessments disagreed — and that disagreement is a finding.** The detector agent measured 10 text pairs and reported *all pass WCAG AA*. The design review measured different pairs and found four failures: white on `--status-good #0ca30c` = 3.35:1, white on `.series-blue #2a78d6` = 4.42:1, `.column .count #999` on `#ECECE9` = 2.41:1, and `.hbar-track` against its panel = 1.08:1. Both are correct; the sample differed. Body copy passes comfortably — it is the **data-encoding surfaces** (status segments, stage counts, empty bar tracks) that fail. A contrast sweep that only samples paragraphs will keep declaring this page clean.

**Visual overlays:** none. No overlay was injected, so there is nothing highlighted in a browser tab. Findings above come from CLI scan plus direct DOM measurement.

## Overall Impression

The information architecture is sound and the data model behind it is genuinely well thought out — but the screen spends its attention almost exactly inversely to what matters. The loudest, largest block above the fold is the *stale projects* banner (housekeeping); the quietest fact is how much cash is overdue (existential). Add that the primary task — spot overdue money, open that project — is **impossible with a keyboard**, and this is a dashboard that reads well to one specific user: a mouse-using person who already knows what they're looking for.

Biggest single opportunity: format money as money and surface one number — *total overdue, in and out*. That one change moves heuristics 2, 6 and 9 at once and costs a Jinja filter.

## What's Working

1. **Every aggregate is a filtered navigation target.** Tiles → `projects_list?view=overdue`, bar rows → `?stage=`, legend items and stacked segments → `?client_status=`. The charts aren't decoration, they *are* the filter UI. This is the right instinct for a working tool and is the idea worth building everything else around.

2. **The dismissed/real alert split** (`routes/board.py`). The banner respects per-session dismissals; the OVERDUE ITEMS tile never does. Dismissing hides the nag while the count keeps telling the truth, and dismissals evaporate at next login. That is a system that refuses to let a user lie to themselves — uncommon, and worth protecting through any redesign.

3. **Numeric discipline.** `font-variant-numeric: tabular-nums` applied consistently across `.stat-value`, `.countdown`, `.hbar-value`, `.stacked-seg`. Columns of digits align and scan cleanly. Invisible, precise, on-brief — brand living in details rather than decoration.

## Priority Issues

**[P0] Money is not rendered as money, and the one number that matters is missing.**
- *Why it matters:* six tiles, both amount columns and both cash-flow labels emit `'%.0f'` → `210500`. People misread unseparated six-digit integers, and the aggregate the team actually needs — total overdue in and out — must be summed by hand across two tables 900px apart. A cash-flow tool that renders cash as a bare integer has not been designed for its own domain.
- *Fix:* add one Jinja filter (`{{ v|money }}` → `AED 210,500`), apply to all ten money outputs. Replace the OVERDUE ITEMS *count* tile with **OVERDUE — `AED 75,000` in / `AED 6,000` out**, count demoted to a secondary line, in `--accent`. `.stat-critical` already exists.
- *Suggested command:* `/impeccable clarify`

**[P1] 18 interactive elements are unreachable by keyboard, and no focus style exists anywhere.**
- *Why it matters:* `[onclick]:not(a):not(button)` returns 18 — every project card and every payment-table row. The primary task is keyboard-impossible except via the alert banner, whose links double as the dismiss mechanism. Both assessments independently confirmed there is no visible focus indicator on any link; the only `:focus` rule in the stylesheet (`style.css:62`) *removes* an outline.
- *Fix:* convert card bodies and the first cell of each payment row to real `<a href>` (delete the `onclick`s), then add one global rule, on-brief: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`.
- *Suggested command:* `/impeccable audit`

**[P1] Hierarchy is inverted — the least urgent alert and the least useful panel own the most pixels.**
- *Why it matters:* the stale banner renders 8 inline project links + 8 dismiss carets across 3 wrapped lines above the fold, larger than either genuinely painful banner. Recent Activity is 571px of near-duplicate autogenerated notes. The screen cries loudest about what matters least, which trains people to skim past all three banners.
- *Fix:* collapse the stale banner to one line — `8 projects untouched for 14+ days →` linking to `?view=stale`, no inline links. Cut `recent_notes` to 4, collapse consecutive identical notes, move the panel below the Pipeline. Returns ~600px to the payment tables.
- *Suggested command:* `/impeccable layout`

**[P1] Section chunking is inverted — proximity says the opposite of the meaning.**
- *Why it matters:* measured y-ranges [734–1214][1214–1562][1562–2140]: **0px between sections, 24px within them.** Unrelated panels butt together with doubled 2px seams, so the eye cannot find where "pipeline health" ends and "money" begins.
- *Fix:* `.grid-2 { margin-bottom: 1.5rem; }`, drop the inline margin on Recent Activity, and group the four money panels under one uppercase section rail so the page reads as three chapters rather than eleven boxes.
- *Suggested command:* `/impeccable layout`

**[P2] Charts are quantitatively misleading and encode state by colour alone.**
- *Why it matters:* stage bars use `count / max * 100` with no axis, so 2 vs 3 renders as 66% vs 100% solid black — exaggerating a one-project difference; the empty track is 1.08:1 against the panel, so a zero-count stage is invisible. The stacked segments carry only a bare numeral, with status meaning held purely in fill colour — and white-on-`#0ca30c` (3.35:1) and white-on-`#2a78d6` (4.42:1) both fail AA. Adjacent Paid/Partially-Paid segments differ from each other by 1.27:1, so colour-deficient users lose the distinction entirely.
- *Fix:* scale stage bars against total active projects; give `.hbar-track` a `1px solid var(--border)`; darken `status-good` and `series-blue` past 4.5:1; add `aria-label="Paid: 4 projects"` to each segment.
- *Suggested command:* `/impeccable colorize`

**[P3] Two detector-only findings, both on shared classes this page uses.**
- *Why it matters:* `.note { border-left: 3px solid var(--accent) }` (`style.css:124`) is the single most recognisable AI-generated-UI tell, and it sits on Recent Activity. `.hbar-fill { transition: width }` (`style.css:229`) animates a layout property on the stage and cash-flow bars, causing layout thrash. Neither is covered by the pinned theme — CLAUDE.md fixes colour, font and radius, not side-borders or transition targets.
- *Fix:* drop the left border (or replace with a small `--accent` dot before the meta line); swap to `transform: scaleX()` with `transform-origin: left`.
- *Suggested command:* `/impeccable polish`

## Persona Red Flags

**Alex (impatient power user).** Lands to three red-ish banners, the biggest about *stale* projects. Looks up for the damage: `210500`, `30000`, a green `180500`, and `3` — none of which is "how much am I owed, late". Clicking OVERDUE ITEMS *leaves the board* for a filtered list instead of scrolling to the table already on this page. Clicking Client Invoiced / Vendor Invoiced / Net Position throws him into a print report in a new tab (`target="_blank"`) with no warning. In the payments table he cannot sort by amount, sees no totals, and project names wrap to three lines. Nothing states when the countdowns were computed, so a tab left open overnight silently lies about "1 day left". The actual Pipeline is 1635px down with 484px clipped behind a horizontal scrollbar. And his one write action — dragging a card — has no drop-target highlight, no confirm and no undo; a slip onto "Closed" (a column that is *always* empty, since terminal-stage projects are filtered out of the query) makes the project vanish from the board.

**Sam (keyboard + screen reader + contrast).** **Cannot complete the primary task at all.** All 5 payment rows and all 13 project cards are `onclick` handlers on `<tr>`/`<div>` — not focusable, not activatable, not announced as interactive. The only keyboard route to an overdue project is the alert banner link, which also dismisses the alert as a side effect explained solely in a `title` attribute. No focus indicator is authored anywhere. Screen-reader output of the banner is 11 repetitions of "*project name*, link" followed by "**×**, link" — the dismiss control's entire accessible name is a multiplication sign. Heading structure is 2 `<h1>`, **0 `<h2>`**, 15 `<h3>` — level skips throughout, two top-level headings in one document (independently confirmed by both assessments). Target size: `.alert-dismiss` is 7×17px against a 24×24 WCAG 2.2 minimum; 66 of 72 interactive elements fall under 44×44. Colour-only meaning across four stacked bars and both legends, where `.legend-swatch` is an empty `<span>` with a background colour and nothing to announce.

## Minor Observations

- `.note-meta` uppercases the **author's name** → `ALDRIN JOSEPH`. CLAUDE.md explicitly forbids uppercasing user data — chrome and labels only.
- Note timestamps ship as raw sliced ISO (`2026-07-24 05:01`), in UTC, unlabeled, beside due dates that are local.
- Status colours `#0ca30c`, `#fab219`, `#ec835a`, `#2a78d6` are hardcoded in `style.css:243-259`, outside the `:root` token block — a brief violation independent of the fixed palette. They should become `--status-*` tokens.
- `board.html:75` hardcodes both delivery keys and lines 108-135 hardcode the four status keys, while `DELIVERY_MODES` / `CLIENT_PAYMENT_STATUSES` are data-driven constants. Add a status and the bars silently under-report without erroring.
- Delivery Mode and Cash Flow share one panel under two `h3`s while Client and Vendor status each get their own — arbitrary partitioning of equal-weight content.
- `.alert-item { white-space: nowrap }` is what produces the ragged 3-line stale banner.
- The good-news empty state ("No pending client payments.") is styled identically to a data row, so "you're all paid up" reads as a missing record.
- `main { max-width: 1200px }` leaves 240px of dead margin at 1440px while the Pipeline below clips 484px horizontally.
- Mobile: at 375px the document scrolls to 663px — the two payment tables force 288px of horizontal overflow.
- Tab title, nav item and `h1` all say "Board"; a second `h1` on the same page says "Pipeline".

## Questions to Consider

1. **If this screen could show exactly one number, would it be "Net Position 180500"?** That figure counts invoices nobody has paid. The number this team lives on is "you are owed X, of which Y is late, and you owe Z." Why is the accounting identity in a green hero tile while collectible cash must be summed by hand from two tables 900px apart?

2. **The page is called Board, but the board is the last thing on it and 30% of it is off-screen.** Is this a board with a dashboard bolted on, or a dashboard that should ship at `/dashboard` and give `/board` back to the kanban? Deciding that removes about half the issues above for free.

3. **You already built the right primitive and hid it in the banner.** The dismissal model captures "I've seen this" without changing the truth. What if that became the whole screen — a worklist of "3 things to chase today", each row carrying amount, days late, client, and snooze-until — and the six tiles collapsed into a single cash strip above it? What is actually lost, besides charts nobody has made a decision from?
