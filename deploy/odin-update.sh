#!/bin/sh
# Odin's self-update, run by cron on the production server every 5 minutes:
#
#   */5 * * * * $HOME/odin-update.sh >> $HOME/odin-update.log 2>&1
#
# It moves the server to the newest release tag on main (vX.Y.Z). A tag only
# exists once a pull request from dev was merged and CI passed on main (the
# Release workflow creates it), so this never deploys untested code.
#
# Steps: back up, check out the tag, rebuild, preflight. If the rebuild or
# preflight fails it goes back to the previous tag and rebuilds that, and it
# does not retry the failed tag (a newer one is tried when it appears).
# The database only ever gains tables and columns, so the previous release
# runs on it; the pre-update backup is there if data must be restored.
#
# Installed outside the checkout ($HOME/odin-update.sh) because it rewrites
# the checkout while it runs; after a successful update it refreshes itself
# from deploy/odin-update.sh of the new release.
set -u
APP=${ODIN_DIR:-/opt/odin}
STATE=${ODIN_UPDATE_STATE:-$HOME/.odin-update}
mkdir -p "$STATE"
exec 9>"$STATE/lock"
flock -n 9 || exit 0                      # a run is still going

log() { echo "$(date -u +%FT%TZ) $*"; }
cd "$APP" || { log "no $APP"; exit 1; }

git fetch --quiet --tags origin main 2>/dev/null || { log "fetch failed"; exit 1; }
target=$(git describe --tags --abbrev=0 --match 'v[0-9]*' origin/main 2>/dev/null) || exit 0
current=$(git describe --tags --exact-match HEAD 2>/dev/null || echo none)
[ "$target" = "$current" ] && exit 0
[ "$(cat "$STATE/failed" 2>/dev/null)" = "$target" ] && exit 0     # tried and rolled back already
# forward only: never "update" to an older release
if [ "$current" != none ] && [ "$(printf '%s\n%s\n' "$current" "$target" | sort -V | tail -1)" != "$target" ]; then
  exit 0
fi

log "update $current -> $target"
if ! docker compose exec -T app python backup.py >/dev/null 2>&1; then
  log "backup failed: update skipped"; exit 1
fi
log "backup done"

deploy() {
  git checkout --quiet "$1" && docker compose up -d --build --quiet-pull >/dev/null 2>&1 || return 1
  # nginx's config is a file mounted from the checkout: recreate it so a changed config applies
  docker compose up -d --no-deps --force-recreate nginx >/dev/null 2>&1 || return 1
  i=0
  until docker compose exec -T app python preflight.py >/dev/null 2>&1; do   # the app needs a moment after a restart
    i=$((i + 1)); [ $i -ge 12 ] && return 1; sleep 10
  done
}

if deploy "$target"; then
  log "now on $target"
  rm -f "$STATE/failed"
  cp deploy/odin-update.sh "$HOME/odin-update.sh.new" 2>/dev/null && chmod +x "$HOME/odin-update.sh.new" && mv "$HOME/odin-update.sh.new" "$HOME/odin-update.sh"
  docker image prune -f >/dev/null 2>&1
  exit 0
fi

log "$target failed (build or preflight); going back to $current"
echo "$target" > "$STATE/failed"
if [ "$current" != none ] && deploy "$current"; then
  log "back on $current"
else
  log "ROLLBACK FAILED: check the server by hand (docker compose ps, docker compose logs app)"
fi
exit 1
