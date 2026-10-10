---
target: Flow page
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
timestamp: 2026-10-10T09-00-18Z
slug: frontend-src-pages-flow-tsx
---
Method: dual-agent (A: design review · B: detector + browser overlay)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Board never refreshes; on-track rows hide late tasks |
| 2 | Match system / real world | 3 | Bare "—" on upcoming nodes |
| 3 | User control and freedom | 3 | Esc on Advance closes the rollout, focus to body |
| 4 | Consistency and standards | 2 | Move / Advance / Move with wording; selected row vs DESIGN.md; decline uses window.confirm |
| 5 | Error prevention | 3 | Task delete has no confirm and no Undo |
| 6 | Recognition rather than recall | 3 | Stepper segments unlabelled; folded nodes truncate |
| 7 | Flexibility and efficiency | 3 | 20 tab stops row → Advance |
| 8 | Aesthetic and minimalist | 3 | Next task said 3×; four red marks per overdue row |
| 9 | Error recovery | 3 | Empty filter has no clear action |
| 10 | Help and documentation | 2 | No shortcut sheet; nothing explains the colours |
| **Total** | | **28/40** | Good (was 26) |

Specificity: authored for this product. Detector: CLI clean; overlay 17, real: 11 px key hint; list pane flush bottom (borderline).

Priority issues:
- [P1] "On track" rows hide late next tasks inside the fold (clarify, harden)
- [P2] Rail leads with Advance while work is open; next task repeated (distill)
- [P2] Time strip doesn't draw the target (clarify)
- [P2] Keyboard path into the detail; Esc drops focus (harden)
- [P3] Flowchart noise: "—" nodes, + Task ×4, sign-off said 3× (quieter)
