---
target: Flow page
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
timestamp: 2026-10-10T08-10-49Z
slug: frontend-src-pages-flow-tsx
---
Method: dual-agent (A: design review · B: detector + browser overlay)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Selecting a row announces nothing; timeline paints overdue amber |
| 2 | Match system / real world | 3 | "No open task · 3 of 3 done" when the step is "ready to advance" |
| 3 | User control and freedom | 3 | 5-min undo, Esc; Cancel drops focus to body |
| 4 | Consistency and standards | 2 | Overdue red on rows, amber on timeline; red accent on selection/links/primary |
| 5 | Error prevention | 2 | "Move to X now" lands under the cursor, autofocused: double-click commits |
| 6 | Recognition rather than recall | 2 | 12 unlabelled progress columns |
| 7 | Flexibility and efficiency | 3 | j/k, ⌘K; j/k doesn't load detail; no action keys |
| 8 | Aesthetic and minimalist | 3 | Calm; client name and open-task counts repeated |
| 9 | Error recovery | 3 | Inline role=alert with server message, undo |
| 10 | Help and documentation | 2 | No legend for progress, j/k never hinted |
| **Total** | | **26/40** | Acceptable |

Specificity: detail pane is authored (flowchart, SLA on nodes, folded done); list is generic issue-list. Detector: CLI clean; overlay 16–21, all false positives except the list panel's flush bottom padding.

Priority issues:
- [P1] Selected row wash #FFF0F2 ≈ overdue chip fill; links and Advance red beside lateness (colorize)
- [P1] Advance confirm double-click / Enter-Enter commits (harden)
- [P2] Rail order hides the next move below the fold; "Next up" only knows tasks (layout, clarify)
- [P2] Progress columns unreadable without labels (distill)
- [P2] Tasks in ~120 px columns, folding goes too far, first paint overflows (layout)

Personas: Alex j/k + Enter per rollout, 29 tab stops before first row; Sam no focus/announce on select, Advance panel has no heading, 6 "+ Task" stops incl. Closed.
