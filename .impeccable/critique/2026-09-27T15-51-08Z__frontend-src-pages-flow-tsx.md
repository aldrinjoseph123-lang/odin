---
target: Flow first screen
total_score: 21
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
timestamp: 2026-09-27T15-51-08Z
slug: frontend-src-pages-flow-tsx
---
Method: dual-agent (A: design review · B: detector + browser)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|---|---|---|
| 1 | Visibility of System Status | 3 | Overdue task shows neutral in Next up; time strip draws no over-SLA bar when start_date is after the stage began |
| 2 | Match System / Real World | 3 | Rollout/stage/SLA language fits; ten bare "0 d" rows say little |
| 3 | User Control and Freedom | 1 | Advance has no undo or confirm; no way to close the lower pane; filter not kept |
| 4 | Consistency and Standards | 2 | Rose/amber accents paint selection and primary actions in state hues |
| 5 | Error Prevention | 1 | One-click Advance with open tasks and a pending approval; caveat sits far from the button |
| 6 | Recognition Rather Than Recall | 2 | Stepper dot count varies per project; due dates only in title tooltips |
| 7 | Flexibility and Efficiency | 2 | Cmd-K and deep links good; no j/k rows, no Esc, every row a tab stop |
| 8 | Aesthetic and Minimalist Design | 3 | Calm and flat; "+ Task" under every stage, repeated client name |
| 9 | Error Recovery | 2 | Same error announced twice (role=alert ×2) |
| 10 | Help and Documentation | 2 | Good empty states; no legend for rings/dots or SLA |
| **Total** | | **21/40** | **Acceptable** |

## Design Specificity Verdict
LLM: the diagram (per-row stepper, node-and-arrow flowchart, "9 d · SLA 5", honest "open before moving on") is authored for Odin; the chrome around it (nav, pill filters, inputs) is category-standard.
Deterministic: CLI scan clean (0). Browser detector: undersized 10 px avatar initials (real, minor); thin border + wide shadow on the closed palette dialog (style call); overused-font and flat-type-hierarchy (page-wide notes, Inter and the tight ramp are deliberate); clipped-overflow on the resizable group (false positive, sr-only spans). Contrast: 0 failures across light/dark and six accents (lowest 4.52:1, search placeholder). No horizontal scroll at 375 px.

## Priority Issues
- [P1] Advance is a one-click, mass-notifying move with no confirm step and no undo; open tasks, pending approval and who gets notified are not shown at the button (Flow.tsx:335-341). Fix: consequences in the Advance section + in-place confirm. Command: harden.
- [P1] Rose and amber accents collide with state colours (red = overdue, amber = warning). Fix: replace them with non-state hues. Command: colorize.
- [P2] Flowchart doesn't fit ~1050 px laptops: 280 px rail from lg; nodes clipped behind a sideways scroll. Fix: rail stacks under the flow below xl. Command: adapt.
- [P2] Keyboard/screen reader: every row a tab stop, no arrow/j-k movement, faint focus ring, run-on accessible names, unlabeled split handle, Esc does nothing. Command: harden.
- [P2] Overdue tasks invisible; Next up = first task in API order. Fix: sort current stage then due date; inline due dates with "n d late". Command: clarify.

## Persona Red Flags
Alex: no j/k, no Esc, filter lost on reload. Sam: duplicate alerts, 14 px checkboxes, run-on row names, dots and strip segments unreachable by keyboard. Delivery lead: dot columns don't line up across rows; time strip blank for an over-SLA rollout.

## Minor Observations
Time strip range should start at the earliest stage entry; hover-only delete never shows on touch; filter chip names read "All15"; 9-10 px avatar initials.

## Questions to Consider
Is the stepper a progress bar or a map? Should the loudest thing in the pane be what blocks the advance? At 300 rollouts, is a flat list still "state before text"?
