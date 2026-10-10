---
target: Project page
total_score: 24
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 4
timestamp: 2026-10-10T08-10-49Z
slug: frontend-src-pages-project-tsx
---
Method: dual-agent (A: design review · B: detector + browser overlay)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Health (RAG) below the fold; hero chip and RAG use two vocabularies |
| 2 | Match system / real world | 3 | "client=Globex", "Hit them:" leak internal words |
| 3 | User control and freedom | 2 | Remove member, rotate links, delete doc: bare window.confirm, no undo |
| 4 | Consistency and standards | 2 | Accent "now" ≈ Slip "late"; rose focus ring looks invalid; numbering order |
| 5 | Error prevention | 3 | Re-baseline needs why; Delete project next to Rotate links |
| 6 | Recognition rather than recall | 2 | No section index on a ~4,300 px page |
| 7 | Flexibility and efficiency | 1 | Note box at tab 93, upload at 154; no page keys |
| 8 | Aesthetic and minimalist | 2 | Team and Recent notes twice; stage editor always open; 8/9 Slip cells red |
| 9 | Error recovery | 3 | Clear load errors; sticky notice |
| 10 | Help and documentation | 3 | Useful hints, a little long |
| **Total** | | **24/40** | Acceptable |

Specificity: top half authored (flowchart, advance rail, plan Gantt, Lessons); below is a generic admin stack. Detector: CLI clean; overlay 25, mostly false positives; real: h1 → h3 skipped heading, 11 px plan dates, two ~110-char help lines.

Priority issues:
- [P1] Red spent on slip, accent "now", links, focus ring: red stops meaning overdue (colorize)
- [P1] Health below the fold and worded differently from the hero (clarify)
- [P1] Long page, no section index, Team and notes duplicated (distill, layout)
- [P2] Rare configuration always open: stage editor, invites, Delete project (distill)
- [P2] window.confirm for destructive and trust actions (harden)

Personas: Alex 93 tabs to the note box, Lessons files everything as a risk; Sam no focus ring on "Choose files", h1→h3, invisible note Edit/Delete until focus.
