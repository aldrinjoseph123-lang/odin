# Odin runbook

Short steps for the incidents that need a person on the server. Everything runs
on the production VM (`ssh <you>@192.168.1.237`, then `cd /opt/odin`) as the
user that owns the checkout and runs Docker, unless it says "Proxmox host".
`.env` there sets `COMPOSE_FILE`, so a plain `docker compose …` uses the right
files. Background: `DEPLOY.md` (install, backups, the self-updater) and
`docs/GO_LIVE.md`.

A quick look at health from the VM (works with every compose overlay):

```bash
docker compose ps                                   # every service "running (healthy)"?
docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read().decode())"
```

`/healthz` answers `ok` and three lines (database, scheduler heartbeat, free
disk), or `503 down` when the database cannot be read or written.

## Uptime check (set up once)

Odin tells the admins in the bell about failed jobs, stale backups, a nearly
full disk and failed updates, but nothing inside Odin can say that Odin is down.
Watch it from outside, either:

- **Cloudflare:** Notifications → Add → *Health Checks* (needs a health check on
  the zone: Traffic → Health Checks → `https://odin.<domain>/healthz`, expected
  code 200, response body contains `ok`, every 60 s, from two regions) → email
  the admins.
- **Uptime Kuma** on the Proxmox host (an LXC or a container): an *HTTP(s) -
  Keyword* monitor on `https://odin.<domain>/healthz`, keyword `ok`, interval
  60 s, retries 2, notification by email or Teams.

The Access policy keeps `/healthz` reachable without a sign-in (GO_LIVE Phase 3,
policy *Health*). It shows no names and no data.

## Odin is down

1. Look: `docker compose ps`. A service not running or `unhealthy`:
   ```bash
   docker compose logs --tail=200 app          # or scheduler, nginx
   docker compose up -d                        # start what stopped
   ```
2. Running and healthy, but the site does not load from outside: the tunnel.
   ```bash
   sudo systemctl status cloudflared           # cloudflared on the host (docker-compose.host-tunnel.yml)
   sudo systemctl restart cloudflared
   docker compose logs --tail=50 cloudflared   # or as a container (docker-compose.cloudflare.yml)
   ```
