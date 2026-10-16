#!/bin/sh
# Odin's self-update, run by cron on the production server every 5 minutes:
#
#   */5 * * * * $HOME/odin-update.sh >> $HOME/odin-update.log 2>&1
#
# It moves the server to the newest release tag on main (vX.Y.Z). A tag only
# exists once a pull request from dev was merged and CI passed on main (the
# Release workflow creates it), so this never deploys untested code.
#
# Steps: back up, check out the tag, rebuild, then wait until the app and the
# scheduler are healthy (Docker's health checks: /healthz and the scheduler's
# heartbeat) and `preflight.py --update` passes (it gates on what a build can
# break; settings an admin owns, such as the public address, only warn). If a
# step fails it goes back to the previous tag and rebuilds that.
#
# A failed tag is tried again, because a network blip or a slow first boot is
# not a broken release: after 30 minutes, then 60, and at most 3 times
# (ODIN_UPDATE_TRIES, ODIN_UPDATE_BACKOFF seconds). The count is kept in
# $STATE/failed ("tag tries when"); delete that file to try again now. A newer
# tag is always tried. Touch $STATE/hold to pause updates; delete it to resume.
# A failed pre-update backup counts the same way (a full archive every five
# minutes would fill the disk that probably made it fail). Each failure leaves
# a notice that the scheduler turns into a bell item for the admins
# (DATA_DIR/ops-notices), whether or not the rollback worked.
#
# "Already on the newest tag" is judged by $STATE/deployed, written only after
# a deploy went through (build, health, preflight), never by git HEAD: a reboot
# between the checkout and `compose up` leaves old images running on a new HEAD.
#
# The previous release runs on the newer database: it ignores what it does not
# know, and (from v1.7.1, PRAGMA user_version) skips destructive boot steps on
# a newer schema; v1.7.0 and older still delete permission and alert-type rows
# they do not know. The pre-update backup is there if data must be restored.
#
# Installed outside the checkout ($HOME/odin-update.sh) because it rewrites
# the checkout while it runs; after a successful update it refreshes itself
# from deploy/odin-update.sh of the new release. Operators: docs/RUNBOOK.md.
set -u
APP=${ODIN_DIR:-/opt/odin}
STATE=${ODIN_UPDATE_STATE:-$HOME/.odin-update}
TRIES=${ODIN_UPDATE_TRIES:-3}
BACKOFF=${ODIN_UPDATE_BACKOFF:-1800}
mkdir -p "$STATE"
exec 9>"$STATE/lock"
flock -n 9 || exit 0                      # a run is still going
[ -e "$STATE/hold" ] && exit 0            # paused by hand

log() { echo "$(date -u +%FT%TZ) $*"; }
cd "$APP" || { log "no $APP"; exit 1; }

# A bell notice for the admins, read by the scheduler's next pass. A one-off
# container like the backup, so it works while the app is down.
tell_admins() {
  echo "$1" | docker compose run --rm --no-deps -T app sh -c 'cat >> "${ODIN_DATA_DIR:-/data}/ops-notices"' >/dev/null 2>&1 \
    || log "could not leave a notice for the admins"
}

healthy() {   # Docker's own health checks: the app answers /healthz, the scheduler keeps its heartbeat
  for service in app scheduler; do
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q $service)" 2>/dev/null)" = healthy ] || return 1
  done
}

git fetch --quiet --tags origin main 2>/dev/null || { log "fetch failed"; exit 1; }
target=$(git describe --tags --abbrev=0 --match 'v[0-9]*' origin/main 2>/dev/null) || exit 0
current=$(git describe --tags --exact-match HEAD 2>/dev/null || echo none)
# off a tag (a checkout by hand): roll back to this exact commit if the update fails
previous=$current; [ "$current" = none ] && previous=$(git rev-parse HEAD)
deployed=$(cat "$STATE/deployed" 2>/dev/null || echo none)
if [ "$target" = "$current" ]; then
  [ "$deployed" = "$target" ] && exit 0
  # no record yet (first run of this updater): trust a stack that is up and healthy, once
  [ "$deployed" = none ] && healthy && { echo "$target" > "$STATE/deployed"; exit 0; }
  # else HEAD is on the tag but the deploy never finished: go through it again
fi
# forward only: never "update" to an older release
if [ "$current" != none ] && [ "$(printf '%s\n%s\n' "$current" "$target" | sort -V | tail -1)" != "$target" ]; then
  exit 0
fi
tries=0
if [ -f "$STATE/failed" ] && read -r ftag ftries fwhen < "$STATE/failed" && [ "$ftag" = "$target" ]; then
  tries=${ftries:-1}                                              # an older updater wrote the tag alone
  [ "$tries" -ge "$TRIES" ] && exit 0                             # given up on this tag: a newer one, or delete the file
  [ "$(date +%s)" -lt $(( ${fwhen:-0} + BACKOFF * tries )) ] && exit 0   # not yet: wait before the next try
fi

# the failed file's count and the wording of "again", for a failed backup and a failed deploy alike
record_failure() {
  tries=$((tries + 1))
  echo "$target $tries $(date +%s)" > "$STATE/failed"
  again=$([ "$tries" -lt "$TRIES" ] && echo "tried again in $((BACKOFF * tries / 60)) minutes" || echo "not tried again (try $tries of $TRIES)")
}

log "update $current -> $target"
# A one-off container, so the backup works while the app is down (after a
# failed rollback), and local only: a network share is mounted in the
# scheduler, not here.
if ! docker compose run --rm --no-deps -T app python backup.py --local >/dev/null 2>&1; then
  record_failure
  log "backup failed: update to $target skipped; $again"
  tell_admins "The update to Odin $target was skipped because the backup before it failed. It is $again. Check the free disk space (docs/RUNBOOK.md, \"Disk full\")."
  exit 1
fi
log "backup done"

deploy() {
  git checkout --quiet "$1" && docker compose up -d --build --quiet-pull >/dev/null 2>&1 || return 1
  # nginx's config is a file mounted from the checkout: recreate it so a changed config applies
  docker compose up -d --no-deps --force-recreate nginx >/dev/null 2>&1 || return 1
  i=0
  # the app needs a moment after a restart, and the scheduler starts once the app is healthy
  until healthy && docker compose exec -T app python preflight.py --update >/dev/null 2>&1; do
    i=$((i + 1)); [ $i -ge 18 ] && return 1; sleep 10
  done
}

if deploy "$target"; then
  log "now on $target"
  rm -f "$STATE/failed"
  echo "$target" > "$STATE/deployed"
  # refresh this script from the release, unless the new copy does not even parse
  cp deploy/odin-update.sh "$HOME/odin-update.sh.new" 2>/dev/null && sh -n "$HOME/odin-update.sh.new" && chmod +x "$HOME/odin-update.sh.new" && mv "$HOME/odin-update.sh.new" "$HOME/odin-update.sh"
  docker image prune -f >/dev/null 2>&1
  docker builder prune -f --filter until=168h >/dev/null 2>&1   # build cache older than a week
  exit 0
fi

record_failure
log "$target failed (build, health or preflight); going back to $previous; $again"
if deploy "$previous"; then
  log "back on $previous"
  echo "$previous" > "$STATE/deployed"
  tell_admins "The update to Odin $target failed and the server went back to $previous. It is $again. Details: ~/odin-update.log on the server (docs/RUNBOOK.md)."
else
  log "ROLLBACK FAILED: check the server by hand (docker compose ps, docker compose logs app)"
  tell_admins "ROLLBACK FAILED: the update to Odin $target failed and going back to $previous failed too. Check the server by hand now (docs/RUNBOOK.md)."
fi
exit 1
