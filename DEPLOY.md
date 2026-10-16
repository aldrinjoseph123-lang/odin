# Deploying Odin

**First production install:** follow [docs/GO_LIVE.md](docs/GO_LIVE.md) — the phased runbook
for a Linux VM behind Cloudflare Tunnel, starting clean. This file is the reference behind it.

## Docker (recommended)

Everything stateful lives in one volume (`odin-data`): `odin.db` plus every
uploaded document. Back that up; nothing else in the stack holds state.

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_hex(32))'   # paste into SECRET_KEY
# put fullchain.pem + privkey.pem in deploy/certs/
docker compose up -d --build
docker compose exec app python preflight.py                 # must report "Ready to serve"
```

Then, immediately:

1. Sign in as `admin` with the password the first boot printed once
   (`docker compose logs app | grep "first admin"`), or set one first with
   `docker compose exec app python scripts/set_password.py`, and change it on the
   Account page. The policy rejects anything containing `changeme`, `password`, `odin`, etc.
2. If the database carries demo projects you don't want, with nothing writing meanwhile:
   `docker compose stop app scheduler && docker compose run --rm --no-deps app python reset_data.py && docker compose start app scheduler`.
3. If you use Microsoft 365, register this deployment's exact callback URI
   (`https://your-host/integrations/callback`) in the Azure app — scheme, host,
   port and path must all match or sign-in fails with `AADSTS50011`.

### What the compose file does

| Service | Role |
|---|---|
| `app`   | gunicorn, 2 workers × 4 threads, `--preload` so `init_db()` runs once before forking |
| `nginx` | TLS termination, serves `/static` directly, proxies everything else |
| `scheduler` | Runs the daily digest, backups, weekly report and nightly audit retention at the times set in Settings (`scheduler.py`). Starts once `app` is healthy; its own health check is a heartbeat in the last 3 minutes. `docker compose logs scheduler` shows each job. |

`PMS_TRUST_PROXY=1` is set for `app` because nginx sits in front: without it
every request appears to come from 127.0.0.1, which would make the audit log
useless and collapse the login rate limiter into a single shared bucket that
one attacker could use to lock out every user.

`SECRET_KEY` is mandatory — `wsgi.py` refuses to boot without it, and the
container entrypoint fails earlier still with a clearer message.

### Proxmox install (Debian 12 VM + Docker)

Use a **VM**, not an LXC container: Docker inside LXC needs nesting and
keyctl workarounds and Proxmox's own guidance is a VM. Sizing for a team of
20–50 with a few hundred projects:

| | Minimum | Comfortable |
|---|---|---|
| vCPU | 1 | 2 |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB + uploads (up to 100 MB per file; the upload policy sets the limit) |
| OS | Debian 12 (bookworm) | same |

The whole stack idles under 300 MB RAM: gunicorn ≈ 120 MB, nginx ≈ 10 MB,
cloudflared ≈ 30 MB, the scheduler container sleeps between minutes.

```bash
# 1. On the VM, as root — Docker from Docker's own repo (Debian's is stale)
apt-get update && apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 2. Code
git clone <your-repo> /opt/odin && cd /opt/odin      # or scp the folder
cp .env.example .env && chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'   # → SECRET_KEY in .env
#    → CLOUDFLARE_TUNNEL_TOKEN in .env (Zero Trust → Networks → Tunnels → Create → token)
#    In the tunnel's Public Hostname tab: odin.yourdomain → HTTP → nginx:80

# 3. Up
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
docker compose exec app python preflight.py                 # must say "Ready to serve"
docker compose ps                                           # app should be "healthy"

# 4. First sign-in at https://odin.yourdomain — admin and the password the first
#    boot printed once (docker compose logs app); you will be forced to set a new
#    password before anything else loads.
```

Then the Cloudflare side below (Access, rate limits). Keep Proxmox's own
`vzdump` of the VM nightly **in addition to** Odin's `backups/` folder — the
VM backup is the disaster recovery, the zip is the quick restore.

