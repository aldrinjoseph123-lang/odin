# Releasing Odin

The rule (CLAUDE.md): work goes on `dev`; the user tests it on UAT (port 5051) and approves;
a pull request **dev -> main** that raises `VERSION` is the release. Merging it is the go-ahead
for production: CI runs on main, the Release workflow tags the commit `v<VERSION>`, and the
server's cron (`~/odin-update.sh`, every 5 minutes) moves to the newest tag. Use a merge commit,
not a squash, so the change log keeps every commit. Nothing is pushed straight to main
(`scripts/pre-push` refuses it; install it once with
`ln -sf ../../scripts/pre-push .git/hooks/pre-push`).

## Checklist

1. **Dev is what the user approved.** UAT on 5051 was tested, the user said go.
2. **Schema.** A new table, column, permission or alert type raises `db.SCHEMA_VERSION`. A table keyed by
   `project_id` is in `reset_data.WIPE_TABLES`, the purge cascade in `db.cleanup_soft_deletes`, and
   `scripts/seed_uat.py` when UAT needs rows (CLAUDE.md, "Adding a table").
3. **Generated guards are current.**
   - Routes or permissions changed: regenerate the role x route table, read the diff, commit it.
     `ODIN_WRITE_GOLDEN=1 venv/bin/python -m unittest test_v18_meta.GoldenRoutesTestCase`
   - An API answer changed shape: `ODIN_WRITE_CONTRACT=1 venv/bin/python -m unittest test_v18_meta.ApiContractTestCase`,
     then make `frontend/src/lib/api.ts` match until `npm --prefix frontend test` passes.
   - The look changed: refresh the `@visual` goldens with the CI workflow's `update_snapshots` input and commit the artifact.
4. **Version, then map, in that order.** Set `VERSION` and **commit it alone first**. Then run
   `python3 scripts/build_system_map.py` (it reads the last commit and refuses an uncommitted `VERSION`),
   edit the hand-written parts of `docs/system-map.html` if the release changed how Odin runs, moves or
   exposes data (fixed loopholes keep their number and get `fixed: "vX.Y.Z"`; bump `MAP_STAMP`), commit, and
   republish the artifact (CLAUDE.md, "System map"). `python3 scripts/build_system_map.py --check` must exit 0;
   CI runs it on every pull request into main.
5. **Tests pass.** On GitHub: CI green on the pull request. While Actions is unavailable (billing), run it here:
   `scripts/ci_local.sh` (everything CI runs: Python suites, the updater self-check, advisories, map check, oxlint,
   vitest incl. the API contract, `tsc -b` strict over the app, scripts and e2e specs, Playwright without `@visual`,
   Lighthouse and the bundle ceiling, Docker build if Docker is installed, else reported as skipped, not ok; the Python
   advisories are checked against the >= 3.10 pins production runs). It exits non-zero on any failure and names the step. Paste its last lines in the pull request.
6. **A Linux build when the image can change.** If the Dockerfile, a compose file, `requirements.txt` or a
   lockfile changed, build the image on a throwaway Linux machine and boot it with a `SECRET_KEY`: nothing on the
   development Mac builds it, and Python 3.12 / Linux are only proven by CI. Ask the user for the machine.
7. **Open the pull request** dev -> main with `.github/PULL_REQUEST_TEMPLATE.md` filled in. The user merges it
   (or tells you to), with a merge commit.
8. **Tag.** The Release workflow tags `v<VERSION>` when CI passes on the merged commit. If Actions is
   unavailable, tag by hand on the merged commit after `scripts/ci_local.sh` passed on it:
   `git tag -a vX.Y.Z -m "Odin X.Y.Z: <title>" <merge commit>` and `git push origin vX.Y.Z`
   (pushing a tag is not a push to main; the hook allows it).
9. **The server follows** (`DEPLOY.md`, "Upgrades: the self-updater"). Never SSH in to check: ask the user to read
   `~/odin-update.log` and the version shown in the app.

## The Python lock

`requirements.txt` is the human-edited list of exact pins; `requirements.lock` is generated from it and holds the
sha256 of every file the production image installs (Python 3.12, Linux x86_64, glibc). The Dockerfile installs with
`pip install --require-hashes -r requirements.lock`, so a changed or substituted package fails the build.

After **any** change to `requirements.txt`, regenerate and commit both together:

    python3 scripts/make_lock.py            # needs network and pip >= 23 (any OS: it downloads Linux wheels)
    python3 scripts/make_lock.py --check    # exit 1 = the lock is stale (test_v2_small also fails)

The script runs `pip download --no-deps --only-binary=:all: --python-version 3.12 --implementation cp --abi cp312
--platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64` on the pins for
Python >= 3.10 and hashes each file. It stops when a package has no wheel for that target (an sdist would need a
compiler in the image, so decide that deliberately; today every package has a wheel). The lock covers x86_64 only: an
arm64 build (Apple Silicon `docker build`) is refused until a second platform is added to `TARGET`. A transitive
package missing from `requirements.txt` shows up as a failed image build (`--require-hashes` refuses a dependency
it holds no hash for), which step 6 below exercises.

## Rolling back

Tag the previous good commit as the next patch version from a branch that reverts the change, and release it the
same way. The server never moves to an older tag by itself except to undo its own failed update. Going back by
hand, and what an older release does to a newer database: `docs/RUNBOOK.md`.
