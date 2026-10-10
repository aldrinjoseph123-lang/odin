---
target: Project page
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
timestamp: 2026-10-10T09-00-18Z
slug: frontend-src-pages-project-tsx
---
Method: dual-agent (A: design review · B: detector + browser overlay)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Sticky reply bar doesn't stick: replies land far above the action |
| 2 | Match system / real world | 3 | "Fill the gaps from SLAs" jargon |
| 3 | User control and freedom | 3 | RAID delete has no undo |
| 4 | Consistency and standards | 2 | Three confirm idioms; Lessons unnumbered; health said twice |
| 5 | Error prevention | 3 | Re-baseline needs a reason |
| 6 | Recognition rather than recall | 3 | Section index scrolls away |
| 7 | Flexibility and efficiency | 2 | 63 tabs to the note box, 18 date pickers in the path |
| 8 | Aesthetic and minimalist | 2 | ~3,600 px; facts repeated 2–3× |
| 9 | Error recovery | 3 | Good load/dialog errors |
| 10 | Help and documentation | 3 | Panel hints, dialog descriptions |
| **Total** | | **26/40** | Acceptable (was 24) |

Specificity: top authored, bottom generic record. Detector: CLI clean; overlay 16, all false positives.

Priority issues:
- [P1] Section index and reply bar never stick: the wrapper doesn't scroll, the window does (harden)
- [P1] Slip column all red on a forecast miss, incl. finished stages, against an amber verdict (colorize)
- [P2] Health, SLA lateness, name stated 2–3× (distill)
- [P2] Notes buried; plan always in edit mode; Lessons always open (layout)
- [P3] Lessons and RAID delete off-system (harden)
