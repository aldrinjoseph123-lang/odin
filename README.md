# Odin

Project lifecycle tracker for a cybersecurity company: one place to follow every
product and service rollout from purchase order to hypercare — stages, tasks,
documents, SLAs, and a per-project link for the customer and the vendor.

Deliberately **not** a billing tool. Commercials live elsewhere; Odin tracks
delivery.

[![CI](https://github.com/aldrinjoseph123-lang/odin/actions/workflows/ci.yml/badge.svg)](https://github.com/aldrinjoseph123-lang/odin/actions/workflows/ci.yml)

## What it does

- **Board** — kanban by stage, schedule health (overdue / due soon / stale), stage-SLA breaches, delivery-mode split, recent activity.
- **Projects** — create from a client PO (required), vendor/product/account-manager, tasks with assignees and due dates, deliverable uploads, status history, duplicate, search, sort, CSV export, print reports.
- **Cycle time** — time-in-stage analytics reconstructed from history; set SLAs by hand or from measured averages.
- **Guest links** — two per project: the customer sees progress and can comment; the vendor can also advance the stage one step. Every guest write is named, throttled, audited, and notifies the owner.
- **Roles** — Admin, Member, Contributor (create and comment, never move a stage), Viewer. Editable permission matrix.
- **Evidence** — append-only audit trail with actor and real client IP, CSV export; user list with created / last-login for access reviews.
- **Microsoft 365** (optional) — email and Teams notifications, OneDrive mirror of uploads and nightly backups.

## Run it

**Production** — Docker, Cloudflare Tunnel in front: see [DEPLOY.md](DEPLOY.md) (includes a Proxmox walkthrough).

```bash
cp .env.example .env            # set SECRET_KEY (+ CLOUDFLARE_TUNNEL_TOKEN)
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
docker compose exec app python preflight.py
```

First sign-in is `admin` / `changeme`; you are forced to set a new password before anything else loads.

**Development**

```bash
python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt
npm --prefix frontend ci && npm --prefix frontend run build   # React pages → frontend/dist
python app.py                   # http://localhost:5050 (serves the build for ported pages)
python -m unittest test_app     # 187 tests
```

Front-end iteration: `npm --prefix frontend run dev` on http://localhost:5173 — Vite serves the React pages and proxies everything else to Flask.

## Stack

Flask 3 · SQLite (WAL) · gunicorn · nginx · **React + TypeScript + shadcn/ui** (Vite, Tailwind 4) for the front end, migrating page by page from Jinja — see CLAUDE.md for the rules. Three Python runtime dependencies; Node is a build-time dependency only (multi-stage Dockerfile). State is one directory (`ODIN_DATA_DIR`): the database plus `uploads/` and `backups/`.

## Security posture

CSRF on every mutation · session regenerated on login, 60 min idle / 12 h absolute, revoked on deactivation · per-user+IP login lockout · forced password change on seed and admin resets · upload extension **and** magic-byte checks, downloads forced as attachments · CSP, HSTS, nosniff, no-referrer on guest pages · non-root container that refuses to boot without a secret key. Designed to sit behind Cloudflare Access for MFA/SSO. Full third-party audit and remediation record in the project history; UAT script and results under [docs/](docs/).

## Docs

| | |
|---|---|
| [DEPLOY.md](DEPLOY.md) | Docker, Proxmox, Cloudflare, backups and restore, bare-metal alternative |
| [RBAC.md](RBAC.md) | Roles and permissions |
| [AZURE_SETUP.md](AZURE_SETUP.md) | Microsoft 365 app registration |
| [docs/UAT_SCRIPT.md](docs/UAT_SCRIPT.md) | Re-runnable acceptance script (93 steps) |
| [docs/UAT_RESULTS_2026-09-08.md](docs/UAT_RESULTS_2026-09-08.md) | Latest executed results |
| [CLAUDE.md](CLAUDE.md) | Theme and token architecture for UI work |
