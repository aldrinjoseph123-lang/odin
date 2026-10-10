---
target: whole app
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 4
timestamp: 2026-10-10T11-20-04Z
slug: frontend-src-pages
---
Method: five agents, as on the first whole-app run (A1 core, A2 secondary, A3 admin and entry; B detector, clean overlay and font probe; B2 code inventory).

| Group | Before | Now |
|---|---|---|
| A1 core work | 27 | 27 |
| A2 secondary | 28 | 28 |
| A3 admin and entry | 24 | 28 |
| **Whole app (mean)** | **26** | **28 (Good)** |

Fonts: Inter and Chakra Petch load from Odin itself on every page (error page and framed map included), nothing from Google, no CSP errors; sizes on the six-size scale. Gaps: "→" (27 uses) and ⌘ ⅓ ⅔ ⋯ fall outside the latin subset; the frozen guest stylesheet sets body text in Chakra Petch.

Priority issues:
- [P1] One state, one wording, one glyph (four wordings of one rollout's state; Stepper shrinks to dots at 96 px; RAG words vs flow words)
- [P1] --bad still used for ~14 errors and destructive actions (incl. failure toasts); Cycle time colours numbers with no words
- [P1] Settings frame and Save model (three header patterns; Saves enabled before any change; one card with three filled Saves)
- [P1] Native fields: 35 hand copies; textareas cannot use field (fixed h-8)
- [P2] 31 hand-written section labels; 8 segmented controls; 33 pill-shaped Buttons; Delete in 7 looks
- [P2] Flow view switcher jumps; project form tidy; My work stepper tooltip shows numbers (bug)
- [P2] Print: portfolio clips on A4, sign-off prints its send panel
- [P3] Guest page "PO PO-…"; system map opens scrolled; off switch thumb; dates built by hand in 8 places
