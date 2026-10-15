# v1.8.0 fix round: shared brief for every agent

Odin (Flask + SQLite JSON API, React 19 + TS + Tailwind v4 + shadcn base-ui SPA in
`frontend/`) at /Users/aldrinj/PMS, branch `dev`. The findings are in
`docs/review-2026-10-14.md` (P2-xx and P3-xx rows, plus "Reviewer 14" advice items
A1..A23, B1..B20). Read **CLAUDE.md** and, for UI work, **DESIGN.md** first. Read the
full row of every finding you own before you start.

## Rules for every agent

- **Own only your files.** Your prompt lists them. Other agents edit other files at the
  same time. If a file you do not own must change, make the smallest edit, re-read the
  file immediately before each edit, and say so in your report. Never revert someone
  else's change.
- **No git.** No commit, stash, checkout, reset or branch. The lead commits.
- **Never** touch `/Users/aldrinj/PMS/odin.db`, `uat-data/`, or ports 5050, 5051, 5099.
  If you must run a server, use only the port your prompt gives you, with a throwaway
  `ODIN_DATA_DIR` under `/private/tmp/claude-501/-Users-aldrinj-PMS/3ac2ebe6-16ad-4b1e-bbe4-61b8665407f1/scratchpad/`.
  Seed passwords are in `frontend/e2e/helpers.ts`: use them only against your localhost
  server and never print them.
- **Do not run Playwright** (`npm run e2e` / `npx playwright test`); the lead runs it.
  You may write or adjust e2e specs in the files you own.
- **House rules:** every mutation audited (`audit_log`); any number an admin could want to
  change is a policy in `policies.POLICIES`; no hard-coded colours (tokens only); shared
  components (Button, Dialog, Panel, Segmented, fieldArea, danger...); toasts for silent
  saves, inline field errors; wording says "rollout" where a person reads about the work;
  comment density and style match the surrounding code. Root-cause fixes, shortest
  correct diff, no speculative abstractions.
- **Schema:** a new table or column goes in `schema.sql`/`migrate_db` as the code does
  today. Do NOT bump `db.SCHEMA_VERSION` (the lead bumps it once). A new table keyed by
  `project_id` or holding per-user secrets must be wired into `reset_data.WIPE_TABLES`,
  the purge cascade in `db.cleanup_soft_deletes`, `services/report_data.py` if it is
  history, and `scripts/seed_uat.py` if UAT needs rows (see CLAUDE.md "Adding a table").
- **Tests:** put new Python tests in the NEW module your prompt names (use test_app's
  harness the way `test_fix_logic.py` does with `FixBase`). Do not add tests to
  `test_app.py`, `test_fix_*.py`, `test_release_safety.py`, `test_scheduler_ops.py`
  unless your prompt says so; fixing an existing test whose old behaviour was the bug is
  allowed (say so). Front-end unit tests go next to the code (`src/lib/*.test.ts`,
  `src/pages/*.test.tsx`).
- **Checks before you report:** your Python module, then the full
  `venv/bin/python -m unittest test_app test_fix_logic test_fix_security test_release_safety test_scheduler_ops <all test_v18_*.py modules that exist>`
  (other agents' in-progress edits may cause unrelated failures: report them, don't fix
  them). Front end: `cd frontend && npx tsc -b --noEmit && npx oxlint && npm test`
  (oxlint baseline 15 warnings: add none).
- **Report** concisely: per finding ID, what changed (file:line), decisions taken, tests
  added, anything deferred and why, anything the user must decide, and the list of every
  file you modified.