Updates are the self-updater's job (below); do not `git pull` on production.

### Public access through Cloudflare

Odin is meant to sit behind Cloudflare Tunnel + Access. Do these before the DNS
record goes live:

1. **Tunnel, no open ports.** Run `cloudflared` beside the stack (a fourth
   compose service or the host package) with a public hostname routed to
   `http://nginx:80`. Remove the `80:80` / `443:443` port mappings; TLS now
   terminates at Cloudflare and nginx needs no certificates. Keep
   `PMS_HTTPS=1` — the cookie must stay `Secure`.
2. **Real client IP.** `deploy/nginx.conf` already forwards
   `CF-Connecting-IP` as `X-Forwarded-For`. Without that the app would record
   the tunnel connector's address for every visitor and one attacker's failed
   logins would lock out everyone.
3. **Access = your MFA/SSO.** Create an Access application for the hostname:
   Allow policy = your Entra ID tenant (MFA enforced in Entra); a **Bypass**
   policy for `/auth/link*` (external partners and customers sign in by
   email link there — Access must not stand in front of it) and for
   `/guest/*` while the old anonymous links are still in use;
   enable *Protect with Access* on the tunnel so nothing skips the check.
4. **WAF + rate limits.** Managed ruleset on. Rate-limit `/login` (5/min per
   IP) and POSTs to `/guest/*` (10/min per IP). Bot Fight Mode on. Consider
   Turnstile on the guest forms.
5. **Health.** Point a Cloudflare health monitor (or any uptime check) at
   `/healthz`. Docker's own `HEALTHCHECK` uses the same endpoint.
6. **Evidence.** Access logs are your sign-in evidence — keep them via Logpush
   or the 18-month API window. Odin's own audit trail is append-only and
   exportable from Settings → Audit Logs → Export CSV.

### Backups and restore

`backup.py` (run by the `scheduler` service at the time set in **Settings →
Backups**, or by "Back up now") always writes `odin-backup-<timestamp>.zip`
(database snapshot, documents, profile pictures and a `manifest.json`) into
`<ODIN_DATA_DIR>/backups/`, restore-tests it (integrity check + every document
present), copies it to the destinations switched on there — OneDrive, a
SharePoint site folder, a network share mounted into the `scheduler`
container — and keeps daily / weekly / monthly copies by the retention set
there, locally and at each destination. Every run, and its restore-test
result, is listed in Settings → Backups. Switch on at least one off-host
destination: a backup on the disk it protects is only half a backup.

A backup by hand (the same restore-tested archive, never a copy of the live
files: committed rows can still sit in the WAL beside `odin.db`):

```bash
docker compose exec app python backup.py                               # app running
docker compose run --rm --no-deps -T app python backup.py --local      # app down
docker compose run --rm --no-deps app ls -l /data/backups              # what is there
```

Archives and their folder are readable by the container's user only (0600,
0700): each holds the whole database, guest tokens included.

**Restore** is in `docs/RUNBOOK.md`, "Restore a backup" (tested; rehearse it quarterly):
the same `.env`, the updater held, the archive unpacked as the container's user.

### AI server (optional)

Odin's AI features use any OpenAI-compatible server (today the shared
`P24-AI` model on the office LAN). Nothing is installed in Odin's containers:
after the release, an admin opens **Settings → AI**, enters the base address
(e.g. `http://192.168.1.238:11434/v1`, better a LAN name) and the model name,
presses **Check**, then **Save**. The `scheduler` service's AI worker then
validates every feature on it; nothing calls the server until it is switched
on there. The app container must be able to reach that address (Docker's
default bridge reaches the LAN); an address outside the private network is
refused unless "Allow an external AI provider" is ticked.

### Upgrades: the self-updater

