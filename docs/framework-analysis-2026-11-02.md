# Odin framework analysis — 2 Nov 2026

End-to-end architecture review of Odin at dev `0573dc3` (v2.1.0, unreleased): backend core,
background jobs and integrations (AI included), front end, and the delivery/quality framework.
Four reviewers (two Opus, two Sonnet), one layer each, read-only; every P1 and the top P2s
were re-checked in code before they went into this report. Earlier reports
(`docs/review-2026-10-14.md`, `docs/simulation-2026-10-28.md`) and closed loopholes are not
repeated.

## Verdict

The architecture fits Odin's scale with room to spare. At 150 rollouts the hot pages run a flat
number of queries (`/api/flow` 33 queries / 23 ms, `/api/dashboard` 50 / 31 ms), the alert pass
is ~24 queries in steady state, SQLite WAL has headroom, and every external call has a timeout.
No security hole or data-corrupting defect was found in the framework itself.

The risk is **operational, not structural**: a dead scheduler is silent, backups may live only
on the VM's own disk, and (when AI is on) the night shift can occupy the model into the working
morning. The biggest cheap win is in the test harness: ~80% of the 18-minute Python gate is
password hashing.

The structural debt is ordinary for a codebase that grew fast: domain logic in route modules,
implicit transactions, no client-side data layer, and release ceremony (the system map) that
costs more commits than it saves.

## 1. Operational risks (fix first)

| # | Risk | Evidence | Smallest step | Effort |
|---|---|---|---|---|
| R1 | **A dead scheduler goes unnoticed.** Every ops bell comes from the scheduler itself; `/healthz` answers 200 "ok" to outside callers whatever the heartbeat; queued mail older than 24 h is dropped as too old. A crash-looping scheduler stops alerts, digest, chasers, backups and housekeeping with no signal. | `routes/auth.py:417-466`, `scheduler.py:435-470`, `services/outbox.py:96-101` | Web process shows admins a banner/bell when the heartbeat is >10 min old; `/healthz?scheduler=1` returns 503 when stale, for the external uptime check. | S |
| R2 | **Backups may exist only on the VM.** With no off-server destination a local backup counts as success; OneDrive/SharePoint need M365 (not connected); the updater's pre-update backup is local too; `SECRET_KEY` is outside backups by design. One lost disk takes the database, uploads and every backup. The network-share copy has no timeout and runs in the clock thread. | `backup.py:163, 273-288`, `scheduler.py:264-281`, `policies.py:206-210` | Daily admin bell when no off-server copy succeeded in N days; preflight WARN; share copy in a subprocess with a timeout. **Needs your answer: is an off-box copy (share, vzdump, other) running in production?** | S |
| R3 | **AI night shift runs into the morning** (only while AI is on). It queues 3 per-rollout features for every open rollout; the "nothing changed" skip never fires because inputs carry `today` and day counters; the queue is strict FIFO, so morning briefs and people's drafts wait. ~300–360 calls × ~48 s ≈ 4–5 h from 03:30, ending ~08:00–08:45; Zeus shares the server. | `services/ai/health.py:200-204, 273, 355-369`, `features/weekly_words.py:40`, `raid_proposals.py:39` | Order jobs `requested_by IS NULL, id` (people first); hash inputs without `today`/day counters; weekly_words only before a report day; validation on change + weekly instead of daily. | S |
| R4 | **Nobody can see the outbox.** No route reads it; failures surface as one bell per kind per day. Once mail is on, a failed approval request looks like a sent one, with no retry. | grep: no reader of `outbox`; `services/notifications.py:250-268` | Settings › Notifications "Delivery" panel: pending / given-up counts, last 50 failures, Retry. | S–M |
| R5 | **One user's delegated M365 sign-in will power mail, Teams posts and cloud backups.** A password/MFA reset, Conditional Access change or 90 days idle stops all three at once. | `graph.py:33, 237-263` (Teams bot already uses app-only) | Before go-live Phase 6: app-only `Mail.Send` scoped to the mailbox, `Sites.Selected` for backups. | M |
| R6 | **Thin observability.** ~12 real logger calls, no per-request access line (route, status, ms, user), 3×10 MB log rotation, client crash reports only as log lines; external uptime check documented but unverifiable from the repo. | `core.py:43`, `docker-compose.yml:12-15`, `docs/RUNBOOK.md:20-35` | One `after_request` access-summary line; rotation 5×20 MB. **Needs your answer: is the Uptime Kuma / Cloudflare check set up?** | S |

