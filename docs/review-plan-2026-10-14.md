# Odin full review plan — 14 Oct 2026

Written by Fable; to be run by Opus. A senior-developer review of everything on `dev`
(v1.6.0 live + unreleased: design round 2, Odin-PMS@ alias, Odin PMS Teams app, Kibana
removal, Flow views Kanban/Gantt/Calendar). Thirteen junior reviewers as agents, each with
one angle, then a fourteenth that looks across everything for missing best practices and
quality-of-life gains, then the senior pass: verify, de-duplicate, rank, fix.

## Ground rules (every agent)
- Read-only. No edits, no commits, no servers on 5050, never touch `odin.db` or `uat-data/`.
  Throwaway servers only on 5111–5117 with `ODIN_DATA_DIR` in the scratchpad, seeded by
  `scripts/seed_uat.py`; seed accounts from `frontend/e2e/helpers.ts` (never echo passwords).
- Report as a list: `file:line · severity (P0 blocker / P1 must fix / P2 should / P3 nit) ·
  the defect · how to reproduce or why it breaks · suggested fix · CONFIRMED (ran or read it)
  or SUSPECTED`. No praise, no restating what works, no style nits unless they mislead.
- Authority: `CLAUDE.md`, `DESIGN.md`, `PRODUCT.md`, the memory rules (desktop-first,
  English-only, tokens only, one auth door, audit everything, plan words for health,
  "rollout" wording). A finding that contradicts a documented decision is not a finding.
- Phone-only findings are out of scope (desktop ~90%); note them in one line at the end.

## Orchestration (Opus runs this)
Run as a Workflow or as parallel Agent calls, three waves, with Opus as the senior:
1. **Wave 1 (parallel, 13 agents, Sonnet for the static readers, Opus for the four that
   drive a browser or simulate roles):** reviewers 1–13 below.
2. **Wave 2 (one agent, Opus, after wave 1):** reviewer 14, the best-practice and
   quality-of-life advisor, reads every wave-1 report plus the code and proposes what the
   defect hunt cannot: what we are not doing that we should, and what would make daily
   use smoother.
3. **Wave 3 (senior, Opus):** merge the lists, drop duplicates, verify every P0/P1 by
   reading the code or reproducing it, re-grade, and write the report
   (`docs/review-2026-10-14.md`): a table per severity, a count per angle, the fixes
   ordered by risk × effort, and reviewer 14's proposals as their own section for the
   user to pick from.