Production updates itself. `deploy/odin-update.sh`, installed outside the
checkout and run by cron every 5 minutes, moves the server to the newest
release tag on `main` (`vX.Y.Z`, made by the Release workflow once a pull
request from `dev` is merged and CI passed). Each update: a restore-tested
backup (`backup.py --local`), checkout, `docker compose up -d --build`, then
it waits until the app and the scheduler are healthy (the scheduler's check
accepts only a heartbeat from its own container's process, not the previous
container's last beat) and `preflight.py --update` passes (settings an admin
owns only warn there). If any step fails it goes back to the previous tag and
rebuilds that; the admins get a bell notice either way (and "ROLLBACK FAILED"
if going back failed too). A failed backup skips the update and is counted and
told the same way. "Already on the newest tag" is judged by
`~/.odin-update/deployed`, written only after a deploy went through, not by
`git` HEAD, so a reboot between the checkout and `compose up` is finished on
the next run. Migrations run on boot (`init_db()` is idempotent). Never check
out a release by hand on production: the updater moves it back to the newest
tag within 5 minutes. Hold it first (below) if you must.

**Install** (once, as the user that runs Docker, from the checkout in `/opt/odin`):

```bash
cp /opt/odin/deploy/odin-update.sh ~/odin-update.sh && chmod +x ~/odin-update.sh
( crontab -l 2>/dev/null; echo '*/5 * * * * $HOME/odin-update.sh >> $HOME/odin-update.log 2>&1' ) | crontab -
```

After each good update it refreshes `~/odin-update.sh` from the new release.
`ODIN_DIR` (default `/opt/odin`) points it at another checkout.

| | |
|---|---|
| Log | `~/odin-update.log`: one line per step, `now on vX.Y.Z`, `... failed ...; going back to ...`, `ROLLBACK FAILED` |
| Failed tag | `~/.odin-update/failed` holds `tag tries epoch`. A failed tag, or a failed pre-update backup, is tried again after 30 minutes, then 60, at most 3 times; a newer tag is always tried |
| Deployed | `~/.odin-update/deployed` holds the tag whose deploy last went through (build, health, preflight) |
| Retry now | `rm ~/.odin-update/failed` (the next run, within 5 minutes, tries again) |
| Hold updates | `touch ~/.odin-update/hold`; resume with `rm ~/.odin-update/hold` |
| Run now | `~/odin-update.sh` (exits at once if a run is in progress) |
| Admin notices | the updater appends to `DATA_DIR/ops-notices`; the scheduler turns each line into a bell item for the admins within a minute |

Rotate the log (the updater only appends), as root:

```bash
cat > /etc/logrotate.d/odin-update <<'EOF'
/home/*/odin-update.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
EOF
```

Outside production (or with the updater held) an upgrade by hand is
`docker compose exec app python backup.py && git pull && docker compose up -d --build`.

---

## Secrets and security settings

Odin runs only in Docker (above); the image builds the React front end and
the Python app together. The settings that matter for security live in `.env`:

| Variable | Set it to | Why |
|---|---|---|
| `SECRET_KEY` | 64 hex chars: `python3 -c "import secrets; print(secrets.token_hex(32))"` | Signs session cookies. Required: `wsgi.py` refuses to start without it, because the fallback is a publicly known development key. |
| `PMS_HTTPS` | `1` once TLS is live | Adds `Secure` to the session cookie so it never crosses plaintext. |
| `PMS_TRUST_PROXY` | `1` behind nginx (the compose file sets it) | Reads the real client IP from `X-Forwarded-For` for the audit log and the sign-in rate limiter. Only with a proxy really in front, or clients can spoof their own IP. |
| `MS_CLIENT_SECRET` | optional | The Microsoft 365 client secret, if you would rather not store it through Settings → Integrations. |

Keep `SECRET_KEY` stable: two-step sign-in secrets are sealed with a key
derived from it. Changing it signs everyone out and makes every enrolled
authenticator unreadable: people then sign in with a recovery code, or an
admin resets two-step sign-in for them on the Users page.
