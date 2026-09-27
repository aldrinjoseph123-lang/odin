# Visual authority

**DESIGN.md is the visual authority for the React front end** (`frontend/`), written
from the built world on 8 Sep 2026 when the user released the previous identity
and chose a light, direct-flowchart UI (convention played straight; craft bar:
Linear, Whimsical/FigJam). Product truth lives in PRODUCT.md. Read both before UI
work; do not reintroduce the retired look (dark nav, brand red #E11D2E, Chakra
Petch, 2 px corners) anywhere in React.

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

# Adding a table

A table keyed by `project_id` (or holding per-user secrets) must be wired into
every place that walks the schema, or the next reset leaves rows that attach
themselves to the next project created:
`reset_data.WIPE_TABLES` (children before parents) · the purge cascade in
`db.py` (`purge_deleted`) · `services/reports.draft_report` if it is
project history · `scripts/seed_uat.py` if UAT needs rows · a purge for
anything that only grows (`login_links` is trimmed as links are minted).

# Front end migration — React + shadcn/ui (in progress)

Decision (8 Sep 2026): the UI moves to **Vite + React + TypeScript + shadcn/ui**
in `frontend/`, Flask becomes the JSON API. **Strangler rollout**: a Jinja page
stays live until its React replacement has passed tests and UAT; then its
endpoint name is added to `SPA_PAGES` in `spa.py` and Flask serves the built
bundle for it. Order: login ✅ → board ✅ → projects ✅ → project detail ✅ → users ✅ /
audit ✅ → settings ✅ → RBAC ✅ / contacts ✅ → new/edit project form ✅ →
account ✅ / my-work ✅ / analytics ✅ / alerts ✅ / reports ✅. Still Jinja: the guest
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
- Frontend tests: `npm --prefix frontend test` (vitest, node env). Pure
  formatting lives in `src/lib/format.ts` so it can be tested without a DOM;
  keep page files free of logic worth a unit test.
- Dev: `npm --prefix frontend run dev` (5173, proxies un-ported paths to Flask
  on 5050) or build once and let Flask serve it (`npm --prefix frontend run build`).
- shadcn CLI: `npx shadcn@latest add <component>` from `frontend/`.
  Components land in `src/components/ui` via the `@` alias in `tsconfig.json`.
