# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary: the owner / delivery lead** (the person who commissioned Odin). Opens it daily to answer one question first: *where is every deployment right now, and what is stuck?* Self-described "visual" — wants to see state, not read it. Then drills into one customer's rollout.
- **Delivery / project managers (Member role):** run each rollout day to day — move stages, tick tasks, upload deliverables, write status notes.
- **Sales / account managers (Contributor role):** create a project from a customer PO, watch progress, comment; never move a delivery stage.
- **Viewers:** read-only staff.
- **External participants (contractors, resellers, customer contacts):** invited to a project by email, sign in with a one-time link (no password), see only the projects they are on, read and comment, tick tasks tagged to them. A customer contact may also approve or decline each stage change when the project asks for it.
- **Customers / vendors via the older per-project guest links** (view-and-comment, or advance one step): still live until invited accounts replace them.

## Product Purpose

Odin tracks the delivery lifecycle of every cybersecurity product and service the company sells — from purchase order through scoping, kickoff, deployment, tuning/UAT and hypercare to closed — for a security company running many rollouts in parallel. Success: nothing stalls unnoticed; the team, the customer and the vendor all see the same state of a rollout; the audit trail proves who did what.

Deliberately **not** a billing or commercial tool: invoices, payments and margins were removed and live elsewhere.

## Positioning

One shared pipeline for internal team, customer and vendor, with **stage SLAs measured from history** (time-in-stage reconstructed from status notes, targets set by hand or from measured averages), **per-party guest links** with different powers, and an **append-only audit trail** built for ISO 27001 / SOC 2 evidence. Generic project tools do not know what a security-product rollout is; Odin's stages, gates and parties are that rollout.

## Operating Context

- Internal Docker deployment on Proxmox, published through Cloudflare Tunnel + Access (MFA via Entra ID); guest links bypass Access.
- A rollout is created from a **client PO document** (required). Each has a client, vendor, product, delivery mode (Distribution/MSSP or Outsourced), owner, target end date, tasks with assignees and due dates, uploaded deliverables, status notes (some guest-visible), and two guest links.
- Stages are configurable per install; default lifecycle: PO Received → Scoping → Kickoff → Deployment → Tuning/UAT → Hypercare → Closed. The last stage is terminal everywhere.
- Alerts: overdue (past target end), due soon, stage-SLA breach, stale (untouched). Board banner shows them; a daily digest goes to admins; Teams/email via Microsoft 365 when connected.
- Rituals: daily glance at the portfolio; moving a card when a milestone lands; sending a guest link to a customer/vendor; quarterly access review from the users export; nightly backup.
- Scale: dozens to a few hundred active rollouts; a team of roughly 20–50.

## Capabilities and Constraints

- Stack: Flask + SQLite JSON API; React + TypeScript + shadcn/ui front end (Vite, Tailwind 4) migrating page by page from Jinja (strangler). Login and Board are React today; projects list, project detail, settings, users, audit log, guest pages are still Jinja.
- Roles/permissions matrix (Admin, Member, Contributor, Viewer, External) enforced server-side; the UI must reflect them (Viewers and Externals see, never move). Per project, every participant also has a project role (Project manager = owner, Sales, Coordinator, Contractor, Reseller, Customer), and it binds staff too: only the Project manager moves stages, edits the project, its stage list, team, report and guest links; a Coordinator runs tasks and documents; everyone else on or off the project reads, comments, and ticks tasks tagged to them; a Customer contact approves stage changes. Admins bypass the project role.
- Every project owns its stage list: copied from a template in Settings at creation, then editable per project (add, rename, reorder, delete, SLAs). There is no shared stage header; each row carries its stage by name.
- Tasks belong to a stage of their project and are worked from the flow screen: add with an assignee from the project team, tick, delete. The person a task is tagged to may tick it whatever their role.
- Reports: a draft is built from the stage timeline, tasks, notes and documents; the project manager edits it as plain text and saves numbered versions. Partners and customers see saved versions only.
- Notifications: a stage change emails every participant with an address (actor excluded), plus the owner and Teams. The project manager is also emailed when anyone else adds a note, finishes a task or uploads a document on their project; an approval decision reaches every participant. Every mail links to the project, an external account through a fresh one-time sign-in link. The project page also shows an Activity feed (the audit trail's own rows for that project, staff only) for people who do not read their email. Optional per project: the customer contact is asked to approve each stage change; the stage still moves, the decision is recorded, noted and audited.
- Guest pages are public-internet surfaces: no internal navigation, no internal notes, no PO number on the vendor link, author name required on every write.
- Drag-and-drop stage changes exist and are audited; vendor may advance one step only, never to terminal.
- All stored timestamps are UTC; rendered in the reader's zone.
- Terminology: *project* = one rollout; *stage*; *task*; *deliverable*; *guest link* (customer / vendor); *SLA* = expected days in a stage.
- **Undecided:** whether time-on-axis (Gantt-style planned vs actual) becomes a first-class view or a detail-page section; how "gates" (required task/document before a stage change) are enforced — today they are not.

## Brand Commitments

- Name: **Odin**. Never rebranded as the company.
- The user has **released the previous visual identity** (dark nav, brand red #E11D2E, Chakra Petch, 2 px corners) for this rework: the whole look may be replaced. Nothing else is pinned.
- Voice (existing, keep): plain, specific, active; controls say exactly what happens; errors say what went wrong and how to fix it. No hype.
- **Standing visual preference (8 Sep 2026):** convention played straight — a light, clean, modern, *direct* flowchart UI (boxes, arrows, states; no metaphor, no story). Craft bar: **Linear** and **Whimsical / FigJam**. Explicitly rejected: dark/industrial worlds, metaphorical worlds (trains, plants, courses), Jira/Monday/Asana-style SaaS boards, gamification, and number-dense tables.
- First screen: **portfolio flow above, the selected rollout's own flowchart below, equal weight.**

## Evidence on Hand

- Real data: a production database with 14 rollouts and 5 users; a seeded UAT dataset (32 rollouts) at the scratch path used for testing.
- `docs/UAT_SCRIPT.md`, `docs/UAT_RESULTS_2026-09-08.md`, the independent audit report (artifact) — real behaviour, real findings.
- No logo asset exists beyond the wordmark "Odin". No customer testimonials, no screenshots for marketing; none must be invented.
- Real vendor/product names in the data are the company's actual suppliers (e.g. CrowdStrike / Falcon Complete in test data).

## Product Principles

1. **State before text.** The first screen shows where every rollout is and what is stuck, without reading a table.
2. **One pipeline, three audiences.** Team, customer and vendor look at the same flow with different powers; the UI never shows a party more than it may do.
3. **Time is a first-class fact.** How long a stage has taken, against its SLA, is always visible where the stage is.
4. **Every move is evidence.** Anything that changes a rollout is attributed, audited, and reversible where the product allows.
5. **Density serves scanning.** Hundreds of rollouts must stay legible; cap, cluster and summarise rather than list.

## Accessibility & Inclusion

WCAG 2.1 AA is the working floor (contrast verified across pages in the last audit; every control labelled; keyboard-reachable rows). Colour never carries state alone — stage/SLA state needs a second channel (shape, label, position).
