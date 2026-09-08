# Surface: Flow (first screen, /board)

Mode: Operate. Visitor: the delivery lead opening Odin daily; then PMs and sales working from it.

Job: answer "where is every rollout, what is stuck, what do I do next" without reading a table, then act on one rollout.

Direction (approved 8 Sep 2026, convention played straight; craft bar Linear + FigJam):
- Light, direct flowchart world. Inter. One accent for selection/primary action; colour otherwise only for state (ok / over-SLA amber / overdue red).
- Composition: a **resizable vertical split**. Top pane: every active rollout as one compact row — name, client, a 7-dot progress stepper (done dots filled, current ringed and coloured by state), days in stage, owner; stuck rows first. Bottom pane (expands on selection): the selected rollout's flowchart — stages as connected nodes, done/current/next, dwell time per node; under the current node its open tasks with assignee and due date; the next actionable item and ETA (target end) called out; a time strip beneath with planned span, actual progress and today.
- Memorable moment: dragging the divider up so the flowchart owns the screen; the stepper on the selected row and the flowchart node highlight together.

Constraints: no gamification; no number-dense tables; Viewers see everything, move nothing; the stage change from this screen goes through the existing audited API. "Gate" language stays honest: the product does not enforce gates today, so the panel shows "open before moving on: N tasks", never a lock.

Unresolved: whether "Projects" is renamed "Rollouts" across the product (kept "Projects" until decided); Gantt planned-vs-actual beyond the single time strip.

Approved comp: .impeccable/mocks/comp-b.png (list) + the flowchart panel common to all comps. Do not literalize: the fake "Gate: signed scope document missing" (not a product capability), the mock avatar initials colours.

Implementation fidelity inventory:
| Ingredient | Medium |
|---|---|
| Rollout rows + stepper | semantic HTML + CSS (shadcn Tooltip for stage names) |
| Resizable split | react-resizable-panels (shadcn Resizable) |
| Flowchart nodes + arrows | HTML/CSS (arrows as CSS pseudo-elements), no raster |
| Time strip | HTML/CSS bars from real dates |
| Avatars | initials, single neutral style |
| Icons | lucide-react (already installed) |
| Imagery | none — accepted omission (Operate surface) |

## Seed record

Direction rolls: 8533f9f4 (assigned 3, Signaller's Panel, re-rolled) and f1e2be4e (assigned 4, Control-Room HMI, re-rolled); the user then took the canon exit. Approved comp: .impeccable/mocks/comp-b.png. Screenshots: .impeccable/shots/flow-desktop.png, flow-mobile.png.
