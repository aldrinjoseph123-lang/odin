---
target: whole app
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 4
timestamp: 2026-10-10T10-33-04Z
slug: frontend-src-pages
---
Method: five agents. Design review in three page groups (A1 core, A2 secondary, A3 admin and entry); B detector and overlay plus a font probe; B2 code consistency inventory.

| Group | Score |
|---|---|
| A1 core work (Dashboard, Flow, Projects, Project, forms, My work) | 27/40 |
| A2 secondary (People, Alerts, Cycle time, reports, Sign-off, Account) | 28/40 |
| A3 admin and entry (Settings, Users, RBAC, Contacts, Audit, sign-in, error, guest) | 24/40 |
| **Whole app (mean)** | **26/40** |

Weakest heuristic everywhere: 4 Consistency and standards (2/4 in every group).

Fonts: Inter and Chakra Petch load on every app page under the real CSP (production sends the same Flask header); six sizes hold in pages. Defects: error page never loads Inter; dialog titles 16 px Inter (off-scale); font-mono on ordinary fields (holidays).

Priority issues:
- [P1] Colour: overdue red on baseline slip, errors and destructive actions; accent as chart colour (People, Person, Time on Odin, reports, My work); green "On track" pill
- [P1] Projects page hides lateness and keeps the old dot stepper (also My work)
- [P1] Dates: timeAgo and localDateTime follow the browser locale ("Sep 24" beside "24 Sep")
- [P1] Settings feedback off-screen; four Save styles; two on/off controls
- [P2] One component per job: fields (6 class copies), pills (7), toggle chips (9), state chips (6), stat tiles (5), panel labels (3 sizes, data-n on 23/67), empty states (3 kinds), notices (8 bars), page headers (17 vs 24 px h1)
- [P2] Off-state switch about 1.4:1; outline buttons have no visible edge in light
- [P2] Wording: Advance/Move, rollout/project, Delete/Remove
- [P3] Audit names split mid-word; guest page red current stage and no byline; truncation with no title (55)
