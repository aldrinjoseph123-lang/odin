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

Tokens live in `frontend/src/index.css` (`:root`): white ground, ink text, one
accent `#3D5AFE` for selection and the primary action, `--primary-text` for the
accent as text, green/amber/red **only** as state (`--ok/--warn/--bad` + `-soft`
and `-line`), Inter, `--radius: 0.5rem`, hairline `--border`.

**Themes (27 Sep 2026, the user's call):** each user picks light / dark / follow
the OS and one of eight accents on the Account page (header button cycles the
theme). Dark is `:root[data-theme="dark"]`, accents are `:root[data-accent=…]`,
both set before first paint by the script in `frontend/index.html` and kept in
`localStorage` as `odin.theme` / `odin.accent`; the saved choice lives on the
user row (`users.theme`, `users.accent`). Never hard-code a colour: every
component must read tokens so both themes and every accent follow.

**Jinja pages keep `static/style.css` (the legacy look) until each is ported.**
That stylesheet is frozen: fix defects only, no new components, no re-theming —
the port replaces it page by page.

# Admin settings

People pages (`/people`, `/people/<id>`) and My work draw from `services/people.py`; a
note to a colleague is `POST /api/people/<id>/notify` (kind `nudge`, audited).
The home page is `/dashboard` (`home_url()` in `routes/auth.py`: sign-in, `/`
and the logo land there; a user may pick the flow on their Account page,
`users.home`; partners always get the flow). Settings is one side-menu page (`components/SettingsLayout.tsx`), one address
per area: `/settings/general|security|workflow|notifications|integrations|reports|backups|api|audit`
plus Users, Role permissions, Contacts and the Audit log in the same menu.
Recurring work (digest, backups, weekly report, audit retention) runs only in
`scheduler.py` (its own service), at policy times in the workspace time
zone — never in a web worker.
**The dashboard layout is the one admin-set value that is not a policy:**
it is a JSON list of widgets, edited on the dashboard itself (`PUT
/api/dashboard/layout/default`, audited) and kept in the settings table under
`dashboard.layout`; a user's own arrangement lives on their row
(`users.dashboard_layout`). The widget catalogue, defaults and validation are
`services/dashboard.WIDGETS` / `normalize_layout`.
**Any value an admin may change is a policy:** add it to `policies.POLICIES`
(area, kind, default, limits, label, help; kinds int, bool, choice, multi, text,
url, domains, emails, time, lines), read it with `policy("key")`
(pass `db` outside an app context), and the settings page draws, validates
(`save_policies`, one audited route `/settings/policies/<area>`) and
explains it. Never hard-code a number an admin could reasonably want to change.

# Adding a table

A table keyed by `project_id` (or holding per-user secrets) must be wired into
every place that walks the schema, or the next reset leaves rows that attach
themselves to the next project created:
`reset_data.WIPE_TABLES` (children before parents) · the purge cascade in
`db.py` (`purge_deleted`) · `services/reports.draft_report` if it is
project history · `scripts/seed_uat.py` if UAT needs rows · a purge for
anything that only grows (`login_links` is trimmed as links are minted).
`plan_changes` and `raid_items` (30 Sep 2026) are wired this way; plan dates live
on `project_stages` (`plan_*`, `base_*`). Reports read one structure
(`services/report_data.py` per rollout, `services/portfolio.py` for all) that
the page, the PDF (`services/report_pdf.py`) and the weekly email share; the
customer cut is made on the server, never in the page.
`scope_items` and `signoffs` (30 Sep 2026) are wired the same way. The sign-off
(`services/signoff.py`, routes in `routes/signoff.py`) gates the terminal stage:
every stage-move path (`change_stage`, the vendor guest link) calls
`signoff.gate()`; a new path must too. A sent version is frozen (canonical JSON +
SHA-256); never edit `signoffs.content` after sending — withdraw and send anew.

# Front end migration — React + shadcn/ui (in progress)

Decision (8 Sep 2026): the UI moves to **Vite + React + TypeScript + shadcn/ui**
in `frontend/`, Flask becomes the JSON API. **Strangler rollout**: a Jinja page
stays live until its React replacement has passed tests and UAT; then its
endpoint name is added to `SPA_PAGES` in `spa.py` and Flask serves the built
bundle for it. Order: login ✅ → board ✅ → projects ✅ → project detail ✅ → users ✅ /
audit ✅ → settings ✅ → RBAC ✅ / contacts ✅ → new/edit project form ✅ →
account ✅ / my-work ✅ / analytics ✅ / alerts ✅ / reports ✅ / dashboard ✅ (new page, no Jinja twin: without a build it redirects to the flow). Still Jinja: the guest
pages (public, token-based, to retire), the login fallback form, error page.

Rules while both UIs exist:
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
- Dev: `npm --prefix frontend run dev` (5173, proxies un-ported paths to Flask
  on 5050) or build once and let Flask serve it (`npm --prefix frontend run build`).
- shadcn CLI: `npx shadcn@latest add <component>` from `frontend/`.
  Components land in `src/components/ui` via the `@` alias in `tsconfig.json`.
