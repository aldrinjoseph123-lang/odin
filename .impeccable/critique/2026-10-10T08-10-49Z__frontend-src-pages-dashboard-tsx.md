---
target: Dashboard page
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 4
timestamp: 2026-10-10T08-10-49Z
slug: frontend-src-pages-dashboard-tsx
---
Method: dual-agent (A: design review · B: detector + browser overlay)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Live dot good; silent 15 s reloads; deltas don't say "vs a week ago" |
| 2 | Match system / real world | 3 | "32% of stages done" abstract; Schedule day tiles lack month |
| 3 | User control and freedom | 3 | Undo on every layout change, but far from the widget |
| 4 | Consistency and standards | 2 | Accent text #B4143C ≈ overdue #B4231C; "late" counted three ways |
| 5 | Error prevention | 3 | Remove has Undo |
| 6 | Recognition rather than recall | 2 | Timeline names cut at ~12 chars; stage only on hover |
| 7 | Flexibility and efficiency | 2 | No page keys; timeline rows 2 tab stops each |
| 8 | Aesthetic and minimalist | 2 | 11 equal-weight widgets; rose sparkline on every tile; stretched cards |
| 9 | Error recovery | 3 | Rollback + message (two sentences run together, Dashboard.tsx:691) |
| 10 | Help and documentation | 2 | Nothing defines Idle / Over SLA / Due soon |
| **Total** | | **25/40** | Acceptable |

Specificity: generic SaaS dashboard (TaskFlux reference); only the Timeline and Schedule's approvals are Odin's own. Detector: CLI clean; overlay 36, all false positives except 3 Schedule truncations without a full-text title.

Priority issues:
- [P1] Charts and sparklines drawn in accent red that matches overdue red (colorize)
- [P1] "What is stuck" not first; Open alerts in row 3; four disagreeing "late" counts (distill)
- [P1] Timeline label column 96–176 px truncates names; no stage; amber rows have no word (layout)
- [P2] "Rollouts per stage" is a donut for an ordered pipeline; draw stage nodes (shape)
- [P2] Three Recharts SVGs are unnamed role=application tab stops (harden)

Personas: Alex no page keys, 24 tab stops through the timeline; Sam unnamed SVG tab stops, silent reload, dialog title read twice.
