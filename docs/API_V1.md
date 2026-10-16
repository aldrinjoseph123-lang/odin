# Odin `/api/v1`: the read API and the CRM intake

For scripts and reports (Power BI, a spreadsheet pull, a status board) that need
Odin's rollouts without a person signing in. Three `GET` routes read (rollouts with their custom fields,
tasks and the links between them, milestones, asks and ratings, saved reports); one `POST` route, `/api/v1/intake`,
lets the CRM hand over a won deal (below). Nothing else writes.
Everything here is written from the code in `routes/tokens.py` (`token_required`,
the three views), `routes/intake.py` and `services/intake.py` (the intake) and the data builders they call (`services/plan.py`,
`services/report_data.py`); the tests are in `test_app.py`
(`test_api_tokens_read_only_shown_once_revocable`) and `test_v18_projects.py`
(`test_v1_report_carries_the_whole_report`); the intake's are in `test_v2_intake.py`, and the v2.0.0 additions (paging, task links, milestones, asks) in `test_v2_integrate.py`.

## Tokens

An admin makes a token in **Settings → API tokens** (`/settings/api`): a name and a
life of 30, 90 or 365 days. The token (`odin_` followed by 43 URL-safe characters) is shown
once, with a Copy button; Odin keeps only its SHA-256. Revoking it stops it at once.
Expired and revoked tokens are deleted after 90 days.

**Scopes.** A token has one scope, fixed when it is made. `read` (made in **Settings → API tokens**)
opens the three `GET` routes. `create` (made in **Settings → Integrations → Intake**, where its name is
the *source* shown on every intake) opens `POST /api/v1/intake` and nothing else. A token used on a route
of the other scope answers `403`. Tokens made before scopes existed are `read`.

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
  site). The read routes have no rate limit, so poll politely; the intake has one (below).
- Behind Cloudflare Access, `/api/v1` needs its own Access policy (a service token)
  or the request never reaches Odin.

## Conventions

- JSON, UTF-8. The three read routes take `GET` only and the intake `POST` only: any other method answers `405`.
- A rollout waiting for confirmation (a pending intake) is not a rollout to the read routes: it is missing from
  `/api/v1/projects` (even with `?all=1`) and its id answers `404` until a project manager confirms it.
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
| 403 | A token of the wrong scope for the route (`This token has the read scope; this route needs a token with the create scope`) |
| 405 | Any method but the route's own (`GET`; `POST` for the intake) |
| 500 | A fault in Odin. The body carries `ref`, a request id; quote it to an admin. Every response also carries `X-Request-Id` |

## `GET /api/v1/projects`

The active rollouts, oldest first (by `id`). `?all=1` also returns closed ones.

**Paging (v2.0.0).** Without `limit` the answer is the whole set, as before. `?limit=N` (1 to 500) returns at
most N rollouts and `?offset=M` (0 or more) skips the first M, in the same `id` order; both combine with
`?all=1`. Every answer carries `total` (how many rollouts match, ignoring the page), `limit` (`null` when not
asked for) and `offset`. A limit or offset that is not a whole number in range answers `400`
(`limit: 1 to 500`, `offset: 0 or more`, `limit and offset are whole numbers`). To read everything in pages:
start at `offset=0` and add `limit` until `offset >= total`.

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
      "owner": "Sam Rivera",
      "fields": { "Region": "UAE", "Endpoints in scope": 220 }
    }
  ],
  "total": 1,
  "limit": null,
  "offset": 0
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
| `fields` | The rollout's custom fields (Settings → Rollouts & workflow → Custom fields) that have a value, by name: text, a number, a `YYYY-MM-DD` date, one of a choice field's choices, or `true`/`false`. Every field, not only those marked for the customer |

"Active" means the current stage is not the last stage of the rollout's own list.

## `GET /api/v1/projects/<id>`

One rollout with its stage list, tasks, milestones, and what was asked of the customer and partners.

