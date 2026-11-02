<p><img src="docs/brand/odin-logo-ink.svg" alt="Odin" height="48"></p>

# Odin by Protect24x7

**Every project. On watch.** Brand guide: [docs/BRAND.md](docs/BRAND.md).

Project lifecycle tracker for a cybersecurity company: one place to follow every
product and service rollout from purchase order to sign-off and close: stages, plan
and baseline, tasks, risks, documents, SLAs, reports, and a link for the customer and
the vendor. Local AI drafts and proposes; people decide.

Deliberately **not** a billing tool. Commercials live elsewhere; Odin tracks
delivery. The product statement is [PRODUCT.md](PRODUCT.md).

[![CI](https://github.com/aldrinjoseph123-lang/odin/actions/workflows/ci.yml/badge.svg)](https://github.com/aldrinjoseph123-lang/odin/actions/workflows/ci.yml)

## What it does

- **Flow** — the first screen: every active rollout as a row with its own stage stepper, stuck rows first; the selected rollout drawn as a flowchart with its tasks under each stage, next-up, ETA, team, and a one-click advance. Beside the list: a **Kanban** by stage (a card moves only to its next stage), a **Gantt** of every rollout and its stages, and a **Calendar** (Month, Week, Agenda).
- **Dashboard** — the home page: widgets on a grid (needs attention, headline numbers with trends, timeline, schedule, team, alerts, cycle time, custom metrics), arranged by an admin as the default and by each person for themselves.
- **Per-project stages** — templates in Settings, copied at creation, then owned by the project: add, rename, reorder, delete, SLAs. Working-day counts (public holidays in Settings). Cycle-time analytics per template, SLAs set by hand or from measured averages.
- **Plan, baseline and RAID** — planned dates per stage, frozen as a baseline on first save, every later move logged with its reason; a forecast; health read as On track / At risk / Off track with its reasons; a register of risks, issues, decisions and blockers.
- **Team and roles** — five global roles (Admin, Member, Contributor, Viewer, External) with an editable permission matrix, and a project role on every rollout (project manager, sales, coordinator, contractor, reseller, customer). Project roles bind staff: only the PM moves stages; coordinators run tasks and documents; everyone else reads and comments.
- **External access** — partners and customers are invited by email and sign in with a one-time link, no password. They see only the rollouts they are on.
- **Tasks** — per stage, tagged to a person, worked from the flow screen and My work; the person tagged may tick their own task whatever their role. People pages show load and recent work.
- **Reports** — a rollout report (internal and customer cut) drafted from the numbers, edited by the PM and saved as numbered versions; a portfolio report; both as PDF, with document templates for the look. A weekly report goes out by email and Teams.
- **Scope and sign-off** — the agreed scope, and a sign-off document the customer e-signs and we countersign; closing a rollout waits for it. The PDF certificate carries both signatures and a fingerprint.
- **Notifications and approval** — a bell for everything; email and a card in each staff member's Teams chat (the "Odin PMS" app) by topic; sent through an outbox with retries. Per rollout, one named customer approver can be asked to approve each stage move; a decline pauses the stage until they approve or the project manager overrides with a reason. Eight alert types, four of them bottlenecks (approval waiting, blocker open, task with no owner, customer task overdue).
- **AI (local)** — fourteen features on one OpenAI-compatible server inside the office network (weekly words, risks proposed, why amber, portfolio narrative, SOW to plan, chase drafts, morning brief, catch me up, ask this rollout, meeting notes to tasks, lessons and more). Queued by the scheduler, never in a web request; each feature must pass validation first; output is a suggestion a person accepts through the normal audited route. **Lessons** library with similar rollouts.
- **Projects** — create from a client PO (required), duplicate, edit, documents, notes, search, sort, filters, CSV export.
- **Evidence** — append-only audit trail with actor and client IP, CSV export, retention with an archive; user list with created / last-sign-in for access reviews; read-only API tokens ([docs/API_V1.md](docs/API_V1.md)).
- **Sign-in** — Microsoft (Entra ID) for staff, with an emergency password for flagged accounts; password accounts get two-step sign-in (authenticator app and recovery codes); sign-up links with admin approval.
- **Microsoft 365** (optional) — email and Teams notifications, OneDrive and SharePoint copies of uploads and backups.
- **Backups and updates** — scheduled, restore-tested backups; production moves itself to each new release tag and goes back if the update fails.
- **Guest links** (legacy) — the older anonymous per-project links still work until invited accounts replace them; they expire (180 days by default) and an admin can switch them off.

## Run it

**Production** — Docker, Cloudflare Tunnel in front: see [DEPLOY.md](DEPLOY.md) (includes a Proxmox walkthrough).

```bash
cp .env.example .env            # set SECRET_KEY (+ CLOUDFLARE_TUNNEL_TOKEN)
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
docker compose exec app python preflight.py
```

First sign-in is `admin` with the random password printed once in the app's log (`docker compose logs app`), or the one in `ODIN_ADMIN_PASSWORD` if you set it; you are forced to set a new password before anything else loads.

**Development**

```bash
python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt
npm --prefix frontend ci && npm --prefix frontend run build   # React pages → frontend/dist
python app.py                   # http://localhost:5050 (serves the build for ported pages)
python -m unittest test_app test_fix_security test_fix_logic
```

Front-end iteration: `npm --prefix frontend run dev` on http://localhost:5173 — Vite serves the React pages and proxies everything else to Flask.

## Stack

Flask 3 · SQLite (WAL) · gunicorn · nginx · **React + TypeScript + shadcn/ui** (Vite, Tailwind 4) for the front end. Every signed-in page is React; Flask serves JSON and the form routes the React pages post to (see CLAUDE.md). Only the public guest pages, the sign-in fallback and the error page remain Jinja. Python runtime dependencies are in `requirements.txt`; Node is a build-time dependency only (multi-stage Dockerfile). State is one directory (`ODIN_DATA_DIR`): the database plus `uploads/` and `backups/`.

## Security posture

CSRF on every mutation · session regenerated on login, 60 min idle / 12 h absolute, revoked on deactivation · per-user+IP login lockout · forced password change on seed and admin resets · upload extension **and** magic-byte checks, downloads forced as attachments · CSP, HSTS, nosniff, no-referrer on guest pages · non-root container that refuses to boot without a secret key. Staff sign in with Microsoft or with a password plus two-step sign-in; Cloudflare Access may sit in front but is not required. Full third-party audit and remediation record in the project history; UAT script and results under [docs/](docs/).

## Docs

| | |
|---|---|
| [DEPLOY.md](DEPLOY.md) | Docker, Proxmox, Cloudflare, backups and restore, the self-updater, security settings |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Incidents: Odin down, a failed update or rollback, a lost key, restoring a backup, a full disk; the uptime check |
| [AZURE_SETUP.md](AZURE_SETUP.md) | Microsoft 365 app registration |
| [docs/UAT_SCRIPT.md](docs/UAT_SCRIPT.md) | Re-runnable acceptance script (93 steps) |
| [docs/UAT_RESULTS_2026-09-25.md](docs/UAT_RESULTS_2026-09-25.md) | Latest executed results (v2 dry run) |
| [docs/UAT_RESULTS_2026-09-08.md](docs/UAT_RESULTS_2026-09-08.md) | v1 results |
| [CLAUDE.md](CLAUDE.md) | Theme and token architecture for UI work |
| [PRODUCT.md](PRODUCT.md) | What Odin is and does today: users, rules, capabilities |
| [docs/DECISIONS.md](docs/DECISIONS.md) | The decisions the owner has made, one dated line each |
| [docs/API_V1.md](docs/API_V1.md) | The read-only `/api/v1` for scripts and reports |