## 2. Quick wins (high value, small effort)

| # | Win | Evidence | Step |
|---|---|---|---|
| Q1 | **Python gate 1,057 s → ~150–200 s.** Every test seeds an admin with PBKDF2 at 1,000,000 iterations (~0.31 s each, ~3 per test); hashing is 56–88% of module time. Measured: `test_v2_workload` 28.9 → 3.9 s, `test_v2_intake` 37.8 → 5.4 s at 1,000 iterations, no failures. | `db.py:824`, werkzeug default 1,000,000 | One line in `test_app.py` (imported by every module) lowering `werkzeug.security.DEFAULT_PBKDF2_ITERATIONS` for tests; production unchanged. |
| Q2 | **vitest gate stops flaking under load.** Default 5 s timeout, no worker cap, 79 `userEvent.setup()` with keystroke delay; 19 of 23 failures under load were timeouts (the gate has hit this twice). | `frontend/vite.config.ts` | `testTimeout: 20_000` in the ui project, `userEvent.setup({ delay: null })`, `maxWorkers`. |
| Q3 | **Order-dependent reset test fixed** (and tests stop writing into the repo). `reset_data` binds `DB_PATH`/`UPLOAD_DIR` at import, so `test_reset_data_wipes_every_project_table…` fails after other modules (reproduced); `routes/auth.py` binds `AVATAR_DIR` the same way and a test wrote into `./avatars/`. | `reset_data.py:31`, `routes/auth.py:15`, `db.py:41` | Read `db.DB_PATH` etc. at call time. |
| Q4 | **Settings shows the wrong section's data on a quick switch** (confirmed race); 14 of 19 hand-written fetch effects have no latest-wins guard. | `frontend/src/pages/Settings.tsx:60-63`, `ReportAll.tsx:86` | Move them onto the existing `useLoad(key, fn)`. |
| Q5 | **~25 in-app links reload the whole SPA** (835 KB JS + session) — the Projects list → rollout click is the most common journey. Plus a hand-kept `REACT_PAGES` allowlist that silently downgrades nav links. | `Projects.tsx:135,140,177,183`, `Flow.tsx:670`, `AppShell.tsx:27` | `<Link>` instead of `<a href>`; drop `REACT_PAGES`. |
| Q6 | **Schema bump enforced by a test.** `SCHEMA_VERSION` is raised by hand; the rollback guard depends on it. (Fresh vs upgraded-from-v1.0.0 databases converge today: 0 differences.) | `db.py:251` | Generated `tests/golden_schema.json` that fails when the shape changes without a bump; keep the convergence check as a test. |
| Q7 | **Contract fixtures diff only on shape.** The last regeneration changed 25 of 40 files, almost all timestamps; the real changes (`task_stalled`, `customers`) were buried. | `test_v18_meta.py:722-740`, commit 45dccf1 | Normalise values by type when writing fixtures; pin the seed clock. |
| Q8 | **Main bundle at 95% of its ceiling** (245.7 / 260 KB gzipped) and a cold-load waterfall. | `frontend/e2e/perf.mjs:14` | Lazy-load Project, ProjectForm, Account, People, MyWork as the admin pages already are. |
| Q9 | **Write-per-read on API tokens** (every `/api/v1` GET commits `last_used_at`) and on rate-limited intake calls. | `routes/tokens.py:56-63`, `services/intake.py:54-58` | Write only when the date changes; one rate-limited row per minute. |
| Q10 | Small reliability fixes in the clock thread: daily notice marker written before the notice (a locked DB loses that day's "backup failed"), Graph connections wait 5 s not 30 s, weekly report renders all 150 PDFs then discards most, doc-text pass has no total budget, digest/weekly Teams posts bypass the outbox. | `scheduler.py:231-239`, `graph.py:41-50`, `weekly_report.py:109-129`, `doctext.py:125-134`, `send_daily_alerts.py:106-109` | One-liners each. |

## 3. Structural debt (plan, don't rush)

| # | Debt | Evidence | Recommended step | Effort |
|---|---|---|---|---|
| D1 | **Core domain logic lives in route modules; services import routes.** `change_stage` (the only stage-move path) reads `session`, calls `abort`, builds `url_for`; 353 direct `db.execute` in routes; `routes/api.py` 1,612 lines / 94 lazy imports; `services/dashboard.py` and `services/signup.py` import from routes. | `routes/projects.py:93, 554` | Move `change_stage`, `decide_approval`, `load_project`/visibility, `save_document` and the login family into services with the actor passed in; routes become thin wrappers. Do it module by module. | M |
| D2 | **Transactions are implicit.** 217 `commit()` sites, many inside shared helpers (`audit_log`, `outbox.add`, `notify_users`, `soft_delete`); one stage move = 8 transactions / 61 queries; 12 routes write after a committing helper (e.g. an invited external user is committed before their participant row). `rules.flush` silently rolls back anything a route forgot to commit. | `services/audit.py:47`, `services/rules.py:301-317` | One unit of work per request: helpers stop committing, one hook commits on success / rolls back on error; explicit commits only at intended durable boundaries. | M |
| D3 | **No client data layer.** One rollout page fires ~14 requests (plan fetched twice, intake three times); invalidation by remount keys and stamp counters; three loading idioms; polling hand-written five times with different visibility/focus/error rules. | `Project.tsx:56,63,195`, `PlanPanel.tsx:27`, `PendingIntake.tsx:38,44,60`, `Flow.tsx:858,918` | Give `useLoad` a keyed cache with in-flight dedupe and `invalidate(prefix)`; one `useVisibleInterval` hook that stops on 401. No query library. | M |
| D4 | **God pages.** Flow 1,110 lines (19 useState, 13 components, exported `Detail` imported by Project — a page-to-page dependency), Dashboard 927, Settings 641; 18 of 29 pages have no jsdom test. | `Flow.tsx`, `Project.tsx:14` | Move `Detail`/`StageTasks` to components; `useFlowParams` hook; split Settings per section as its routes already are. | M |
| D5 | **Schema has no single source.** 39 tables in `schema.sql`, 20+ more created only inside a 531-line `migrate_db` (CLAUDE.md says 2.0 tables are all in schema.sql — not true for 18), plus `NEW_*_COLUMNS` and 32 ALTERs; `_purge_orphans` is a second hand-kept copy of the purge list and misses `ai_calls`. | `db.py:269-800` | After Q6: move table definitions into `schema.sql`, derive the orphan list from the purge list, one test that every project-keyed table is in `WIPE_TABLES`. | S–M |
| D6 | **Two API styles leak into client logic.** Form routes signal failure only by flash category; `Account.tsx:71` branches on the text "Password updated". | `core.py:472-497` | Let form routes return structured data through `json_for_fetch`; new routes JSON-only. | S to start |
| D7 | **Tests organised by release.** 36 of 37 modules named by version; harness spread across ~25 cross-imported base classes inside a 6,583-line `test_app.py`; the module list is hand-kept in 3 places plus a meta-test to catch drift. | `test_fix_logic.py:12-26`, `ci.yml`, `ci_local.sh`, `CLAUDE.md` | Extract `tests/harness.py`; `unittest discover` (or one list file) instead of three lists; then shard CI. No mass rename. | M |
| D8 | **Release gate runs on a different interpreter than production** (local Python 3.9/macOS vs 3.12/Linux, dual pins kept for 3.9; 156 `utcnow()` calls deprecated on 3.12 but silent locally). | `requirements.txt`, `scripts/ci_local.sh` | Local venv on 3.12; drop the 3.9 pins; one UTC helper. | S |
| D9 | **Production builds from source and rollback is another build** (`npm ci` + `vite build` on the VM; CI's image is never what runs). | `deploy/odin-update.sh` | Release workflow pushes `ghcr.io/…/odin:vX.Y.Z`; updater pulls and retags (instant, byte-identical rollback); keep build as fallback. | M |
| D10 | **The production trust boundary is "who can push a tag".** No branch protection (known), pre-push hook not installed, nothing checks `VERSION` is raised on a PR into main (a missed bump ships nothing, silently), updater trusts any `v*` tag without verification. | `release.yml:33-36`, `.git/hooks` | `core.hooksPath scripts/hooks`; CI step: `VERSION` > latest tag on PRs to main; later, signed tags + `git verify-tag` in the updater. | S / M |
| D11 | **The system map costs ~40% of commits.** 89 of the last 200 commits touch it, 80 are standalone "regenerate" commits; the file is 544 KB with one 358 KB generated line, so diffs show nothing; the Stop hook forces ceremony commits on timestamp alone, while CI's `map` job already enforces freshness on PRs to main. | `scripts/system_map_stale.sh`, `ci.yml:48-58` | Generate the facts block only at release (RELEASING step 4) and in the Docker build; keep the hand-written loophole register as the only edited part; drop the hook's timestamp check. **Your call — it is your process.** | M |
| D12 | **CI cost.** A dev commit with an open PR runs the full suite twice, the merge a third time; docker waits for the e2e job; advisory audits block unrelated hotfix releases while the weekly audit already detects them. | `ci.yml:6-9, 45-46, 74-75, 145` | Drop `push: dev` (or skip when a PR exists); docker after frontend only; audits non-blocking on push/PR. | S |
| D13 | Smaller: 638 function-level imports (only 15 avoid a real cycle); `core.py` mixes the app with pure validators (12 services import Flask just for `text_field`); request hooks ordered by import side effect; 906 literal `text-[Npx]` classes with the type ramp enforced only in prose; no formatter (664 lines >200 chars); three compose variants and two ~85%-identical nginx configs; runtime image carries `frontend/src`, `e2e`, `scripts`; point-in-time reports beside runbooks in `docs/`. | various | Opportunistic, when touching those files. | S each |

## 4. Keep (do not break these in a refactor)

- **One stage-move path** with compare-and-set and best-effort follow-ups; one approvals door; one AI door (meta-tested).
- **Database-backed claims and uniqueness** instead of leases: outbox and AI jobs claimed by conditional update; partial unique indexes on alerts and rule runs; due jobs keep "tried" and "done" apart under `flock` — a second scheduler or a crash loop doubles nothing.
- **Policies registry**: 121 typed, validated, audited settings, all read, cached per request.
- **Generated guards**: golden routes × roles, API contract against `api.ts`, the schema-walking purge test, the updater's 30-scenario test with stubbed docker.
- **Supply chain and image hygiene**: sha256 lock with `--require-hashes`, digest-pinned bases, non-root image, CI leak check; tags cut only after green CI on main.
- **Front end**: strict TS (1 `as unknown as`, 2 `any`), token-only theming with a contrast test across 9 accents × 2 themes, `useLoad` latest-wins semantics, `lazyPage` reload-once after a deploy.
- **Request ids** from nginx through gunicorn to the app log and the error page, token paths redacted; `/healthz` does a real rolled-back write.

## 5. Questions only you can answer

1. Is an **off-server backup** running in production (network share, Proxmox vzdump, other)? Decides whether R2 is P1.
2. Is **AI switched on** in production? Decides whether R3 is live today.
3. Is the **external uptime check** (Uptime Kuma / Cloudflare) set up? R1 and R6 lean on it.
4. Keep the **system map** as a per-commit artifact, or generate it at release only (D11)?

## 6. Suggested order

1. **Round 1, one small release (all S):** R1, R2 bell + share timeout, R3 ordering and hashing, Q1–Q5, Q9, Q10. Mostly one-liners; Q1 alone makes every later round ~5× faster to verify.
2. **Round 2:** R4 outbox panel, R6 access log, Q6–Q8, D8, D10 (hooks + VERSION check), D12.
3. **Before M365 go-live:** R5.
4. **Then, one module at a time:** D1 + D2 together (services own transactions), D3 + D4 together (data layer, then split Flow), D5, D7, D9, D11 per your call.

## 7. Measurements

| Measure | Value |
|---|---|
| Code | routes 8.2k lines / 272 routes; services 9k (+2.3k AI); root Python 5.4k; front end pages 9k, components 6.2k, lib 3.7k |
| Tests | Python 950 tests / 37 modules / 16.3k lines, gate 1,057 s; vitest 343; Playwright 95 (flows: 52 serial on one DB) |
| Queries at 150 rollouts | `/api/flow` 33 (23 ms), `/api/dashboard` 50 (31 ms), rollout detail 31, session 16; stage move 61 queries / 8 transactions / 120 ms; alert pass 24 queries steady |
| Data | 57 tables (27 project-keyed), 64 indexes, 121 policies, 20 env vars |
| Commits | `commit()` sites 217; function-level imports 638 (15 cycle-guarding) |
| Background | 1 scheduler process, 4 threads; 24 external HTTP call sites, all with timeouts |
| Front end | `api.ts` 869 lines / 285 exports; contract covers 36 of 48 named GETs (11 anonymous uncovered); main bundle 245.7 KB gz of 260 ceiling |
| Map | 89 of last 200 commits touch `docs/system-map.html` (544 KB) |
