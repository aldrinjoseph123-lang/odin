---
target: Dashboard page
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
timestamp: 2026-10-10T09-00-18Z
slug: frontend-src-pages-dashboard-tsx
---
Method: dual-agent (A: design review · B: detector + browser overlay)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Save notice and Undo render only at the page top |
| 2 | Match system / real world | 3 | "stage steps", "32% of stages done", Idle without threshold |
| 3 | User control and freedom | 3 | Undo exists but often off-screen |
| 4 | Consistency and standards | 2 | Four row-open patterns; tile dialog alphabetical, not worst-first |
| 5 | Error prevention | 3 | Remove is instant but undoable |
| 6 | Recognition rather than recall | 3 | Timeline bar encoding has no legend |
| 7 | Flexibility and efficiency | 2 | 103 tab stops, no page keys, tile → dialog → flow |
| 8 | Aesthetic and minimalist | 2 | Same overdue rollouts in ~7 widgets; stretched empty cards |
| 9 | Error recovery | 3 | One failed fetch blanks the page |
| 10 | Help and documentation | 2 | Nothing explains slipping, Idle, bar encoding |
| **Total** | | **26/40** | Acceptable (was 25) |

Specificity: half authored (Needs attention, stage flow, drill-downs); the rest generic SaaS dashboard. Detector: CLI clean; overlay 26, real: 11 px reason chips, ~210-char cycle-time line.

Priority issues:
- [P1] Fold repeats the same overdue rollouts twice; counts start below the fold (distill, layout)
- [P1] Timeline bars don't show lateness; red fill encodes progress; no legend (clarify)
- [P1] Save feedback/Undo at page top, not a toast (harden)
- [P2] Stretched cards, filler widgets, repetitive activity feed (layout)
- [P2] Tile dialog not worst-first; Schedule "Open" pills; tiles don't link to the filtered flow (polish)

Personas: Alex 103 tab stops, no keys; Sam KPI aria-label drops the delta, reason pills outside the link name, live reload unannounced.
