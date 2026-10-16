<!-- Branch rule (CLAUDE.md): work lands on dev; a pull request dev -> main with VERSION raised is the
     release, and merging it is the go-ahead for production. Merge with a merge commit, not squash. -->

## What this release changes
<!-- One line per user-visible change; the change log is built from the commits. -->

## Before merging
- [ ] The user tested dev on UAT (port 5051) and approved this release.
- [ ] `VERSION` is raised **and committed first**; `python3 scripts/build_system_map.py` was run after that commit, and `docs/system-map.html` is committed and republished (`MAP_STAMP` bumped, fixed loopholes marked).
- [ ] Tests run: CI is green, or (while GitHub Actions is unavailable) `scripts/ci_local.sh` passed on this branch. Paste its last lines:
  ```
  ```
- [ ] If the **Dockerfile, a compose file, `requirements.txt` or a lockfile** changed: the image was built on a throwaway Linux machine (nothing here builds it), and booted with a `SECRET_KEY`.
- [ ] If a table, column, permission or alert type was added: `db.SCHEMA_VERSION` is raised, and a project-keyed table is wired into `reset_data.WIPE_TABLES`, the purge cascade and `scripts/seed_uat.py`.
- [ ] If a route or its permission changed: `tests/golden_routes.json` was regenerated and the diff read. If an API answer changed shape: `frontend/src/lib/__contract__/` was regenerated and `api.ts` still matches (`npm --prefix frontend test`).
- [ ] If the look changed: the `@visual` goldens were refreshed (CI `update_snapshots`) or the change is known to leave them as they are.

## After merging
- [ ] The Release workflow tagged `v<VERSION>` (or the tag was made by hand: `docs/RELEASING.md`).
- [ ] The user confirmed the server moved to the tag (`~/odin-update.log`).
