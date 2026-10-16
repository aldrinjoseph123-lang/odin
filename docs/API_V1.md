# Odin `/api/v1`: the read-only API

For scripts and reports (Power BI, a spreadsheet pull, a status board) that need
Odin's rollouts without a person signing in. It is read-only: three `GET` routes.
Everything here is written from the code in `routes/tokens.py` (`token_required`,
the three views) and the data builders they call (`services/plan.py`,
`services/report_data.py`); the tests are in `test_app.py`
(`test_api_tokens_read_only_shown_once_revocable`) and `test_v18_projects.py`
(`test_v1_report_carries_the_whole_report`).

## Tokens

An admin makes a token in **Settings → API tokens** (`/settings/api`): a name and a
life of 30, 90 or 365 days. The token (`odin_` followed by 43 URL-safe characters) is shown
once, with a Copy button; Odin keeps only its SHA-256. Revoking it stops it at once.
Expired and revoked tokens are deleted after 90 days.

Send it on every request:

```
curl -H "Authorization: Bearer odin_…" https://odin.example.com/api/v1/projects
```

- Only the `Authorization: Bearer` header is read. A token in a query string, a
  cookie or a body is ignored, and a browser session never opens `/api/v1`.
- **A token sees what internal staff see: every rollout, not a role-limited few.**
  Treat it like a staff password: store it in the tool's secret store, give each
  tool its own, revoke it when the tool is retired.
- Each token's last use is shown in Settings. The first read of a day by a token is
  written to the audit trail (`api_token_read`, actor `token:<name>`, naming the
  request); later reads that day only move "last used".
- There is no CSRF check on `/api/v1` (a Bearer header cannot be forged by another
  site) and no per-token rate limit. Poll politely.
- Behind Cloudflare Access, `/api/v1` needs its own Access policy (a service token)
  or the request never reaches Odin.

## Conventions

- JSON, UTF-8. `GET` only: any other method answers `405`.
- Dates (`start_date`, `target_end_date`, `due_date`) are `YYYY-MM-DD` in the
  workspace's calendar. Timestamps (`created_at`, `updated_at`) are UTC ISO 8601
  without a zone suffix (`2026-10-14T09:30:12.123456`).
- Stage names are the rollout's own (each rollout owns its stage list). The last
  stage of the list is the terminal one: a rollout sitting in it is closed.