4. **Wave 4 (only with the user's go):** fix P0/P1 on dev in phases, the suites after each,
   a throwaway server check, commit, map, republish. P2/P3 and the picked proposals become
   the next phases.

Each agent gets: this file's rules, its own section below, the key paths, and the
instruction to finish with a count of CONFIRMED vs SUSPECTED.

## The reviewers

### 1. Backend logic (Python) — Sonnet
Scope: `routes/*.py`, `services/*.py`, `db.py`, `policies.py`, `constants.py`,
`scheduler.py`, `send_daily_alerts.py`, `backup.py`.
Hunt: wrong calculations (days in stage, SLA, working days vs calendar days, late tasks,
health = worse of plan RAG and schedule, forecast chains), off-by-one on dates and time zones
(stored UTC vs workspace local day), race conditions (compare-and-set on stage moves, undo
window, concurrent plan saves), soft-delete and purge cascade for every `project_id` table
(`reset_data.WIPE_TABLES`, `cleanup_soft_deletes`), scheduler jobs that can run twice or
never, exceptions swallowed silently, N+1 queries on the Flow/Gantt/portfolio paths,
migrations that assume column order, `policy()` defaults that drift from `POLICIES`.

### 2. API contract — Sonnet
Scope: every `/api/*` route in `routes/api.py` and the JSON twins of form routes; `lib/api.ts`.
Hunt: fields the frontend reads that the server never sends (and vice versa), types that
disagree (`stages` list vs count, nullables), error shapes (`error` vs `messages`), status
codes (403 vs 404 leaks existence), pagination bounds, `as_id`/`text_field` limits missing,
JSON bodies not validated, routes without `permission_required` or `project_role_required`,
the read-only `/api/v1` token API exposing more than read.

### 3. Security — Opus
Scope: `security.py`, `core.py`, `routes/auth.py`, `routes/sso.py`, `routes/mfa.py`,
`routes/guest.py`, `routes/tokens.py`, `routes/signup.py`, `graph.py`, `services/teams_bot.py`,
`services/sealed.py`, nginx and Dockerfile under `deploy/`.
Hunt: auth bypass (any second login door besides `attempt_login`), CSRF exemptions
(`/api/teams/messages` — confirm it reads nothing), IDOR on every `<int:project_id>` and
`<int:task_id>` (`load_project` as the one door), guest-link token entropy and lifetime,
sign-in link single use, session fixation, password reset flow, TOTP replay, SSO state and
nonce, open redirects in `next=`, file upload type/size/path traversal, download of another
project's documents, SQL built with f-strings (every `{scope_sql}` — confirm parameters),
XSS in `escape()`-less HTML (emails, Teams cards, PDFs, Jinja guest pages), CSP (nonce,
`frame-src`, fonts), secrets in logs or audit details, sealed token storage, rate limits on
login/link/signup, information in error pages, `Permissions-Policy`/`X-Frame-Options`,
the audit meta-test's exemption list, dependency CVEs (`pip list --outdated`, `npm audit`).

### 4. RBAC simulation — Opus (drives a throwaway server)
For each of **Admin, Member, Contributor, Viewer** and each external project role
(**Contractor, Reseller, Customer** via sign-in link), and for the **guest vendor link**:
start a seeded server, sign in, and walk every route in `frontend/src/App.tsx` plus every
`/api/*` and form route with GET and (where applicable) POST/PUT. Build the matrix:
route × role → 200 / 403 / 404 / redirect, and compare with `PERMISSIONS`, `ROLE_PERMISSIONS`,
`PROJECT_ACTIONS` and PRODUCT.md's role descriptions. Flag: anything a role can do that the
matrix says it cannot (P0), anything it should but cannot (P1), external accounts seeing
internal fields (PO number, internal contacts, reasons, baseline), partners on one project
reaching another, a Viewer changing anything, the Kanban `can_move`, Gantt `can_edit` and
calendar `can_edit` flags matching the server's refusals when forced with curl.
Also: the Settings menu items each role sees vs can POST to; the read-only API token's reach.

### 5. Frontend code (React/TS) — Sonnet
Scope: `frontend/src/**` except tests.
Hunt: state that goes stale after a mutation (lists not reloaded, the detail pane after a
Kanban move or calendar drag), effects without cleanup (polls, listeners, timers), stale
closures in `useCallback`, missing `key`s, unhandled promise rejections, `ApiError` branches
that swallow messages, double submits (busy flags), optimistic updates without rollback,
URL state that can disagree with component state (`?view`, `?rollout`, `?month`, `?week`,
`?day`, `?cal`), localStorage reads without try/catch, `lazy()` chunks that fail offline,
dead code and unused exports after the Kibana removal and the Flow rewrite, TypeScript
`as` casts hiding real type errors, and anything the `oxlint` baseline (15 warnings) hides.

### 6. UI consistency (against DESIGN.md) — Sonnet
Scope: every page and component; `DESIGN.md` is the ruler.
Hunt: hard-coded colours or non-token classes, sizes outside 11/12/13/14/17/24, spacing off
the 4/8 grid, cards inside cards, red used for anything but overdue/declined/blocker/
critical, `--bad` for errors (must be `--destructive`), health words other than On track /
At risk / Off track, "project" where "rollout" is the rule (and vice versa for the record),
hand-copied fields/labels/pills where `lib/ui.ts`, `PanelTitle`, `Panel`, `PageHeader`,
`Segmented`, `StateChip`, `StatTile`, `EmptyState`, `MoveConfirm` exist, pill-shaped
`<Button>`s, Save enabled before a change, glyphs outside the self-hosted font subset,
dark-mode branches in components (never allowed), the new Kanban/Gantt/Calendar against the
"Flow views" section.

### 7. UX and flows — Sonnet (reads code + the e2e journeys)
Walk each journey as a first-time user would, from the code and `frontend/e2e/flows.spec.ts`:
create a rollout → plan → move stages (rail, Kanban) → tasks (project, My work, calendar
drag) → approvals → RAID → report → sign-off → close; settings → connect M365 → test
buttons; sign-up link → approval; forgot password; partner link.
Hunt: dead ends (an error with no way out), confirmations missing on destructive acts or
present on harmless ones, toasts that vanish before they can be read, undo that cannot be
reached, empty states that explain nothing, forms that lose input on error, keyboard traps,
focus lost after dialogs, loading states missing (>300 ms), the Flow's four views disagreeing
on filters or selection, the detail pane under a view that no longer contains the rollout,
copy that is unclear, jargon, or inconsistent ("Move to", "Open rollout", plan words).

### 8. Visual checker — Opus (throwaway server + Playwright screenshots)
Boot a seeded server, sign in as admin and as a Customer, screenshot every page in
`e2e/smoke.spec.ts` PAGES plus `/board?view=kanban|gantt|calendar`, `?cal=week|agenda`,
and `/projects/1` fully scrolled, at 1440×900 and 1280×720, light and dark, every accent
(set `odin.accent` in localStorage: blue, red, green, …). Look at each image. Flag:
overflow/clipping, truncation that hides meaning, misaligned rows, contrast failures by
eye (and run `@axe-core` for both themes), empty gaps, overlapping bars/labels on the Gantt
and calendar, the Kanban at 10+ columns, print of the portfolio and sign-off (`page.pdf`),
the guest page and the error page (frozen stylesheet: defects only), the Teams-app icons
in `static/teams`, favicons. Save images to the scratchpad and cite them by name.

### 9. Accessibility — Sonnet (code) + axe output from reviewer 8
Hunt beyond axe: every icon-only control has a name; drag-and-drop has a keyboard route
(Kanban grip = button; Gantt bar = Enter; calendar task chip — does it have one? P1 if not);
live regions announce moves and errors; dialogs trap and return focus; the Flow list's
roving tab stop; tooltips readable by keyboard; colour never alone (late = glyph + word);
`aria-rowcount` on the Gantt grid matches; headings in order on every page; reduced motion
respected; the `Segmented` radiogroup arrow keys; skip link; labels on native selects.

### 10. Tests and CI — Sonnet
Scope: `test_app.py`, `test_fix_*.py`, `frontend/src/**/*.test.ts(x)`, `frontend/e2e/*`,
`.github/workflows/*`, `playwright.config.ts`, `vitest.config.*`, the meta-tests.
Hunt: paths with no test (list the top 20 by risk: every new route since v1.6.0, every
`change_stage` caller, `teams_bot`, `mail_from` fallback, Gantt drag save, calendar drag,
Kanban refusal), tests that pass for the wrong reason (mocked too deep, asserting on
fixtures), flaky patterns (sleeps, race-prone waits, `.first()` on lists), tests coupled to
seed dates, the visual goldens being stale (CI blocked), coverage of each role in e2e
(admin/member/viewer only — no Contributor, no external), the perf budget, the meta-tests'
exemption lists growing.

### 11. Data, migrations, ops — Sonnet
Scope: `db.py` (schema + migrations), `schema.sql`, `reset_data.py`, `backup.py`,
`preflight.py`, `deploy/*`, `Dockerfile`, `docker-compose*.yml`, `scripts/*`.
Hunt: migrations not idempotent or order-dependent, indexes missing on hot queries
(`tasks.project_id`, `status_notes.project_id`, `notifications.user_id`, `audit`), tables
that only grow with no trim (`ai_calls`, `login_links`, `user_activity`, `settings
teams_conv:*` on disconnect), backup completeness (DATA_DIR/brand, uploads, fonts? no), the
restore test, the cron updater's rollback path, env vars documented vs read, `SECRET_KEY`
handling, log rotation, the new npm deps (`@dnd-kit/*`) in the Docker build and the
lockfile, Python/Node version pins, healthz depth.

### 12. Product fit — Sonnet (reads PRODUCT.md + the UI copy)
Compare the built app with `PRODUCT.md` and the memory's product decisions: every promised
capability present, anything built that PRODUCT.md does not mention (document it or cut
it), commercial fields that crept back (must stay removed), wording drift ("rollout",
plan words, no Kibana), settings that exist but no page exposes, policies without help
text, notification kinds without an Account toggle, emails/Teams cards whose copy or links
are wrong (public_url), the Odin PMS manifest's name/description, the guest page's scope.

### 13. Every button, visually — Opus (throwaway server + Playwright, one page at a time)
The question: does each control do what its label says, and does the page show it did?
Method, per page in `e2e/smoke.spec.ts` PAGES plus the Flow's four views, the project page's
every panel (Notes, Plan, RAID, Scope & sign-off, Details, Team, Stages, Documents, Activity,
Sharing), the Settings sections, Users (incl. the Manage dialog), Account, and the sign-off
composer — as Admin, then as Member:
1. List every interactive element (`read_page` / `page.locator("button, a, [role=button],
   [role=radio], [role=tab], [role=menuitem], input, select, textarea, summary")`), with its
   accessible name.
2. Click or operate each one, in order, with a screenshot **before** and **after**, and the
   network calls it made (`page.on("request")`). Destructive ones (Delete, Revoke, Disconnect,
   Deactivate, Waive, Withdraw) only up to their confirm, then Cancel — never confirm on the
   seed unless the e2e journey already does and undoes it. Form submits with valid and with
   empty input.
3. Judge each: did it do what its label says; did something visible change (a toast, a
   navigation, a list update, a dialog, a disabled state, a count) within 300 ms or a
   loading state appear; did it stay usable (not stuck busy); hover, focus and pressed
   states visible; no console error; no 4xx/5xx. A control that does nothing, does the
   wrong thing, gives no feedback, or works only on the second click is a finding with the
   two screenshots named. Count controls checked per page and list the ones not reachable
   (hidden behind data the seed lacks).
4. Keyboard pass on the same pages: Tab reaches everything, Enter/Space operate, Esc closes.

### 14. Best practices and quality of life — Opus (wave 2, after reading all wave-1 reports)
Not a defect hunt. Two lists, each item one line with where it applies and why it is worth
it, graded quick win / medium / large:
- **Best practices we are missing**, across every angle: backend (structured logging,
  request ids, health checks with dependencies, graceful shutdown, DB connection handling,
  transaction scopes, idempotency keys on retried posts, input validation at every edge,
  typed JSON, pagination defaults, N+1), security (headers, secret rotation, session
  limits, audit of reads of sensitive data, dependency pinning and CVE scanning in CI,
  backup encryption, least privilege on the Graph scopes), frontend (error boundaries per
  route, suspense fallbacks, optimistic updates with rollback, request de-duplication,
  query caching/invalidation, bundle analysis, lazy routes, a11y linting, strict TS flags),
  UX (consistent loading/empty/error states, undo over confirm, inline validation, save
  state indicators, keyboard shortcuts documented, onboarding for a first admin),
  testing (contract tests between `lib/api.ts` and routes, role matrix test, visual goldens
  runnable locally, mutation testing, flake tracking), ops (observability, alerts on the
  scheduler, backup restore drills, release checklist, runbook, SLO for the cron updater),
  docs (ADRs for the decisions in memory, API docs for `/api/v1`, a CHANGELOG from the map),
  process (branch protection substitute, PR template, pre-commit hooks for lint/tests).
- **Quality-of-life improvements** a daily user of each page would thank us for: the
  dashboard, Flow (all four views), My work, People, Rollouts, the project page, reports,
  sign-off, Settings, Users, Account. Think: fewer clicks, remembered choices, bulk actions,
  search everywhere, saved filters, "copy link", drag where it is expected, keyboard
  shortcuts, better empty states, what the Teams card and email could carry, notifications
  people would want to mute, exports, print.
Rank each list; mark anything already decided against in memory/PRODUCT.md as "decided
against: skip" rather than proposing it again. End with a proposed order for the next
three releases.

## Senior pass checklist (Opus, wave 3)
- Every P0 reproduced or read in the code; every P1 at least read.
- Cross-check the RBAC matrix against the security findings.
- Group by fix, not by finder; estimate effort (S/M/L); order by risk.
- Write `docs/review-2026-10-14.md`; publish it as an artifact; send the user the summary:
  counts per severity, the five worst, what to fix before v1.7.0, what can wait, and
  reviewer 14's top ten proposals as a separate list to choose from.
- Do not fix anything without the user's go.

## Suggested agent prompt skeleton
```
You are reviewer N ({angle}) on Odin, a Flask + SQLite JSON API with a React 19 /
Vite / TypeScript / Tailwind v4 / shadcn SPA in frontend/. Read-only. {ground rules}.
Scope: {paths}. Hunt: {list}. Read fully before judging; trace a flow end to end before
calling it broken. Output: the finding format above, severity-ordered, then
"CONFIRMED: n, SUSPECTED: m". Nothing else.
```
