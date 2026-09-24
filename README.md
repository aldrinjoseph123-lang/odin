# Odin

Project lifecycle tracker for a cybersecurity company: one place to follow every
product and service rollout from purchase order to hypercare — stages, tasks,
documents, SLAs, and a per-project link for the customer and the vendor.

Deliberately **not** a billing tool. Commercials live elsewhere; Odin tracks
delivery.

[![CI](https://github.com/aldrinjoseph123-lang/odin/actions/workflows/ci.yml/badge.svg)](https://github.com/aldrinjoseph123-lang/odin/actions/workflows/ci.yml)

## What it does

- **Flow** — the first screen: every active rollout as a row with its own stage stepper, stuck rows first; the selected rollout drawn as a flowchart with its tasks under each stage, next-up, ETA, team, and a one-click advance.
- **Per-project stages** — templates in Settings, copied at creation, then owned by the project: add, rename, reorder, delete, SLAs. Cycle-time analytics per template, SLAs set by hand or from measured averages.
- **Team and roles** — every project has a project manager (the owner), coordinators, sales, contractors, resellers and customer contacts. Project roles bind staff: only the PM moves stages; coordinators run tasks and documents; everyone else reads and comments.
- **External access** — partners and customers are invited by email and sign in with a one-time link, no password. They see only the projects they are on.
- **Tasks** — per stage, tagged to a person, worked from the flow screen; the person tagged may tick their own task whatever their role.
- **Reports** — a draft built from the timeline, tasks, notes and documents; the PM edits it as text and saves numbered versions. Partners see saved versions only. Plus the all-projects table, both printable.
- **Notifications and approval** — a stage change emails every participant; per project, the customer contact can be asked to approve each move.
- **Projects** — create from a client PO (required), duplicate, edit, documents, notes, search, sort, filters, CSV export.
- **Evidence** — append-only audit trail with actor and client IP, CSV export; user list with created / last-sign-in for access reviews; editable permission matrix.
- **Microsoft 365** (optional) — email and Teams notifications, OneDrive mirror of uploads and nightly backups.
- **Guest links** (legacy) — the older anonymous per-project links still work until invited accounts replace them.

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
python -m unittest test_app     # 199 tests
```

Front-end iteration: `npm --prefix frontend run dev` on http://localhost:5173 — Vite serves the React pages and proxies everything else to Flask.

## Stack

Flask 3 · SQLite (WAL) · gunicorn · nginx · **React + TypeScript + shadcn/ui** (Vite, Tailwind 4) for the front end. Every signed-in page is React; Flask serves JSON and the same form routes the old pages used (see CLAUDE.md). Only the public guest pages remain Jinja. Three Python runtime dependencies; Node is a build-time dependency only (multi-stage Dockerfile). State is one directory (`ODIN_DATA_DIR`): the database plus `uploads/` and `backups/`.

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
