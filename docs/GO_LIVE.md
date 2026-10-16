# Go-live: Linux VM + Cloudflare Tunnel, clean start

The runbook for the first production install (decided 30 Sep 2026): a
Debian/Ubuntu VM running the Docker stack, reachable only through Cloudflare
Tunnel + Access, starting from an empty database, with Microsoft 365 mail,
sign-in and off-host backups added after go-live (Phase 6). `DEPLOY.md` is
the reference behind each step.

**As deployed on 30 Sep 2026 (v1.0.0):** Ubuntu 26.04 VM, cloudflared installed
on the **host** (`sudo cloudflared service install <token>`, as on the Zeus
server) with the published application route `odin.protect24x7.com →
http://localhost:8080`, `COMPOSE_FILE=docker-compose.yml:docker-compose.host-tunnel.yml`,
and no Cloudflare Access (same as Zeus). The container-cloudflared + Access
variant below remains the alternative.

Work top to bottom; each phase ends with a check. Do not enable the public
hostname until Phase 3's checks pass.

**Until Phase 6 (no mail):** invitations and sign-off requests do not reach
anyone by themselves. The inviter gets the invitation link on screen; for a
sign-off, the project manager uses **Get a sign-in link** on the sign-off page
and sends it (Teams, their own mail). Both are one-time and expire.

---

## Phase 1 — The server

Sizing: 2 vCPU, 2 GB RAM, 20 GB disk (plus room for uploads). Everything
below runs as root (`sudo -i`).

```bash
# 1. Updates and automatic security updates
apt-get update && apt-get -y upgrade
apt-get install -y ca-certificates curl git ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

# 2. Firewall: nothing inbound but SSH (the tunnel connects outbound)
ufw default deny incoming && ufw default allow outgoing
ufw allow OpenSSH            # tighten to your LAN: ufw allow from 192.168.1.0/24 to any port 22
ufw --force enable

# 3. Docker from Docker's own repository
. /etc/os-release            # ID is debian or ubuntu, VERSION_CODENAME e.g. bookworm / noble
install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker run --rm hello-world  # check
```

### The code (private repo → read-only deploy key)

```bash
ssh-keygen -t ed25519 -N "" -C "odin-server" -f /root/.ssh/odin_deploy
cat /root/.ssh/odin_deploy.pub
```

Add that public key on GitHub: repository → Settings → Deploy keys → Add,
**Allow write access unticked**. Then:

```bash
cat >> /root/.ssh/config <<'EOF'
Host github-odin
  HostName github.com
  User git
  IdentityFile /root/.ssh/odin_deploy
  IdentitiesOnly yes
EOF
git clone github-odin:aldrinjoseph123-lang/odin.git /opt/odin
cd /opt/odin && git checkout v1.0.0     # production runs a tag, never a moving branch
```

**Check:** `docker --version`, `ufw status` shows only SSH, `git -C /opt/odin describe --tags` prints `v1.0.0`.

---

## Phase 2 — Cloudflare (dashboard)

1. **Domain** on Cloudflare (nameservers pointed at Cloudflare).
2. **Tunnel:** Zero Trust → Networks → Tunnels → Create (Cloudflared) → name
   `odin` → copy the **token** (for `.env`). Do **not** add the public
   hostname yet.
3. **Access application** (Zero Trust → Access → Applications → Self-hosted),
   domain `odin.<yourdomain>`:
   - Policy *Staff* — **Allow**, include: emails ending in `@<yourdomain>`
     (login method: One-time PIN until Microsoft sign-in exists in Phase 6).
   - Policy *Customer sign-in links* — **Bypass**, path `auth/link*`
     (customers open sign-off and invitation links there; Odin's own
     one-time link is their authentication).
   - Policy *Health* — **Bypass**, path `healthz`.
   - Guest links are switched off in Odin (Phase 3), so `/guest/*` stays behind Access.
4. **Security:** WAF managed ruleset on; rate limiting rule: `/login` POST,
   5 requests / minute / IP → block 10 min; Bot Fight Mode on.

**Check:** the Access application lists three policies in the order Bypass, Bypass, Allow.

---

## Phase 3 — Bring it up (still private)

