# Branches and releases (30 Sep 2026, the user's call)

All work goes on the **`dev`** branch; never commit to `main` directly. When the
user has tested dev (UAT on port 5051) and approves, open a pull request
**dev → main** that raises `VERSION`; the user merges it (or tells you to).
CI then runs on main and the **Release** workflow (`.github/workflows/release.yml`)
tags that commit `v<VERSION>`; the production server's cron job
(`deploy/odin-update.sh`) moves to the newest tag. Merging the pull request is
the go-ahead for production; nothing else deploys. The steps live in one place
each: **releasing** `docs/RELEASING.md`, **install and the self-updater**
`DEPLOY.md`, **restore and incidents** `docs/RUNBOOK.md`. GitHub's free
plan has no branch protection on this private repository, so the rule is kept by
process. Use merge commits (not squash) so the change log keeps each commit.

# Visual authority

**DESIGN.md is the visual authority for the React front end** (`frontend/`), written
from the built world on 8 Sep 2026 when the user released the previous identity
and chose a light, direct-flowchart UI (convention played straight; craft bar:
Linear, Whimsical/FigJam). Product truth lives in PRODUCT.md. Read both before UI
work; do not reintroduce the retired look (dark nav, 2 px corners) in the UI.

**Brand (27 Sep 2026, the user's call): "Odin by Protect24x7".** Raven mark +
ODIN wordmark (red-struck Ø), tagline "Every project. On watch.", all in
`frontend/src/components/Brand.tsx`; guide in `docs/BRAND.md`. The parent's
black, red `#E11D2E` and Chakra Petch are for **brand surfaces only** (logo,
sign-in/reset/link panel, print header, emails via `graph.EMAIL_SHELL`, error
page, icons). In the app: Chakra Petch page titles and numbered panel labels
(`<h3 data-n>`), never red — red in the UI means overdue.

Tokens live in `frontend/src/index.css` (`:root`): accent-tinted ground, white
cards, ink text, one pastel accent (blue by default) for selection and the
primary action, `--primary-text` for the accent as text, green/amber/red **only**
as state (`--ok/--warn/--bad` + `-soft` and `-line`; `--destructive` for errors
and destructive actions), Inter, `--radius: 1rem`, hairline `--border`. Fonts are
served by Odin (`static/fonts`, 10 Oct 2026), never a third party.

**Themes (27 Sep 2026, the user's call):** each user picks light / dark / follow
the OS and one of eight accents on the Account page (header button cycles the
theme). Dark is `:root[data-theme="dark"]`, accents are `:root[data-accent=…]`,
both set before first paint by the script in `frontend/index.html` and kept in
`localStorage` as `odin.theme` / `odin.accent`; the saved choice lives on the
user row (`users.theme`, `users.accent`). Never hard-code a colour: every
component must read tokens so both themes and every accent follow.

**UI/UX rules (9 Oct 2026, the user's refactoring plan):** six type sizes (11–24 px), spacing on the 4/8 px grid, no card inside a card (tone instead), dark depth by tone not shadow, buttons with a `loading` state, inline field errors (`lib/fieldErrors.ts`), toasts for silent saves (`lib/toast.ts`), receipt rows and chunked lists. Details in DESIGN.md.

**9 Oct 2026 refresh (the user's call):** pastel accents (**blue the default again since 10 Oct**, after the critique found the red accent read as overdue; red and green keep only their fill, their accent text and wash fall back to ink), a straight segmented progress bar, a 72 px header with Log out in the avatar menu, app-wide tooltips (`TitleTips`), a stronger settings-menu selection. Details in DESIGN.md.

**The last Jinja pages keep `static/style.css`:** the guest project page and
the sign-in form's fallback (`templates/base.html`, `guest_project.html`,
`login.html`; `error.html` stands alone). That stylesheet is frozen at what
they use: fix defects only, no new components, no re-theming.

# Admin settings

People pages (`/people`, `/people/<id>`) and My work draw from `services/people.py`; a
note to a colleague is `POST /api/people/<id>/notify` (kind `nudge`, audited).
The home page is `/dashboard` (`home_url()` in `routes/auth.py`: sign-in, `/`
and the logo land there; a user may pick the flow on their Account page,
`users.home`; partners always get the flow). Settings is one side-menu page (`components/SettingsLayout.tsx`), one address
per area: `/settings/general|security|rbac|people|workflow|contacts|documents|automations|notifications|integrations|ai|reports|backups|api|audit|map`
(the menu is `frontend/src/lib/settingsMenu.ts`) plus Users (`/users`) and the Audit log (`/audit-logs`) in the same menu.
Recurring work runs only in `scheduler.py` (its own service), never in a web
worker: the digest (with each person's daily summaries and the customer
chasers), backups, weekly report and nightly housekeeping (audit retention,
purges, partner expiry, the next occurrence of repeating tasks) at policy
times in the workspace time zone; every quarter hour the alert pass, which
also scans for the conditions automations wait on; beside the clock, threads
for the heartbeat, the AI worker and the **outbox**
(queued mail and Teams messages; sign-in links and the signed sign-off PDF go
out inline instead); each pass also checks backup freshness and free disk and
turns the updater's `ops-notices` file into bell items for the admins.
**The dashboard layout is the one admin-set value that is not a policy:**
it is a JSON list of widgets, edited on the dashboard itself (`PUT
/api/dashboard/layout/default`, audited) and kept in the settings table under
`dashboard.layout`; a user's own arrangement lives on their row
(`users.dashboard_layout`). The widget catalogue, defaults and validation are
`services/dashboard.WIDGETS` / `normalize_layout`.
**Any value an admin may change is a policy:** add it to `policies.POLICIES`
(area, kind, default, limits, label, help; kinds int, bool, choice, multi, text,
url, domains, emails, time, dates), read it with `policy("key")`
(pass `db` outside an app context), and the settings page draws, validates
(`save_policies`, one audited route `/settings/policies/<area>`) and
explains it. Never hard-code a number an admin could reasonably want to change.
**Sign-in paths:** password sign-in ends in `routes/auth.finish_login` after the
two-step check (`services/mfa.py`, `/api/login/code`); a new password path must
go through `attempt_login`, never `start_session` directly. Microsoft binds to an existing
account by email only when its password cannot sign in; anyone else links from a signed-in
session (Account → Link Microsoft, `routes/sso.py`). Only an Admin acts on an Admin's account
or the role matrix (`routes/users.admin_only`). Stage lengths and
SLAs count working days through `services/workdays.py`; gaps between dates stay
calendar days.

# Adding a table

A table keyed by `project_id` (or holding per-user secrets) must be wired into
every place that walks the schema, or the next reset leaves rows that attach
themselves to the next project created:
`reset_data.WIPE_TABLES` (children before parents) · the purge cascade in
`db.py` (`cleanup_soft_deletes`, run at boot and nightly by the scheduler) · `services/report_data.py` if it is
project history · `scripts/seed_uat.py` if UAT needs rows · a purge for
anything that only grows (`login_links` is trimmed as links are minted).
**Schema number (15 Oct 2026):** a release that adds a table, column, permission or alert
type raises `db.SCHEMA_VERSION`; boot deletes only names listed in `RETIRED_PERMISSIONS` /
`RETIRED_ALERT_TYPES`, and older code on a newer database skips destructive steps (preflight
warns). Dev and UAT bind to 127.0.0.1 (set `HOST=0.0.0.0` to open them) and, without `SECRET_KEY`, keep
a private key in `DATA_DIR/secret_key`. Python tests: `test_app test_fix_logic test_fix_security
test_release_safety test_scheduler_ops test_v18_identity test_v18_notify test_v18_projects test_v18_ops
test_v18_client test_v18_leftovers test_v18_infra test_v18_fixes test_v18_resend test_v2_fields test_v2_deps test_v2_switches test_v2_lock test_v2_gates test_v2_intake test_v2_workload test_v2_milestones test_v2_selfserve test_v2_tools test_v2_rules test_v2_notify test_v2_lead test_v2_integrate test_v2_fixes test_v2_review test_v2_hardening test_v2_atomic test_v18_meta` (every `test_*.py` is named in `ci.yml` and
`scripts/ci_local.sh` too; `test_v18_meta` fails if one is missing). `scripts/ci_local.sh` runs everything CI
runs, for a release while GitHub Actions is unavailable. Two generated guards fail on drift:
`tests/golden_routes.json` (every route x role) and `frontend/src/lib/__contract__/` (the API answers
`lib/api.ts` reads, checked against its types); `docs/RELEASING.md` says how to regenerate them.
`plan_changes` and `raid_items` (30 Sep 2026) are wired this way; plan dates live
on `project_stages` (`plan_*`, `base_*`). Reports read one structure
(`services/report_data.py` per rollout, `services/portfolio.py` for all) that
the page, the PDF (`services/report_pdf.py`) and the weekly email share; the
customer cut is made on the server, never in the page.
Odin 2.0's tables (Oct 2026) are all defined in `schema.sql` (`migrate_db` only adds
columns), wired as above when they are project-keyed: `task_links`, `task_answers`,
`csat`, `milestones`, `project_field_values`, `rule_runs`, `rollout_watch`. Not
project-keyed, so a reset keeps them as it keeps the templates: `rules`,
`custom_fields`, `template_tasks`. `intake_calls` is a log trimmed to the newest 200
(`services/intake.py`): a reset wipes it, a purge sets its `project_id` to NULL.
`user_activity` (per-user active minutes, trimmed nightly), `signup_links` and
`doc_templates` (not project-keyed) arrived the same day; template logos live in
DATA_DIR/brand, which backups include. Document renderers take a template config
(`services/doc_templates.resolve`); a new section must be added to
`doc_templates.KINDS` and to the renderer's section map.
`scope_items` and `signoffs` (30 Sep 2026) are wired the same way. The sign-off
(`services/signoff.py`, routes in `routes/signoff.py`) gates the terminal stage:
every stage-move path (`change_stage`, the vendor guest link) calls
`signoff.gate()`; a new path must too. A sent version is frozen (canonical JSON +
SHA-256); never edit `signoffs.content` after sending — withdraw and send anew.

# AI framework (8 Oct 2026, the user's call)

Odin's AI is a framework in `services/ai/`, Settings → AI (`/settings/ai`,
routes in `routes/ai.py`). The server is shared with Zeus and managed outside
this repo: an Ollama container on the office LAN serving the alias **P24-AI**.
Odin depends on the contract, never on that server:
- **One protocol:** the OpenAI-compatible API (`{base}/models`,
  `{base}/chat/completions` with `response_format` JSON schema), standard
  fields only. Never Ollama's own `/api/*`, never `num_ctx`/`num_thread`/
  `keep_alive` in a request (tuning lives on the server).
- **Everything about the server is a policy** (areas `ai` and `ai_schedule`);
  the key is sealed (`ai.api_key`). Addresses outside the private network are
  refused unless `ai_allow_external` is on.
- **A feature is one `AIFeature` spec** registered in `services.ai.FEATURES`
  (`services/ai/features/<key>.py`, prompt in `services/ai/prompts/<key>.vN.txt`):
  gather (scope applied), JSON schema, fallback, and a synthetic fixture with
  graders (`services/ai/graders.py`). `register()` refuses a spec without them.
- **The gate:** a feature runs only when AI is on, the heartbeat says up, the
  feature is switched on, and it passed validation on the current model
  fingerprint (`id@created` from `/models`) with the current prompt hash — or an
  admin forced it (audited). Otherwise the caller uses the fallback.
- **Never call the model from a web request.** Queue an `ai_jobs` row; the
  scheduler's AI worker thread (`scheduler.ai_worker`, `services/ai/health.tick`)
  runs heartbeats, the daily validation and jobs. Model output lands as a
  suggestion a person accepts through the normal audited route.
- **One door:** nothing outside `services/ai/` calls the server; a meta-test
  enforces it. Tests use `FakeAIServer` in test_app.py, never a real model.
- **The AI server's integration guide (8 Oct 2026)** binds Odin as one of its
  two client apps: every system prompt starts with the identity line (policy
  `ai_identity`); input at most `ai_max_input_chars` (4,000; `fit()` trims,
  documents are read in parts); replies capped at 1,000 tokens; one request
  at a time (the single AI worker); every request logged in `ai_calls`;
  cancel on every draft; arithmetic in code, never in the model. Odin does
  not stream: its AI work is queued, not watched token by token.

# Front end — React + shadcn/ui

Decision (8 Sep 2026): the UI is **Vite + React + TypeScript + shadcn/ui**
in `frontend/`, Flask is the JSON API. The migration finished and the old
Jinja pages were removed on 9 Oct 2026: every page route checks its
permission (and `load_project` for a project) and returns `spa_index()`
(`spa.py`; 503 with how to build when there is no build). Still Jinja: the
guest pages (public, token-based, to retire), the sign-in form's fallback for
a failed non-JS POST, and the error page. Python tests point `SPA_DIST` at a
stub shell (`test_app.STUB_DIST`) and assert on the `/api/*` JSON, never on
page HTML; a flash left for the next page is read with `flashed(client)`.

Rules:
- Style only through the tokens in `frontend/src/index.css` and shadcn
  components; colour is a state, never decoration. See DESIGN.md.
- New pages get a JSON route in `routes/api.py` that reuses the existing
  decorators, permissions and `audit_log` — never a second auth path. The
  audit meta-test enforces this; `attempt_login()` is the shared login door.
- Mutations send `X-CSRF-Token` from `/api/session`. Same session cookie.
  A React page may post to an existing **form** route instead of adding a
  JSON twin: send `Accept: application/json` and the `json_for_fetch`
  hook in `core.py` returns the flashes as JSON (`postForm` in
  `frontend/src/lib/api.ts`). One route, one permission, one audit row.
- `frontend/dist` is built by the Docker stage and CI; never committed.
- Frontend tests: `npm --prefix frontend test` runs both vitest projects —
  `unit` (pure helpers in `src/lib/*.test.ts`, node) and `ui` (page tests in
  `src/pages/*.test.tsx`, jsdom + Testing Library, API mocked, fixtures in
  `src/pages/fixtures.ts`). Pure formatting lives in `src/lib/format.ts`;
  keep page files free of logic worth a unit test.
- UI suite (Playwright, `frontend/e2e/`): `npm --prefix frontend run e2e`
  builds, seeds a throw-away database with `scripts/seed_uat.py` and drives
  Chromium against Flask on 5099. Tiers by tag: `@smoke` (every page for
  admin / member / viewer, every header control), `@flow` (the journeys),
  `@a11y` (axe, WCAG 2.1 AA, light and dark — serious/critical fail),
  `@keys` (keyboard-only), `@visual` (golden screenshots, Linux only;
  refresh with the CI workflow's `update_snapshots` input and commit the
  artifact), and `node e2e/perf.mjs` (Lighthouse thresholds and a gzipped
  main-bundle ceiling). CI's `ui` job runs all of it and blocks the merge.
  A new page or control needs a line in `smoke.spec.ts` and, if it is a
  journey, a test in `flows.spec.ts`.
- Lint: `npm --prefix frontend run lint` is oxlint with the accessibility rules and fails above
  the warning baseline (`--max-warnings` in `frontend/package.json`): add none, and lower the
  number when warnings are fixed.
- Dev: `npm --prefix frontend run dev` (5173, proxies un-ported paths to Flask
  on 5050) or build once and let Flask serve it (`npm --prefix frontend run build`).
- shadcn CLI: `npx shadcn@latest add <component>` from `frontend/`.
  Components land in `src/components/ui` via the `@` alias in `tsconfig.json`.

# System map

`docs/system-map.html` is the source of the **Odin System Map** artifact
(https://claude.ai/artifact/DLoSQZo8uDQ5B4hh3ZnnQz): architecture, project
lifecycle, notifications, permissions, ways in, code structure, tests,
deploy & release, and the loophole register. The folders, files, test lists, CI
jobs, Docker facts and releases are generated from the last commit by
`python3 scripts/build_system_map.py` (never edit the REPO-DATA block by hand).
It must stay true to the code. When a change alters how Odin runs, moves or
exposes data, notifies, grants access, or closes a loophole: edit the page
(a fixed loophole keeps its number and gets `fixed: "vX.Y.Z"`; a new one gets
the next number), bump `MAP_STAMP`, commit it, and republish it to that URL
with the Artifact tool (`file_path: docs/system-map.html`, `url:` as above).
Admins see the same page inside Odin (Settings → System map & changes,
`/settings/map`, framed from `/settings/map/page`), so each release carries the
map and change log of its own code. The change log is generated from git: each
tag is a release, and commits after the last tag appear under the version in
`VERSION`. **Releasing:** `VERSION` is committed first, then the map is regenerated
(the generator refuses an uncommitted VERSION): `docs/RELEASING.md`, step 4.
The Stop hook `scripts/system_map_stale.sh` (`.claude/settings.json`) blocks
the end of a turn while the generated facts do not match HEAD or a code commit
is newer than the map's last commit.
