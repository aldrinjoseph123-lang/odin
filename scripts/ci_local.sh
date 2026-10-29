#!/bin/sh
# What CI runs (.github/workflows/ci.yml), on this machine: the release gate while GitHub Actions is
# unavailable (billing), and a fast way to see a pull request's checks before pushing.
#
#   scripts/ci_local.sh              everything below, in CI's order
#   scripts/ci_local.sh lint vitest  only the steps named
#   steps: python updater audit map lint vitest build e2e perf docker
#
# Exits non-zero if any step failed, and says which. Needs the repo's venv (or PYTHON=...),
# node 22 with `npm ci` done in frontend/, Chromium for Playwright (`npx playwright install chromium`),
# and Docker for the last step (skipped without it). Not covered: Python 3.12 and Linux (CI's);
# the production image has not been built here, so before a release that changes the Dockerfile
# or a lockfile also build it on a throwaway Linux machine (docs/RELEASING.md).
# The @visual goldens are rendered on Linux only, so e2e leaves them out here.
cd "$(dirname "$0")/.." || exit 1
PY=${PYTHON:-venv/bin/python}
[ -x "$PY" ] || PY=python3
ALL="python updater audit map lint vitest build e2e perf docker"
WANT=${*:-$ALL}
failed=""
skipped=""
# Every test_*.py module, named: CI's list and this one are checked against the files by test_v18_meta.
PYTEST="test_app test_fix_security test_fix_logic test_release_safety test_scheduler_ops test_v18_identity test_v18_notify test_v18_projects test_v18_ops test_v18_client test_v18_leftovers test_v18_infra test_v18_fixes test_v18_resend test_v2_fields test_v2_deps test_v2_switches test_v2_lock test_v2_gates test_v2_intake test_v2_workload test_v2_milestones test_v2_selfserve test_v2_tools test_v2_rules test_v2_notify test_v2_lead test_v2_integrate test_v2_fixes test_v2_review test_v2_hardening test_v2_atomic test_v2_friction test_v2_approver test_v2_repeats test_v2_evidence test_v18_meta"

want() { case " $WANT " in *" $1 "*) return 0 ;; esac; return 1; }
step() {   # step <name> <description> <command...>
  name=$1; label=$2; shift 2
  want "$name" || return 0
  printf '\n==> %s: %s\n' "$name" "$label"
  "$@"; code=$?
  case $code in   # 99 = the step could not run here (docker missing): neither a pass nor a failure
    0) echo "ok   $name" ;;
    99) echo "skipped $name"; skipped="$skipped $name" ;;
    *) echo "FAIL $name"; failed="$failed $name" ;;
  esac
}
in_frontend() { (cd frontend && "$@"); }

serve_and_measure() {
  # Lighthouse needs the app running on the seeded data the Playwright run left behind (as CI does)
  ODIN_DATA_DIR=${E2E_DATA_DIR:-/tmp/odin-e2e} SECRET_KEY=e2e-not-secret PORT=5099 "$PY" -c "from app import app; app.run(host='127.0.0.1', port=5099)" >/dev/null 2>&1 &
  server=$!
  i=0
  while [ $i -lt 30 ]; do curl -fsS http://127.0.0.1:5099/healthz >/dev/null 2>&1 && break; i=$((i + 1)); sleep 1; done
  (cd frontend && node e2e/perf.mjs)
  code=$?
  kill "$server" 2>/dev/null
  return $code
}

audit() {
  code=0
  if "$PY" -m pip_audit --version >/dev/null 2>&1; then
    # The pins production runs (Python >= 3.10): drop the lines meant only for an older local interpreter and
    # the markers on the rest. Fully pinned, so no resolving (which would try to install them in this Python).
    pins=$(mktemp)
    grep -v 'python_version < "3\.10"' requirements.txt | sed 's/; *python_version >= "3\.10"//' > "$pins"
    echo "auditing requirements.txt as pinned for Python >= 3.10 (production's), not this interpreter's"
    "$PY" -m pip_audit --no-deps --disable-pip -r "$pins" || code=1
    rm -f "$pins"
  else echo "pip-audit is not installed in this Python (pip install pip-audit): skipped"; fi
  in_frontend npm audit --omit=dev --audit-level=high || code=1
  return $code
}

docker_build() {
  command -v docker >/dev/null 2>&1 || { echo "docker not found: skipped (build the image on a Linux machine before a release that changes the Dockerfile or a lockfile)"; return 99; }
  docker build -t odin:ci-local . || return 1
  docker run --rm odin:ci-local true && { echo "started without SECRET_KEY: the entrypoint guard is broken"; return 1; }
  return 0
}

step python  "unit tests"                       "$PY" -u -m unittest $PYTEST
step updater "server updater self-check"        sh deploy/test-odin-update.sh
step audit   "dependency advisories"            audit
step map     "system map matches the last commit" python3 scripts/build_system_map.py --check
step lint    "oxlint"                           in_frontend npm run lint
step vitest  "vitest (units, pages, API contract)" in_frontend npm test
step build   "tsc -b (strict: app, scripts, e2e) and vite build" in_frontend npm run build
step e2e     "Playwright (smoke, journeys, axe, keyboard)" in_frontend npx playwright test --grep-invert @visual
step perf    "Lighthouse budget and bundle ceiling" serve_and_measure
step docker  "image builds and refuses to start without SECRET_KEY" docker_build

echo
if [ -n "$failed" ]; then echo "ci_local: FAILED:$failed"; exit 1; fi
if [ -n "$skipped" ]; then echo "ci_local: steps passed, SKIPPED (not run, not checked):$skipped"; exit 0; fi
echo "ci_local: all steps passed"