```bash
cd /opt/odin
cp .env.example .env && chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
nano .env
#   SECRET_KEY=<the value just printed — new, never reused from dev>
#   CLOUDFLARE_TUNNEL_TOKEN=<from Phase 2>
#   COMPOSE_FILE=docker-compose.yml:docker-compose.cloudflare.yml   (uncomment)

docker compose up -d --build
docker compose ps                                  # app healthy, scheduler starting, cloudflared up
docker compose exec app python scripts/set_password.py        # admin's real password, before anything is public
docker compose exec app python preflight.py        # must end with "Ready to serve."
```

Now publish: Cloudflare → the tunnel → **Public Hostname** →
`odin.<yourdomain>` → Service **HTTP** → `nginx:80`.

Sign in at `https://odin.<yourdomain>` (Access PIN, then admin + the new password), then in Settings:

| Where | Set |
|---|---|
| General | Public address `https://odin.<yourdomain>` (links in emails and PDFs), company name, time zone |
| Workflow | Stage SLAs, default stage length, amber/red thresholds, sign-off acceptance statement and handover terms |
| Security → Outside access | **Turn off** the legacy anonymous guest links |
| Settings → templates | Your stage lists (each keeps Sign-off before the last stage) |
| Security | Sign-in link life (`link_minutes`, default 30): raise it (e.g. 240) while mail is off, since links are carried by hand; lower it again in Phase 6 |
| Users | Your staff accounts; hand each their first password privately and have them change it on the Account page (or set it for them with `scripts/set_password.py <username>`) |

**Check:** `curl -s https://odin.<yourdomain>/healthz` starts with `ok` (then the database, scheduler and disk lines); a private
window gets the Access PIN page on `/` but not on `/auth/link/anything`.

---

## Phase 4 — Prove it end to end

With a throw-away project named `GO-LIVE TEST`:

1. Create it; add two scope items; invite your own second address as
   **Customer** (Team → Invite). No mail yet: copy the sign-in link the
   invite shows and open it on your phone, off the office network.
2. Mark the scope delivered, move to Sign-off, send the sign-off. Mail is
   not connected yet, so use **Get a sign-in link** on the sign-off page and
   open that link on the phone; sign as the customer, countersign as admin,
   open the PDF, move to Closed.
3. Delete the project (Undo works for the undo window, 5 minutes by default; the nightly housekeeping then purges it with its files).
4. Settings → Backups → **Back up now**; the run shows the restore test passed.
5. `docker compose ps` — scheduler **healthy**.
6. Snapshot the VM: the known-good point.

---

## Phase 5 — Running it

**Updates** are the self-updater's job: install it once as `DEPLOY.md`, "Upgrades: the
self-updater", says (it also lists the log, the hold and the retry switches). Do not check
out a release by hand: the updater moves the server back to the newest tag within 5 minutes.

**Rolling back** by hand, and the schema number: `docs/RUNBOOK.md`, "Going back to an older
release by hand".

**Watch:** an external uptime check on `/healthz` (`docs/RUNBOOK.md`, "Uptime
check"); the bell, where the scheduler reports failed jobs, stale backups, a
nearly full disk and failed updates; `docker compose logs -f app`.

**Disaster recovery until Phase 6:** Odin's backups sit on the same disk, so keep a
nightly VM backup (Proxmox `vzdump`, or your hypervisor's) on other storage.

**Rotating `SECRET_KEY`** (it leaked, or on a schedule): put a new key in `SECRET_KEY`
and the old one in `SECRET_KEY_FALLBACKS` (comma-separated if there are several), then
`docker compose up -d`. Sessions signed with the old key keep working, and the boot
seals every stored secret (Microsoft 365 tokens, client secrets, the AI key, two-step
secrets) again with the new key. After that one boot, remove `SECRET_KEY_FALLBACKS`
and restart: old sessions end and the old key opens nothing. While the old key is a
fallback it still signs valid sessions, so after a leak remove it as soon as that
first boot is done.

---

## Phase 6 — After go-live

1. Azure app registration (`AZURE_SETUP.md`), redirect URI
   `https://odin.<yourdomain>/integrations/callback` → Settings → Integrations → Connect.
2. Mail on (Settings → Notifications): invitations and sign-off requests reach customers by themselves.
3. Microsoft sign-in for staff (Settings → Security); then switch the Access *Staff* policy to your Entra ID tenant with MFA.
4. Off-host backups: OneDrive or SharePoint (Settings → Backups).
5. Weekly report recipients (Settings → Reports).