```json
{
  "project": { "...": "the fields above, plus", "stages": ["PO Received", "Scoping", "Kickoff", "Deployment", "Tuning/UAT", "Hypercare", "Sign-off", "Closed"] },
  "tasks": [
    { "id": 41, "title": "Confirm rack space", "stage": "Kickoff", "done": true, "due_date": "2026-09-20", "assignee": "Priya Nair",
      "kind": "task", "estimate_hours": 2, "recurrence": null, "waits_on": [] },
    { "id": 42, "title": "Rack the firewalls", "stage": "Deployment", "done": false, "due_date": "2026-10-20", "assignee": "Priya Nair",
      "kind": "task", "estimate_hours": 6, "recurrence": null, "waits_on": [41] }
  ],
  "milestones": [
    { "id": 3, "name": "Cut-over weekend", "date": "2026-11-07", "stage": "Deployment", "customer_visible": true, "done": false, "done_at": null, "missed": false }
  ],
  "asks": [
    { "id": 44, "title": "Upload the network diagram", "kind": "upload", "done": true, "done_at": "2026-10-02T08:11:00", "due_date": "2026-10-03",
      "assignee": "Ann Lee", "assignee_role": "Customer", "category": "Design", "answers": [], "answered_by": "Ann Lee",
      "answered_at": "2026-10-02T08:11:00", "file": "acme-network.pdf" }
  ],
  "csat": [ { "signoff_version": 1, "rating": 5, "comment": "Smooth cut-over", "by_name": "Ann Lee", "at": "2026-11-20T10:00:00" } ]
}
```

- `project.stages`: the rollout's stage names in order.
- `tasks`: every task, oldest first. `id` is the task's number (v2.0.0), `stage` the stage it belongs to, `done`
  a boolean; `due_date`, `assignee`, `estimate_hours` (hours, for workload) and `recurrence` (`weekly`,
  `fortnightly`, `monthly`) may be `null`. `kind` is `task`, or for a task asked of an outside party `upload`
  or `form`. `waits_on` lists the ids of the tasks it waits on (finish-to-start, within the rollout); empty
  when it waits on nothing.
- `milestones`: the rollout's own dated commitments, open ones first by date, then those reached. `done_at` is
  a UTC timestamp once reached; `missed` is true for an open one whose date has passed. `customer_visible`
  says whether the customer sees it; the token sees them all.
- `asks`: the tasks assigned to an outside account (customer or partner), with what came back: `answers` (a
  form's `key`, `label`, `value`), who answered and when, and `file` (the uploaded document's name, while it is
  not deleted).
- `csat`: the customer's rating (1 to 5) and comment at each signed sign-off version, oldest first.
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
| `milestones` | The current and next stages: `stage`, `start`, `end`, `planned_end`; on the current stage, `gate` names what holds the next move (open tasks, missing documents, required fields), when something does |
| `project_milestones` | The rollout's own milestones, as in `GET /api/v1/projects/<id>` |
| `fields` | The custom fields with a value: `name`, `kind`, `value`, `customer_visible` |
| `asks`, `csat` | What was asked of the outside parties and their ratings at sign-off, as in `GET /api/v1/projects/<id>` (with the questions of a form) |
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

## `POST /api/v1/intake`

The CRM hands over a won deal. Odin makes a **pending** rollout: it has its stage list but sits before the
first stage, held by the default project manager, and appears only in the Flow's holding lane (List view) and
under Rollouts › Pending intake. It is in no Flow count, alert, dashboard figure or report, and the read routes
above do not list it. A project manager **confirms** it in the app by attaching the client's PO and taking
ownership; it then starts as any new rollout does, with the template's tasks. Needs a token with the `create`
scope.

```
curl -X POST https://odin.example.com/api/v1/intake \
  -H "Authorization: Bearer odin_…" -H "Content-Type: application/json" \
  -d '{
    "client": "Acme Bank",
    "name": "Branch firewalls",
    "deal_id": "D-1001",
    "product": "FortiGate 90G",
    "vendor": "Fortinet",
    "delivery_mode": "Outsourced",
    "target_date": "2027-06-30",
    "po_number": "PO-1042",
    "contacts": ["ann@acme.example", "bob@acme.example"],
    "fields": { "Region": "UAE", "Endpoints in scope": 220 }
  }'
```