3. `/healthz` says `down` (503): the database cannot be written. A full disk is
   the usual cause (below). Otherwise check the file:
   `docker compose exec app python preflight.py` ("Database opens and passes
   SQLite's quick check"). Damaged: restore the last good backup (below).
4. An update may be in progress (it rebuilds for a minute or two):
   `tail -n 5 ~/odin-update.log`.

## An update was rolled back

The bell says "Odin's update failed" and `~/odin-update.log` has
`vX failed (build, health or preflight); going back to vY`. The server runs the
previous release; nothing is lost.

```bash
tail -n 30 ~/odin-update.log
cat ~/.odin-update/failed                    # "tag tries epoch"
git -C /opt/odin describe --tags             # the release running now
```

The updater tries that tag twice more, after 30 and 60 minutes, and a newer tag
at once. The bell can also say the update "was skipped because the backup before
it failed": nothing was changed, and the cause is usually a full disk ("Disk
full", below); the skipped tag counts a try like any failed one. A blip (network, a slow first boot) clears by itself. To find out why
it fails, hold the updater and try the release by hand:

```bash
touch ~/.odin-update/hold
git checkout vX && docker compose up -d --build
docker compose ps; docker compose logs --tail=200 app
docker compose exec app python preflight.py --update
git checkout vY && docker compose up -d --build      # back to the good one
rm ~/.odin-update/hold
```

Retry now (after a fix on the server, such as freeing disk): `rm ~/.odin-update/failed`.

## ROLLBACK FAILED

The update failed and going back failed too: Odin may be down. Hold the
updater, then put the last good release back by hand.

```bash
touch ~/.odin-update/hold
grep -E "now on|back on" ~/odin-update.log | tail -n 3      # the last good tag
git checkout <last good tag>
docker compose up -d --build
docker compose ps
docker compose exec app python preflight.py
```

Still failing: read `docker compose logs --tail=200 app`. If the database is
the problem, restore the backup the updater made just before (trigger
`before update`, the newest `odin-preupdate-<timestamp>.zip` in `/data/backups`;
the newest three are kept apart from the daily copies, Settings → Backups →
Copies kept; see "Restore a backup"). When
Odin is up again: `rm ~/.odin-update/hold`. The updater will then retry the
failed tag after its wait; to skip that release, keep the hold until a newer
tag exists.

Back on v1.7.1 from v1.8.0 or later: recovery codes made on v1.8.0 (salted)
do not work on v1.7.1. Anyone who made new codes since the upgrade makes them
again on their Account page; someone who has lost their phone meanwhile needs
an admin to reset two-step sign-in on the Users page.

## Going back to an older release by hand

With the updater held: `git checkout <previous tag> && docker compose up -d --build`.
The database stays on the newer schema, and older code ignores the tables and columns
it does not know. From v1.7.1 on the database carries a schema number
(`PRAGMA user_version`, `db.SCHEMA_VERSION`); code older than the database sees it
is a rollback, skips its destructive boot steps and keeps the newer release's
settings (permissions, alert types), and preflight shows a **WARN** (not a FAIL, so
the rollback still boots). Going back to **v1.7.0 or earlier** is different: those
releases delete, on every boot, permission and alert-type settings they do not
know, so after rolling back past v1.7.0 restore the pre-update backup if those
settings matter ("Restore a backup"). Restore that backup too whenever the newer
release's data itself must go.

## SECRET_KEY lost

The key lives only in `/opt/odin/.env` (and the VM's own backups; keep a copy
in the password manager). Odin's backups do not contain it. First look for it:
an older VM snapshot or `vzdump` on the Proxmox host. If it is really gone:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'   # put it in .env as SECRET_KEY=
docker compose up -d
```

What breaks, and the fix for each:

- Everyone is signed out: they sign in again.
- Two-step sign-in secrets cannot be read: people sign in with a recovery
  code, or an admin resets two-step sign-in on the Users page.
- Microsoft 365: Settings → Integrations → Connect again; re-enter the
  Microsoft sign-in client secret and the AI key if they were set; paste the
  Teams webhook again (Settings → Notifications).

A key that leaked (not lost) is rotated without breaking anything:
`docs/GO_LIVE.md`, "Rotating `SECRET_KEY`".

## Restore a backup

Rehearse it quarterly. Keep the same `.env`: the `SECRET_KEY` in it seals the
Microsoft 365 tokens, client secrets, the AI key and every two-step secret in
the database, and a restore under another key leaves them unreadable (people
then sign in with recovery codes and an admin reconnects Microsoft 365). Hold
the updater first so it does not rebuild mid-restore, stop the app and the
scheduler, unpack, start.

```bash
touch ~/.odin-update/hold
docker compose run --rm --no-deps app ls -lt /data/backups | head    # pick one
docker compose stop app scheduler
docker compose run --rm --no-deps app sh -c \
  'cd /data && rm -rf odin.db odin.db-wal odin.db-shm uploads avatars brand && python -m zipfile -e /data/backups/odin-backup-<timestamp>.zip . && rm -f manifest.json'   # or odin-preupdate-<timestamp>.zip
docker compose start app scheduler
docker compose exec app python preflight.py
rm ~/.odin-update/hold
```

For an archive from elsewhere, copy it into the current folder and use
`-v "$PWD:/restore:ro"` on the `docker compose run` and `/restore/odin-backup-<timestamp>.zip`
as the path. The command runs as the container's own user, so the files keep the right
owner. The archive holds `odin.db`, `uploads/`, `avatars/`, `brand/` (document template
logos), `audit-archive/`, `signoff-archive/` (the signed record of deleted rollouts: PDF, JSON, paper copy) and `manifest.json`; `init_db()` runs on boot and applies any
migrations the archive predates. To take a backup by hand first: `DEPLOY.md`, "Backups and restore".

Everything written after that backup is gone; the audit log in the archive is
the record up to it.

## Disk full

The bell says "Odin's disk is nearly full" (below the threshold in Settings →
Backups → Disk space, 10% by default), or saves and backups fail.

```bash
df -h /                                  # the VM's disk
docker system df                         # images, build cache, volumes
docker builder prune -f && docker image prune -f      # old builds: usually the most
docker compose run --rm --no-deps app du -sh /data/backups /data/uploads /data/audit-archive /data/signoff-archive
sudo journalctl --vacuum-size=200M
```

Local backups beyond the retention go on the next backup; lower Settings →
Backups → Copies kept to keep fewer (with an off-host destination switched on,
the local copies are the convenience, not the only copy). Still short: grow the
disk on the **Proxmox host** (`qm resize <vmid> scsi0 +20G`), then in the VM
`sudo growpart /dev/sda 1 && sudo resize2fs /dev/sda1` (check the device names
with `lsblk` first). When space is back, an update that failed on it is retried
with `rm ~/.odin-update/failed`.

## The schedule has stopped

The bell says "Odin's schedule has stopped": the scheduler is alive (its
heartbeat thread sent the notice) but its clock loop has not moved for longer
than Settings → Backups → Stuck schedule (3 hours by default). A job is
hanging, most often a backup copying to a network share that stopped
answering; the digest, alerts, backups and housekeeping wait behind it.

```bash
docker compose logs --tail=100 scheduler     # the last job it started
docker compose restart scheduler             # stops it (two-minute grace), starts it afresh
```

A backup killed this way leaves only a `.partial-*` file, removed by the next
run. Fix what hung (remount the share, or switch that destination off in
Settings → Backups) before the next scheduled backup.