- A deleted rollout (in its undo window or purged) never appears.
- The code does not freeze the shapes. Treat keys you do not know as additions, and
  re-read this file when Odin is updated (the system map's change log lists releases).

## Errors

Every error is JSON `{"error": "<words>"}` with the status code.

| Status | When |
|---|---|
| 401 | No token, a malformed header, an unknown, expired or revoked token. Body: `A valid API token is required (Authorization: Bearer <token>)` |
| 404 | No such rollout, or a rollout with no saved report (`No saved report for this rollout`) |
| 405 | Any method but `GET` |
| 500 | A fault in Odin. The body carries `ref`, a request id; quote it to an admin. Every response also carries `X-Request-Id` |

## `GET /api/v1/projects`

The active rollouts, oldest first (by `id`). `?all=1` also returns closed ones.

```json
{
  "projects": [
    {
      "id": 7,
      "name": "Branch firewalls",
      "client": "Acme Bank",
      "stage": "Deployment",
      "delivery_mode": "Distribution/MSSP",
      "vendor_name": "Fortinet",
      "product_name": "FortiGate",
      "po_number": "PO-1042",
      "start_date": "2026-09-01",
      "target_end_date": "2026-11-30",
      "created_at": "2026-09-01T07:10:44.120000",
      "updated_at": "2026-10-12T13:02:09.551000",
      "owner": "Sam Rivera"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | The rollout's number. Stable; the key for the other routes |
| `name`, `client` | As typed on the project form |
| `stage` | The current stage's name |
| `delivery_mode` | `Distribution/MSSP` or `Outsourced` |
| `vendor_name`, `product_name`, `po_number`, `start_date`, `target_end_date` | As entered; may be `null` |
| `owner` | The project manager's display name |
| `created_at`, `updated_at` | UTC timestamps |

"Active" means the current stage is not the last stage of the rollout's own list.

## `GET /api/v1/projects/<id>`

One rollout with its stage list and tasks.

```json
{
  "project": { "...": "the fields above, plus", "stages": ["PO Received", "Scoping", "Kickoff", "Deployment", "Tuning/UAT", "Hypercare", "Sign-off", "Closed"] },
  "tasks": [
    { "title": "Confirm rack space", "stage": "Kickoff", "done": true, "due_date": "2026-09-20", "assignee": "Priya Nair" }
  ]
}
```

- `project.stages`: the rollout's stage names in order.
- `tasks`: every task, oldest first. `stage` is the stage it belongs to, `done` a
  boolean, `due_date` and `assignee` may be `null`. Tasks carry no id in this API.
- Closed rollouts can be read by id even though `/projects` hides them by default.

## `GET /api/v1/projects/<id>/report`

The latest **saved** report version of the rollout (the project manager's "Save as
version" on the Report page). It is the **internal** cut, as staff see it, not the
customer copy.

```json
{
  "version": 3,
  "kind": "snapshot",
  "body": "On track; the firewalls are racked…",
  "summary": "On track; the firewalls are racked…",
  "next_steps": "Cut-over weekend 7 Nov",
  "asks": "Customer to confirm the change window",
  "data": { "...": "the frozen report data, below" },
  "created_by": "Sam Rivera",
  "created_at": "2026-10-12T13:02:09.551000"
}
```

- `kind` is `snapshot` for a current version. An older plain-text version has
  `kind: "text"`, `data: null` and empty `summary`, `next_steps`, `asks`; read `body`.
- `summary`, `next_steps`, `asks` are the project manager's own words.
- `data` is frozen at the moment of saving (a later change to the rollout does not
  alter it). Its top-level keys (`services/report_data.build`, plus
  `customer_notes`):

| Key | Content |
|---|---|
| `audience` | `internal` |
| `generated_at`, `today`, `company` | When it was frozen (UTC), the workspace's date, the company name |
| `project` | `id`, `name`, `client`, `po_number`, `stage`, `owner_name`, `start_date`, `target_end_date`, `vendor_name`, `product_name`, `delivery_mode`, `stage_number`, `stage_count` |
| `health` | `rag` (`green`, `amber`, `red`, or `done` when closed), `reasons` (list of sentences), `confidence` (`low`, `medium`, `high`). The app shows `green/amber/red` as On track / At risk / Off track |
| `pct_complete`, `elapsed_days`, `has_plan`, `baseline_at` | Progress by planned length, days since start, whether planned dates exist, when the baseline was frozen |
| `finish` | `forecast`, `planned`, `baseline`, `target` (dates), `vs_target_days`, `vs_baseline_days`, `days_to_target` (calendar days; positive vs target means late) |
| `stages` | Per stage: `id`, `name`, `position`, `sla_days`, `status` (`done`, `skipped`, `current` or `next`), `plan_start`, `plan_end`, `base_start`, `base_end`, `actual_start`, `actual_end`, `forecast_start`, `forecast_end`, `planned_days`, `actual_days`, `slip_days`, `suggested_start`, `suggested_end`. Lengths and `actual_days` count working days (calendar days when the workspace has switched working days off); `slip_days` is calendar days |
| `milestones` | The current and next stages: `stage`, `start`, `end`, `planned_end` |
| `raid` | The whole register, one object per item: `id`, `kind` (`risk`, `issue`, `decision`, `blocker`), `title`, `detail`, `impact`, `likelihood`, `status`, `owner_id`, `owner_name`, `due_date`, `stage`, `resolution`, `customer_visible`, `open`, and who and when it was raised |
| `work` | `total`, `done`, `late`, `by_stage`, a weekly `burn` series, and the `open` tasks (up to 40) |
| `team` | `name`, `role`, `active` per participant |
| `people` | Per person: open, done, late, role |
| `plan_changes` | The last 30 days of logged plan moves with their reasons |
| `documents` | Documents by category |
| `history` | `dwell` (time in each stage against its SLA), `approvals`, `notes` |
| `needs` | What waits on the customer: the pending `approval` and their `tasks` |
| `customer_notes` | Customer-visible notes kept aside for the customer cut |
| `template` | The document template frozen with the version |

There is no route for older versions, for the customer cut, or for the PDFs; those
are in the app (`/projects/<id>/report`, `/projects/<id>/report.pdf`).

## What the API does not do

No writes of any kind, no users, documents, notes, alerts, audit rows or settings,
no portfolio report, no webhooks, no pagination (the list is the whole set), no
filtering beyond `?all=1`. If a tool needs more, ask for a route; do not scrape the
app's `/api/*` routes, which belong to the web pages, need a signed-in session and
change with them.