| Key | Type | |
|---|---|---|
| `client` | text, at most 200 | **Required** |
| `name` | text, at most 200 | **Required.** The rollout's name |
| `deal_id` | text, at most 80 | **Required.** The CRM's id for the deal; the key for idempotency (below) |
| `product`, `vendor` | text, at most 120 | Optional |
| `delivery_mode` | `Distribution/MSSP` or `Outsourced` | Optional; `Distribution/MSSP` when left out |
| `target_date` | `YYYY-MM-DD`, 2000 to 2100 | Optional |
| `po_number` | text, at most 60 | Optional. The PO *document* is attached at confirmation |
| `contacts` | list of at most 10 email addresses | Optional. Well-formed addresses are lower-cased and de-duplicated; one whose domain is not allowed by **Settings → Sign-in & security → Partner email domains** (when that list is not empty) is dropped with a warning. Odin keeps them with the intake and, on confirmation, as a staff note; the project manager invites them from the team panel |
| `fields` | object | Optional. Custom fields by **name** (case-insensitive) or **id**, each value in the field's kind (text, number, date `YYYY-MM-DD`, one of a choice field's choices, yes/no). A field Odin does not have is refused, and so is a required field left out |

Every key is typed and capped; a key not listed is refused, and the body must be a JSON object (the
`Content-Type` header is not required).

**Answer.** `201` when the rollout was made, `200` when this deal id had been seen already:

```json
{
  "created": true,
  "rollout": { "id": 12, "name": "Branch firewalls", "client": "Acme Bank", "deal_id": "D-1001", "status": "pending", "path": "/projects/12" },
  "warnings": ["spy@evil.example was dropped: its domain is not allowed (Settings › Sign-in & security › Partner email domains)"]
}
```

`status` is `pending`, or `confirmed` once a project manager has confirmed the rollout. `path` is the rollout's
address in the app, under Odin's own web address. `warnings` lists what Odin changed without refusing (dropped
contacts); it is empty on a repeat.

**Idempotency by deal id.** A second call with a `deal_id` Odin already holds answers `200` with
`"created": false` and the existing rollout, whatever else the body says: it never makes a duplicate and never
changes the first. This holds after the rollout is confirmed. Only a rollout deleted in Odin releases its deal
id, so a CRM retry after a timeout is always safe.

**Audit and log.** Each created rollout is written to the audit trail (`intake_create`, actor `token:<name>`,
naming the source, the deal id and the client). Settings → Integrations → Intake lists the last ten calls with
their result (created, already had it, refused, too many); Odin keeps the newest 200.

**Settings** (Settings → Integrations → Intake): the stage template and the default project manager a new
intake gets (the first template and the first active Admin when left blank), the *allowed sources* (token names
separated by commas; blank lets every `create` token in), and the rate limit (30 intakes per token per minute by
default, 1 to 100). The default project manager is told in the bell, and by email if they have it on.

| Status | Body `error` | Meaning |
|---|---|---|
| 400 | The words: `client is required`, `client: at most 200 characters`, `delivery_mode: one of …`, `target_date: a date like 2026-10-31`, `Unknown field: budget`, `fields: unknown custom field Colour`, `Region: pick one of UAE, KSA`, `contacts: x is not an email address`, `Send a JSON object` | Nothing was made. Several problems are joined with `;` |
| 401 | `A valid API token is required …` | No token, or an unknown, expired or revoked one |
| 403 | `This token has the read scope; …` or `The token <name> is not an allowed source …` | Wrong scope, or the token's name is not in the allowed sources |
| 405 | | Any method but `POST` |
| 409 | `Intake is not set up: …` | Odin has no stage template with two stages, or no active Admin to hold the intake. Fix it in Settings and retry |
| 429 | `Too many intakes from <name>: at most N a minute. Retry in a minute.` | Over the rate limit. The `Retry-After` header says `60`. A refused call counts towards the limit; a call that was itself refused for rate does not |

## What the API does not do

No writes but the CRM intake, and no users, documents, notes, alerts, audit rows or settings,
no portfolio report, no webhooks, no filtering beyond `?all=1`, and paging (`limit`, `offset`) only on
`/api/v1/projects`. If a tool needs more, ask for a route; do not scrape the
app's `/api/*` routes, which belong to the web pages, need a signed-in session and
change with them.
