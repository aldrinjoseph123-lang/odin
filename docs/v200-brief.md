# v2.0.0 build round: shared brief for every agent

Odin (Flask + SQLite JSON API, React 19 + TS + Tailwind v4 + shadcn base-ui SPA in
`frontend/`) at /Users/aldrinj/PMS, branch `dev`. This round builds **Odin 2.0** (the
user's plan of 6 Oct 2026, artifact https://claude.ai/artifact/9h1iRQQqVw74LvHTEC5oko,
summarised per workstream in your prompt) plus the quality-of-life ideas B2–B20 from
`docs/review-2026-10-14.md` ("Reviewer 14", section B). Read **CLAUDE.md**, **PRODUCT.md**
and, for UI work, **DESIGN.md** first.

## Decisions already taken by the user (do not reopen)
- Odin stays a rollout-lifecycle and evidence tool: no commercials (budgets, rates,
  invoices), no marketplace, no mobile app. Workload is hours and counts only.
- CRM is in-house: Odin ships an intake endpoint + token contract, no vendor connector.
- Gate override: Admin and the project manager, with a typed reason; audited, shown in
  the stage history.
- Template tasks: yes, with roles, offsets and links.
- Rules reach staff and Teams only, never the customer; rules never move stages.
- Capacity in hours per week (policy default 30, per-person override). CSAT: one rating
  at sign-off. Dependencies: finish-to-start, within one rollout; no full critical path.
- Desktop and English only; phone layout is not a priority.

## Rules for every agent
- **Own only your files** (your prompt lists them). Others edit other files at the same
  time. Put new logic in NEW modules (`services/<feature>.py`, `routes/<feature>.py`,
  new React components/pages) and keep edits to shared files (schema.sql, db.migrate_db,
  policies.py, constants.py, routes/projects.py, routes/api.py, lib/api.ts, Project.tsx,
  Flow.tsx, App.tsx, smoke/flows specs) to small hunks; **re-read a shared file right
  before every edit**; never revert someone else's change.
- **No git** (no commit, stash, checkout, reset). The lead commits.
- **Never** touch `/Users/aldrinj/PMS/odin.db`, `uat-data/`, or ports 5050, 5051, 5099.
  If you run a server, use only the port your prompt gives, with a throwaway
  `ODIN_DATA_DIR` under `/private/tmp/claude-501/-Users-aldrinj-PMS/3ac2ebe6-16ad-4b1e-bbe4-61b8665407f1/scratchpad/`.
  Seed passwords are in `frontend/e2e/helpers.ts`: only against your localhost server;
  never print them. Do not run Playwright unless your prompt gives you a port for it
  (`E2E_PORT=<port> E2E_DATA_DIR=/tmp/odin-e2e-<you>`); write e2e journeys anyway.
- **House rules:** every mutation audited (`audit_log`; the meta-test enforces it);
  any number an admin could change is a policy in `policies.POLICIES`; the customer cut
  is made on the server; new objects declare what externals may see; no hard-coded
  colours (tokens only); shared components (Button, Dialog, Panel, Field, Notice,
  Segmented, LoadFailed, useLoad, useAction, usePref); wording says "rollout" where a
  person reads about the work; comment style matches the surrounding code; a new page or
  control gets a line in `frontend/e2e/smoke.spec.ts`, a journey in `flows.spec.ts`.
- **Schema:** new tables/columns in `schema.sql` and `db.migrate_db` as the code does it.
  Do NOT bump `db.SCHEMA_VERSION` (the lead bumps it once). A new project-keyed table
  is wired into `reset_data.WIPE_TABLES`, `db.cleanup_soft_deletes`,
  `services/report_data.py` if it is history, and `scripts/seed_uat.py` with a few
  realistic rows (CLAUDE.md "Adding a table"). New permissions go in `constants`
  PERMISSIONS with sensible role defaults.
- **Tests:** new Python tests in the NEW module your prompt names (use `FixBase` from
  `test_fix_logic.py`); freeze the clock (no test may depend on the weekday or month).
  Front-end tests next to the code. When you add or change a route, regenerate the
  goldens deliberately at the end (`ODIN_WRITE_GOLDEN=1 venv/bin/python -m unittest
  test_v18_meta.GoldenRoutesTestCase`; API contract: `ODIN_WRITE_CONTRACT=1 ...
  test_v18_meta.ApiContractTestCase`) and say so. Add your new test module to the three
  lists (`.github/workflows/ci.yml`, `scripts/ci_local.sh`, the "Python tests" line in
  CLAUDE.md) — `test_v18_meta` fails otherwise.
- **Checks before you report:** your module; then the full Python list from CLAUDE.md
  plus every new `test_v2_*.py`; `cd frontend && npx tsc -b --noEmit && npm run lint &&
  npm test` (lint fails above its `--max-warnings` cap: add none). Others' in-progress
  edits may cause unrelated failures: report them, don't fix them.
- **Report** concisely: what you built (file:line), decisions you took, tests added,
  anything deferred and why, anything the user must decide, every file you modified.
