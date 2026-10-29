# Odin lifecycle simulation, 28–29 Oct 2026

Three cybersecurity rollouts lived for 30 virtual days by agents playing every person on their team, beside a permissions prober, a race prober and three load agents on a 150-rollout portfolio, then an improvement advisor and a senior merge. Code was read-only throughout; this report is the only change. Plan: `~/.claude/plans/purrfect-waddling-squirrel.md` (28 Oct); harness in the session scratchpad (`sim/`: `sim_api.py`, `sim_clock.py`, `sim_time.py`, `sim_load.py`, `sim_race.py`, `sim_timing.py`, `clock_loop.sh`, the agents' reports and 270 screenshots).

## How it ran, and what to read with care

- **The lockstep clock broke.** All eight agents stalled for about four hours right after launch (the host's agents, not Odin). The shared clock loop advanced through every round with nobody done, so each director replayed its 30 days on a private seeded copy (ports 5114–5117) with the same time machine, day by day. Day 1 of each story ran on the shared instance; the rest did not run concurrently. The concurrency probes (A5) ran on the shared instance as designed, with 12 writers and 5 readers at once.
- **The RBAC prober changed the shared instance** (an empty role-matrix post switched off 79 of 85 grants for two minutes; director R1 restored the defaults). That accident is itself finding 2.
- **Harness defects, not Odin's:** the sign-in-by-link client lacked the CSRF token at first (fixed); modules imported after the clock patch stamped real time, so bell timestamps on the replicas are real-clock; the load seed wrote text into a number field, which made the portfolio report answer 500 on instance B (that behaviour is finding 25, reachable only through bad data).
- **Mail and AI were off.** "Who was told" means the bell table; the outbox stayed empty except where a prober turned email on.

Every P0–P2 below was reproduced by its agent and re-checked by the senior against the code; the status says which. Counts across the 8 reports: CONFIRMED 70, SUSPECTED 16, UX lines 62 (before de-duplication; the lists below are merged).

## The ten worst

| # | Sev | Where | What | Status |
|---|---|---|---|---|
| 1 | **P1** | `routes/api.py:1491` | **Search shows internal task titles to externals.** The palette's task query carries only the project scope; the Flow adds `t.assignee_id = me` for externals (`:1098`), the search does not. A customer searching a word gets internal task titles of their rollout. | CONFIRMED (A4, senior read) |
| 2 | P2 | `routes/settings.py:215-245` | **A partial role-matrix post wipes every unlisted grant**, Admin's create/edit/delete included (absent checkbox = off). One API call or a trimmed form darkens the workspace; no count, no confirm. Admin keeps settings, users and view rights, so it is recoverable. | CONFIRMED (A4, R1, senior read) |
| 3 | P2 | `services/signoff.py:212` | **The sign-off draft's "Outstanding items" lists every open task, internal ones included**, and sending freezes them into the document the customer signs. PRODUCT: outsiders never see an internal task. | CONFIRMED (R2, senior read) |
| 4 | P2 | `services/report_data.py:164-176, 236-251`; `routes/api.py:~883` | **The customer cut carries the team, dwell-vs-SLA and late counts** ("Tasks 11/19, 6 late", "PO Received 2 d · SLA 1"). PRODUCT: the customer copy has no people, slip or reasons. | CONFIRMED (R3, A4) |
| 5 | P2 | `routes/guest.py:71` | **The outsourcer's name reaches the customer and reseller** through vendor-link note and move authors ("Karim · SecOps Partners LLC (vendor link)"), while the API hides `outsourcer_name` from externals. | CONFIRMED (R2, senior read) |
| 6 | P2 | `routes/projects.py:1231` + `services/intake.py:221` | **Undoing a discarded CRM intake after the CRM re-sent the deal leaves two pending rollouts with one deal id**; `find()` ignores deleted rows and the index is not unique. | CONFIRMED (R3, senior read) |
| 7 | P2 | `routes/projects.py:622-640`; `routes/signoff.py:262-266` | **Half-applied writes after the commit.** A stage move whose notice/outbox step fails answers 500 although it moved (retry → 409, rule never ran, 1 of 4 mails queued); a sign-off reject whose RAID insert fails leaves a rejected version with no issue, no audit row, no notice. | CONFIRMED by failure injection (A5) |
| 8 | P2 | `services/rules.py:536-562` | **The rules scan re-examines every unmatched overdue task every quarter hour, forever**: with one narrowly conditioned rule, 360 `fire()` calls and 821 rolled-back inserts per pass at 150 rollouts (3.2k statements; 16k at 750). And `SCAN_MAX` counts runs, so 300 overdue tasks take four passes (an hour) to reach the PM after a long weekend. | CONFIRMED (B3) |
| 9 | P2 | `backup.py:212-250`; `services/weekly_report.py:152`; `services/outbox.py:59-97` | **Three jobs block the single clock thread:** a 2 GB backup took 66 s and stalled a writer 2 s; the weekly report mails inline (40 staff ≈ 12–25 s, no retry on a failed address, never the outbox); the outbox drains one row at a time with a 15 s timeout, so a hung Microsoft turns a 500-row digest into two hours and a stage-move mail waits behind it. | CONFIRMED (B3; mail latency modelled) |
| 10 | P2 | `services/dashboard.py:192`; `frontend/src/pages/Flow.tsx:838-842`; `frontend/src/App.tsx:100,124-130` | **Polling waste:** every open dashboard rebuilds (180 KB) after any audited action including sign-ins, report views and theme changes (30% of audit rows); every window focus reloads the Flow in full with no minimum gap (Gantt 399 KB + calendar with it); every lazy page waits ~300 ms after its chunk before its first data request. 40 staff on the home page ≈ 160 rebuilds and 29 MB a minute. | CONFIRMED (B2) |

Nothing P0. No leak of the PO, internal notes or internal RAID through any route but #1; 1,308 cross-rollout requests per pass all refused; CSRF held everywhere; the sign-off gate never opened on a superseded version; two stage moves, two confirms, two approvals, two drains never doubled.

## All findings by area

Severity · where · what · status. Agents in brackets.

### Access and the outsider's cut
- P1 · `routes/api.py:1491` · search leaks internal task titles to externals · CONFIRMED [A4]
- P2 · `routes/settings.py:215-245` · partial RBAC post wipes grants · CONFIRMED [A4, R1]
- P2 · `services/signoff.py:212` · internal tasks in the customer's sign-off draft and signed document · CONFIRMED [R2]
- P2 · `services/report_data.py`, `routes/api.py:~883` · customer cut shows team, dwell vs SLA, late counts, stage SLA on the rollout page · CONFIRMED [R3, A4]
- P2 · `routes/guest.py:71`, `routes/projects.py:554` · outsourcer name in guest note/move authors · CONFIRMED [R2]
- P3 · `routes/projects.py:1529-1545` · an invited partner can still tick tasks on a Closed rollout; the guest links refuse (`routes/guest.py:79`) · CONFIRMED [R2]
- P3 · `routes/auth.py:346` · opening a fresh sign-in link in a staff session replaces it with the external's, no sign-out · CONFIRMED [A4]
- P3 · `frontend/src/pages/Projects.tsx` · a customer opening `?view=pending` fires `/api/intake/pending` → 403 console error · CONFIRMED [R3]
- P3 · `services/asks.py:231-236` · the outside-party write limit (10/min) throttles a partner ticking their own tasks (429 on the 11th) · CONFIRMED [R2]

### Lifecycle logic
- P2 · `routes/projects.py:1231` + `services/intake.py:221` · duplicate pending deal after undo of a discard · CONFIRMED [R3]
- P2 · `routes/projects.py:954` · deleting a closed, signed-off rollout asks no reason, tells nobody, and the nightly purge later removes the signed record (evidence) · CONFIRMED [R1]
- P2 · `send_daily_alerts.py:55-61` · the morning reminder counts tasks a partner cannot tick (waiting on the team's open work): "24 tasks need you today" daily for three weeks · CONFIRMED [R2]
- P2 · `services/plan.py:213` · a freshly confirmed rollout is "Off track" from minute one when the template's default lengths overrun the CRM's target; the customer sees the badge on day 5 · CONFIRMED [R3] · **design question**: honest forecast, but no plan exists yet
- P3 · `routes/projects.py:486-513` · the edit route overwrites every field the form omits (an API caller sending one switch clears PO, partner, outsourcer, vendor, dates); the React form sends all, so API-only · CONFIRMED [R2]
- P3 · `services/signoff.py:396-416` · a rejected sign-off's issue is never resolved; the next draft lists it as outstanding; the rollout closes with it open · CONFIRMED [R2]
- P3 · `routes/signoff.py:61` · `/api/projects/<id>/signoff` computes `awaiting_me` without the user: always false · CONFIRMED [R3]
- P3 · `services/raid.py:47-49` · "A issue is open, closed" · CONFIRMED [R1]
- P3 · `routes/projects.py:410-424, 1047` · a Sales member gets two "You are on …" bells at create · CONFIRMED [R1]
- P3 · `routes/projects.py:913-919` · the uploader is not told when their held upload is accepted (a rejection does tell) · CONFIRMED [R1]
- P3 · `routes/projects.py:1101-1120` · an invite writes no bell item for an existing account (`participants/add` does) · CONFIRMED [R2]
- P3 · `services/fields.py:86` · one unparseable stored number value answers 500 for the whole portfolio report and every rollout report; reachable only through bad imports · SUSPECTED [B2, B3]
- Design, recorded not graded: with customer approval on, **a decline changes nothing and a move while an approval is pending supersedes it silently** (`routes/projects.py:614-621, 696-733`); PRODUCT says "the stage still moves, and the decision is recorded", so this is as documented, but both directors and the advisor call it the biggest daily friction [R1, R3]. Also: any Customer contact can approve (no approver per rollout) [R1]; a repeating task makes no third occurrence while two are open, so a missed one quietly ends the series until someone ticks it (documented "at most two open repeats") [R1]; with mail off an existing external cannot get a new link (loophole #2, documented) [R1, R3].

### Concurrency and atomicity (A5, 5 runs each on the shared instance)
- P2 · `routes/projects.py:622-640` · stage move's follow-ups (audit, notices, outbox, rules) are best-effort after the commit: a failure gives 500 + moved + partial notices + no rule run · CONFIRMED (injection)
- P2 · `services/signoff.py:396-414` · reject commits, then the RAID issue in a second transaction · CONFIRMED (injection)
- P3→P2 with rules · `routes/projects.py:1555-1567` · task toggle is read-then-write, no `AND done=?`: 4 of 5 double audit + bell; an external ask ticked twice fires the rule twice (event rules carry no `event_key`) · CONFIRMED
- P3 · `services/signoff.py:458-460` · waive takes `MAX(version)+1` without `BEGIN IMMEDIATE`: 3 of 5 double clicks → 500 (UNIQUE), 2 of 5 → two waived versions · CONFIRMED
- P3 · `services/signoff.py:379-388` · countersign's compare-and-set lacks `superseded_at IS NULL`: a superseded version can read "countersigned" (the gate still refuses it: 0 of 15 opened) · CONFIRMED (message only)
- P3 · `routes/signoff.py:171-188` · two different staff sending at once: both succeed, the customer gets two "please sign" bells, the first pointing at a withdrawn version · CONFIRMED
- P3 · `services/ai/health.py:271-283` · AI job claim has no `AND status='queued'`: two workers run one job, a cancel is overwritten; only with a second worker (`--once` cron beside the service) · CONFIRMED in-process, SUSPECTED deployed
- P3 · `services/outbox.py:64-71` · the lease is stamped from a `now` taken at drain start; latent only for `drain()` with a large limit (production drains one at a time) · SUSPECTED
- Cleared: two stage moves (one 200, one 409), two intake confirms, same-deal-twice, approve vs decline, two sends by one author, two rejects, two signs, two drains (110 rows, every attempt = 1), lock contention (12 writers + 5 readers for 30 s: 5,762 writes, all 200, 0 "database is locked", move latency 11–33 ms).

### Scheduler at scale (B3; 150 / 300 / 750 rollouts, Linux fsync modelled at 5 ms)
- P2 · `services/rules.py:536-562` · unmatched candidates re-examined every pass forever · CONFIRMED
- P2 · `services/rules.py:54,553,562` · `SCAN_MAX` counts runs: a backlog of 300 tasks drains in 4 passes, 1,500 in 18 · CONFIRMED
- P2 · `backup.py:212-250` + `scheduler.py:285-345` · the backup runs in the clock thread ahead of alert sync; 2 GB = 66 s, writer stall 2 s; the 15-minute pass breaks at ~28 GB · CONFIRMED
- P2 · `backup.py:212-262` · no free-space check before writing; retention keeps 23 archives (≈49 GB at 2 GB each) · CONFIRMED
- P2 · `services/weekly_report.py:152-154` · one inline mail per recipient in the clock thread, never the outbox; failed addresses not retried · CONFIRMED
- P2 · `services/outbox.py:59-97` + `scheduler.outbox_pass` · one row at a time, 15 s timeout each: a hung Microsoft makes a 500-row digest two hours and starves urgent mail · CONFIRMED (modelled)
- P3 · `services/alerts.py:35,47,89-117` · two commits per created alert (3,358 commits in one 750-rollout pass) · CONFIRMED
- P3 · `services/alerts.py:89-117` · one bell item per alert type per person per rollout: 356 of 421 person×rollout pairs told 2–5 times in one cold pass · CONFIRMED
- P3 · `services/chasers.py:38-70` · one reminder mail per approval/sign-off, each with its own link: a customer on 5 rollouts gets 5 mails a morning · CONFIRMED
- P3 · `services/notifications.py:138,149` · bell bodies cut at 2,000 chars (the admin digest loses blockers, unowned tasks, milestones), held summaries at 600 (mid-word) · CONFIRMED
- P3 · `send_daily_alerts.py:21-40,90-129` · the digest is comma-run names in id order, no link or days late per rollout; 9 KB for an admin at 150, 64 KB at 750 · CONFIRMED
- P3 · `backup.py:62-79,250` · "Back up now" replaces the day's scheduled copy (newest per day kept) · CONFIRMED
- P3 · `backup.py:127-135` · "663 of 686 documents have no file" is a warning inside the run row only; nobody is told · CONFIRMED
- P3 · `services/doctext.py:150` · a missing file gets a permanent "the file is missing" row; restoring it never re-reads · CONFIRMED
- P3 · `services/retention.py:37,43-44` · `fetchall()` of every row past the cutoff, full scan nightly, 5 s default wait vs 30 s elsewhere · CONFIRMED
- P3 · `graph.py:539-553` · chunked upload has no per-chunk retry; one 429 fails the whole archive until the next day · SUSPECTED
- Budget: the worst quarter hour (digest + backup + weekly report + housekeeping + alert sync + drain) took 26.5 s of 900, 25 s of it the modelled mail loop; longest write-lock hold 109 ms (archiving 50k audit rows); everything scales linearly.

### Front end at scale (B2; Lighthouse 87–92 / 96–100 / 100; main bundle 238 of 260 KB)
- P2 · `App.tsx:100,124-130` + `lib/lazyPage.ts:16` · ~300 ms idle before every lazy page's first data request (React 19 Suspense hold) · CONFIRMED
- P2 · `services/dashboard.py:192` + `pages/Dashboard.tsx:756-767` · the dashboard's change check is `MAX(audit_logs.id)`, so reads rebuild it · CONFIRMED
- P2 · `pages/Flow.tsx:838-842` · focus reloads the Flow with no gap or in-flight check; Gantt and Calendar refetch with it · CONFIRMED
- P3 · `components/NotificationBell.tsx:25-26`, `pages/Dashboard.tsx:765-766` · focus + visibilitychange → two calls per return · CONFIRMED
- P3 · `components/CommandPalette.tsx:37-41` · refetches `/api/people` on every open · CONFIRMED
- P3 · `lib/usePoll.ts:28-33` and six AI panels · a rollout page sends 6 AI requests with AI off, and fetches the plan twice (35 requests) · CONFIRMED
- P3 · `pages/Flow.tsx:257,395`, `pages/FlowKanban.tsx:131,148` · rows and cards not memoised: every poll re-renders 114–150 rows (68–77 ms) · CONFIRMED
- P3 · `lib/theme.ts:25-31` · theme toggle 220–268 ms on `/board` (transitions on 5–8k nodes) · cost CONFIRMED, cause SUSPECTED
- P3 · `pages/FlowGantt.tsx:176,187,191` · zoom re-creates a span per day of a 500-day range; "Open every rollout" → 19k nodes · cost CONFIRMED, cause SUSPECTED
- P3 · `pages/Dashboard.tsx:219,227` · "n d late" label drawn under milestone diamonds ("24◇d") · CONFIRMED
- Clean: no page over the LCP budget on a quiet host (vw1 cold dashboard 2,508 ms under load), zero layout shift, heap flat at 42.7 MB after 10 minutes, every interaction under 100 ms (search debounced, palette, calendar month, bell, tick, note, Kanban drag frames).

### Server timing at scale (B1; in-process harness, 150 rollouts, ±10%; host loaded by the other agents)
Nothing is slow in absolute terms: dashboard ≈ 30 ms, Flow ≈ 12 ms, Gantt data ≈ 45 ms, bell and version polls 1–2 ms. SQL is a minority of the cost (Flow 4 of 12 ms, dashboard 15 of 33); the rest is the Python plan engine (`local_date` called 6,670 times per Gantt request, `policy("timezone")` re-parsed each time), JSON and per-row helpers. Growth is linear in rollouts (4× data → 3.4–4.4×); `/api/people` is quadratic in users × rollouts.

| Endpoint | p50 ms | Cause | Fix | Status |
|---|---|---|---|---|
| `/api/dashboard` | 30–37 | rebuilt per tab after any audit row; `get_stage_names()` 12× per request (3.7 ms); one UPDATE+commit per GET (`services/dashboard.py:255`); says each rollout three times (190 KB) | version check on write actions only; hoist `get_stage_names`; move the "since" write off the GET | CONFIRMED |
| `/api/flow/plan` (Gantt, refetched with every Flow poll and focus) | 45 | plan engine in Python; `task_links.links_for` once per rollout (117×); 409 KB, passes 500 KB at ~145 open rollouts | cache the zone in `local_date`; batch `links_for`; refetch only when the version moved | CONFIRMED |
| `/api/flow` | 12 (30 statements; **478 with any stage gate set**) | 4 correlated COUNT subqueries + `PROJECT_OPEN_SQL` per row; `signoff.completed` 17×; `gates.blocked` 3.8 statements per rollout | batch gates per stage; index below | CONFIRMED |
| `/api/people` | 16 (41 users); 30 (80 users); 67 (80 × 300) | 4 correlated subqueries per user, each walking all projects | one grouped pass over tasks and participants | CONFIRMED |
| `/api/reports/all` (+ PDF) | 46–75 | same engine as the Gantt + `links_for` 117× | as above | CONFIRMED |
| `/api/audit?page=1` | 38–46 | two full scans of 50k rows per page for the filter drop-downs | names from `users`, actions from a constant | CONFIRMED |
| `/api/calendar` | 8 (pm1: 68 statements) | `project_allows` per distinct task project; `substr(created_at,1,10)` defeats indexes | preload roles; range compare | CONFIRMED |
| `/api/session` | 2 (14 statements, every navigation) | 6 point reads of settings + the auth preamble; blocks each page's own fetch | read the 6 keys from the cached policy rows | CONFIRMED |
| `/api/my-work` | 7 (81 statements for pm1) | `project_allows` per project | preload roles | CONFIRMED |
| `/api/analytics` | 7–25 | reads every status note of every template and deleted rollout | restrict like `_cycle` does | CONFIRMED |
| `/api/projects` page as an external | 4.6 vs 2.2 | `sees_po` one query per row | preload the role map | CONFIRMED, trivial |

- **Indexes, measured on a copy:** `project_stages(project_id, position)` is the one that matters (people SQL 17 → 4 ms, flow −37% SQL, alerts −60%, dashboard −30% SQL); `audit_logs(action)`+`(user_id)` −29% on the audit page; `status_notes.author_id`, `tasks.done_at`, `tasks.due_date` change nothing measurable up to 10k tasks.
- **Contention over HTTP:** no 5xx and no "database is locked" in any run. Flask's dev server collapses under concurrency (Flow 69 → 18 req/s from 2 to 8 clients; dashboard p50 9.6 s with 40 readers), gunicorn 2×4 (production) holds 40–80 req/s with a dashboard p50 of 0.64 s at 40 readers; writers p95 under gunicorn at 40 readers ≈ 0.8 s.
- **Polling budget** (40 staff, a Flow tab and a dashboard tab each): 6–8.5 requests/s, 3–10% of one core; dashboard rebuilds are 80% of it at 10 audited actions a minute. CPU saturates before SQLite's writer: roughly 390 staff on two vCPUs at 150 rollouts, 120 at 600. The production disk's fsync cost is unmeasured and would cap writes at 30–300/s.
- **Answer sizes:** nothing over 500 KB; `/api/flow` repeats each row's stage list and team objects (1 KB per row, 123 KB; 10 KB gzipped, nginx gzips in production).

## Friction the directors felt (58 UX lines, grouped)
- **Approvals:** a decline leaves the stage where it is with only a note; the PM cannot ask again (same stage → 409; undo within 5 min; or back-and-forth, which sends everyone three bells); moving on supersedes a pending approval silently; turning approval on mid-rollout tells nobody; both customer contacts get every request [R1, R2, R3].
- **Bell:** bursts of 13–24 items in a second; paragraphs and list items run together (`services/notifications.py:46`); the same rollout 4–5 times after one alert pass; a rule telling the PM about a built-in alert doubles it; "1 of your rollout needs attention" [R1, R2, B3].
- **Digest and reminders:** walls of names; tasks overdue since January listed daily with no age cap; chasers stack on one customer the same day; after `chase_max` nobody tells the PM the customer never answered [R3, B3].
- **Intake:** two deals sat pending 28 days with no reminder; Discard lives only on the rollout page and only for Admins; the placeholder Admin stays Coordinator and inherits the template's Coordinator task; a rule's "add task" duplicates a template task just copied [R3].
- **Stage moves and sign-off:** gates are off by default, so four stages moved in an afternoon with six tasks open, which the sign-off draft then lists as outstanding; reopening a Closed rollout needs no reason; after close, externals land on an empty board; SLA and note saves answer with nothing to toast [R2, R3].
- **Externals:** partners and customers see a "drag a card" hint they cannot use and "no baseline yet" on a baselined rollout; a partner's reminder counts tasks waiting on others; every round needs a fresh link with mail off [R2, R1].
- **Automations:** a rule with no condition fires for every rollout; one bell item per task per rule per person (300 overdue tasks = 648 rows); a rule made today never fires for already-overdue tasks and the page does not say so [R3, B3].
- **Ops:** "Back up now" shows two ok runs and silently replaces the morning copy; the weekly report with mail off leaves no trace an admin can open; the documents-missing warning reaches nobody [B3, R3].
- **Seed/template:** the seeded SIEM template puts Hypercare before the SIEM stages, so a sensible plan reads red from day 3 [R2].

## The advisor's proposals (wave 3, Opus; proposals, not defects)

**Clicks for the five commonest PM actions:** a status note costs two page loads because the Flow detail has no note box; a stage move is three clicks (fine); a task tick is one click on My work (fine); asking the customer something is about seven fields in a task form that never says "ask"; seeing what is late on my rollouts needs "Mine" and "Needs attention", which cannot combine (`pages/Flow.tsx:233` holds one filter value), and Alerts has no "Mine" chip.

**Ten quick wins, by value ÷ effort:**
1. Keep paragraph and list breaks in bell text (`services/notifications.py:46`, one line).
2. Wording batch: "0 d over SLA" (`lib/format.ts:66` rounds; say "over SLA today"), "1 of your rollout", "A issue is open, closed", "Finish Closed by …".
3. Combinable Flow filters, plus "Mine" on Alerts.
4. The missing notices: invite, held upload accepted, approval switched on, chaser cap reached, vendor held at a gate, pending intake ageing.
5. "Copy sign-in link" for an existing customer or partner on the Team panel (mail-off reality; the sign-off link stays email-only).
6. A note box in the Flow detail with a customer-visible switch.
7. Customers and partners keep their closed rollouts (today they land on "No rollout is shared with you yet").
8. A digest that lists decisions ("3 things only you can decide today", then the five worst rollouts with days late and a link each) instead of comma-run names.
9. A neutral "No plan yet" health word until a plan is saved.
10. Group bursts of bell items per rollout (24 "Task assigned" in one second today).

**Three bigger bets, a phase each:**
- **A. Approvals as a first-class object:** a named approver per rollout, approval per stage (so Hypercare and Sign-off do not ask the customer to "decide" on our milestones), Request / Re-request / Withdraw verbs that tell the customer, a decline shown as a state and a health reason. The advisor argues for keeping "the stage still moves" as the default and adding an optional per-stage "wait for the customer" for the stages that truly are the customer's decision; that is a change to a documented decision and is the user's call.
- **B. A "Needs you" inbox:** the bell becomes one item per rollout per thing to do, resolving itself when done (today a superseded approval stays actionable), and the morning digest mails the same list.
- **C. Bookends:** at the start, product templates whose stage order and tasks match the work (the seeded EDR and SIEM templates fight the PM) and "No plan yet"; at the finish, a sign-off draft without internal tasks, a real done state for every party (certificate, final report, rating, lessons), and a reason required for reopen and delete.

Full text with the citing report lines: the advisor's report in the session scratchpad (`sim/reports/ADVISOR.md`).

## What to fix before v2.0.2 ships, and what can wait

**Before v2.0.2 (small, high value):**
1. #1 search cut for externals (one `AND t.assignee_id = ?` clause).
2. #3 sign-off draft: only customer-visible tasks (asks) in "Outstanding items".
3. #4 customer cut: drop `team`, `history.dwell`, `work.late`, `stages[].sla_days` for externals; hide the SLA chip on the customer's rollout page.
4. #5 guest author label without the outsourcer's name for customers (keep it for staff).
5. #2 RBAC save: require a marker field that the React form always sends, refuse a post without it, and confirm when more than N grants would turn off.
6. #6 intake `find()` including deleted rows (refuse the re-send while a discarded twin exists, or restore it), plus a unique index on `intake_deal_id WHERE deleted_at IS NULL`.
7. #10 three one-liners: filter the dashboard version to write actions, a 10 s minimum gap on the Flow's focus reload, `visibilitychange` only for the bell.
8. Bell text separators (`</p>`, `</li>` → newline) and "n of your rollouts".

**Next release (medium):** #7 one transaction for status + follow-up row (move, reject, tick + spawn) and a queued job for notices; #8 rules scan (exclude candidates older than `armed_at` in SQL, cap by time, batch per rollout); #9 weekly report through the outbox, backup off the clock thread (or alert sync first), outbox drain with a bounded batch and a shorter timeout; waive under `BEGIN IMMEDIATE`; toggle with `AND done = ?`; the 300 ms Suspense gap; one bell item per rollout per pass; chasers grouped per person.

**Decisions for the user (design, not defects):** customer decline as a real pause with a re-request action; an approver per rollout; a third repeat occurrence or a visible "series stalled" state; a reason and a notice on deleting a signed rollout; health wording before a plan exists.
