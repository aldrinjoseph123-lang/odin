import type { DateFormat } from "@/lib/format"
// One thin client for Flask's JSON API. Same session cookie as the Jinja
// pages; every mutation carries the CSRF token from /api/session as a header.

export type User = {
  id: number
  name: string
  role: "Admin" | "Member" | "Contributor" | "Viewer" | "External"
  kind: "internal" | "external"
  must_change_password: boolean
  permissions: string[]
  nav: Nav
  theme: "system" | "light" | "dark"
  accent: string
  avatar_url: string | null
  home: "dashboard" | "board"
  prefs?: { date_format: DateFormat; undo_minutes: number; activity_idle_minutes?: number }
}

export type SignIn = { microsoft: boolean; microsoft_only: boolean; link_minutes?: number }
type SessionResponse = { csrf: string; user: User | null; messages?: string[]; signin?: SignIn }

let csrfToken: string | null = null

export async function session(): Promise<SessionResponse> {
  const res = await fetch("/api/session", { credentials: "same-origin" })
  const data = (await res.json()) as SessionResponse
  csrfToken = data.csrf
  return data
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// One JSON request with the CSRF token; every mutation goes through here.
async function send<T>(path: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<T> {
  if (!csrfToken) await session()
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken ?? "" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = (await res.json().catch(() => ({}))) as { error?: string; csrf?: string } & T
  if (data.csrf) csrfToken = data.csrf
  if (!res.ok) throw new ApiError(res.status, data.error ?? `Request failed (${res.status})`)
  return data
}
const post = <T,>(path: string, body?: unknown) => send<T>(path, "POST", body)

export function login(username: string, password: string) {
  return post<{ user: User; csrf: string }>("/api/login", { username, password })
}

export function logout() {
  return post<{ ok: true; csrf: string }>("/api/logout")
}

export type Nav = { active_alert_count: number; my_open_task_count: number; unread_notifications: number; projects_nav_url: string }

export type Card = {
  id: number; name: string; client: string; stage: string; owner_name: string
  delivery_mode: string; task_total: number; task_done: number; updated_at: string
}

export type BoardData = {
  stages: string[]
  terminal: string
  delivery_modes: string[]
  alert_titles: Record<string, string>
  columns: Record<string, Card[]>
  alerts: Record<string, { id: number; name: string }[]>
  real_alerts: Record<string, number>
  dashboard: { stage_counts: Record<string, number>; max_stage_count: number; delivery_counts: Record<string, number>; total_active: number }
  recent_notes: { id: number; author: string; project_id: number; project_name: string; stage: string; created_at: string; note: string }[]
  banner_names: number
  column_cards: number
  can_move: boolean
}

export async function board(): Promise<BoardData> {
  const res = await fetch("/api/board", { credentials: "same-origin" })
  if (!res.ok) throw new ApiError(res.status, `Board failed (${res.status})`)
  return res.json()
}

export function changeStage(projectId: number, stage: string, note = "") {
  return post<{ ok: true; undo: string }>(`/api/projects/${projectId}/stage`, { stage, note })
}

export function dismissAlert(projectId: number, alertType: string) {
  return post<{ ok: true }>(`/api/alerts/${projectId}/dismiss/${alertType}`)
}

// ---- Flow: first screen ----
export type FlowState = "overdue" | "over_sla" | "due_soon" | "on_track"
export type ApprovalStatus = "pending" | "approved" | "declined" | "superseded"
export type FlowRow = {
  id: number; name: string; client: string; stage: string; stages: string[]; stage_index: number; owner_name: string; mine: boolean
  team: { id: number; name: string; avatar_url: string | null }[]
  approval: ApprovalStatus | null
  delivery_mode: string; target_end_date: string | null; days_in_stage: number | null; sla_days: number | null
  over_by: number | null; state: FlowState; open_tasks: number; total_tasks: number
  next_task: { title: string; due_date: string | null; assignee: string | null } | null; updated_at: string
  idle_days: number | null; stale: boolean
}
export type FlowData = { stages: string[]; rows: FlowRow[]; counts: Record<FlowState, number>; can_move: boolean; today: string }
export type FlowStage = { name: string; status: "done" | "current" | "next"; sla_days: number | null; entered_at: string | null; days: number | null }
export type FlowTask = { id: number; title: string; done: boolean; due_date: string | null; assignee: string | null; assignee_id: number | null; assignee_avatar_url: string | null; stage: string }
export type FlowDetail = {
  id: number; name: string; client: string; vendor_name: string | null; product_name: string | null; delivery_mode: string
  outsourcer_name: string | null; owner_name: string; stage: string; stage_index: number; next_stage: string | null
  state: FlowState; over_by: number | null; start_date: string; target_end_date: string | null; days_left: number | null; today: string
  stages: FlowStage[]; tasks: FlowTask[]; documents: number
  recent_notes: { author: string; note: string; stage: string; created_at: string }[]; can_move: boolean
  participants: { id: number; user_id: number; name: string; role: string; avatar_url: string | null }[]
  assignable: { id: number; name: string }[]; can_edit: boolean; me: number
  customer_approval: boolean; can_approve: boolean
  approval: { id: number; stage: string; status: ApprovalStatus; decided_by: string | null; comment: string | null } | null
  signoff?: SignoffState
}
export const decideApproval = (projectId: number, approvalId: number, decision: "approved" | "declined", comment = "") =>
  post<{ ok: true }>(`/api/projects/${projectId}/approvals/${approvalId}`, { decision, comment })
async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin" })
  if (!res.ok) throw new ApiError(res.status, `Request failed (${res.status})`)
  return res.json()
}
export const flow = () => getJson<FlowData>("/api/flow")
export const flowDetail = (id: number) => getJson<FlowDetail>(`/api/projects/${id}/flow`)

// ---- the plan and the RAID register (services/plan.py, services/raid.py) ----
export type Rag = "green" | "amber" | "red" | "done"
export type PlanStage = {
  id: number; name: string; position: number; sla_days: number | null; status: "done" | "skipped" | "current" | "next"
  plan_start: string | null; plan_end: string | null; base_start: string | null; base_end: string | null
  actual_start: string | null; actual_end: string | null; forecast_start: string | null; forecast_end: string | null
  planned_days: number; actual_days: number | null; slip_days: number | null; suggested_start: string; suggested_end: string
}
export type PlanData = {
  stages: PlanStage[]; has_plan: boolean; baseline_at: string | null; today: string; closed: boolean; default_days: number; pct_complete: number
  finish: { forecast: string | null; planned: string | null; baseline: string | null; target: string | null; vs_target_days: number | null; vs_baseline_days: number | null; days_to_target: number | null }
  health: { rag: Rag; reasons: string[]; confidence: "high" | "medium" | "low" }
  changes: { stage: string | null; field: string; old: string | null; new: string | null; reason: string | null; author: string; created_at: string }[]
  can_edit: boolean; project: { id: number; name: string; start_date: string | null; target_end_date: string | null }
}
export const plan = (id: number) => getJson<PlanData>(`/api/projects/${id}/plan`)
export const savePlan = (id: number, stages: { id: number; plan_start: string | null; plan_end: string | null }[], reason: string) =>
  send<{ ok: true; changed: number; baselined: boolean }>(`/api/projects/${id}/plan`, "PUT", { stages, reason })
export const rebaseline = (id: number, reason: string) => post<{ ok: true }>(`/api/projects/${id}/plan/baseline`, { reason })
export type ReportWords = { summary: string; next_steps: string; asks: string; suggested?: { summary: string; next_steps: string; asks: string }; blocks?: ["h" | "li" | "p", string][] }
export type ReportPayload = {
  audience: "internal" | "customer"; generated_at: string; today: string; company: string
  template?: DocConfig
  project: { id: number; name: string; client: string; po_number: string | null; stage: string; owner_name: string; start_date: string; target_end_date: string | null; vendor_name: string | null; product_name: string | null; delivery_mode: string; stage_number: number; stage_count: number }
  health: PlanData["health"]; pct_complete: number; finish: Partial<PlanData["finish"]>; baseline_at: string | null; elapsed_days: number; has_plan: boolean
  stages: PlanStage[]; milestones: { stage: string; start: string | null; end: string | null; planned_end: string | null }[]
  raid: RaidItem[]
  work: { total: number; done: number; late: number; by_stage: { stage: string; total: number; done: number; late: number }[]; burn: { week: string; total: number; done: number }[]
          open?: { id: number; title: string; stage: string | null; who: string | null; due_date: string | null; late: boolean }[] }
  team: { name: string; role: string; active: boolean }[]
  history: { dwell: { stage: string; status: string; entered: string | null; left: string | null; days: number | null; sla: number | null; over: number }[]
             approvals: { stage: string; status: string; requested_by: string; requested_at: string; decided_by: string | null; decided_at: string | null; comment: string | null }[]
             notes: { author: string; note: string; stage: string; created_at: string }[] }
  needs: { approval: { stage: string; requested_at: string } | null; tasks: { title: string; due_date: string | null }[] }
  people?: { name: string; role: string | null; open: number; done: number; late: number }[]
  plan_changes?: PlanData["changes"]
  documents?: ({ category: string; filename: string; uploaded_by: string; uploaded_at: string } | { category: string; count: number })[]
}
export type RolloutReport = {
  audience: "internal" | "customer"; words: ReportWords; data: ReportPayload | null; is_live: boolean
  version: { version: number; kind: "text" | "snapshot"; created_by: string; created_at: string } | null
  versions: { version: number; kind: "text" | "snapshot"; created_by: string; created_at: string }[]; can_edit: boolean; project: { id: number; name: string; client: string }
}
export const rolloutReport = (id: number, audience: string, v?: number | null, template?: number | null) =>
  getJson<RolloutReport>(`/api/projects/${id}/rollout-report?${new URLSearchParams({ audience, ...(v ? { v: String(v) } : {}), ...(template ? { template: String(template) } : {}) })}`)
export const saveRolloutReport = (id: number, words: { summary: string; next_steps: string; asks: string }, template_id?: number | null) =>
  post<{ ok: true; version: number }>(`/api/projects/${id}/rollout-report`, { ...words, template_id: template_id ?? null })
export type RaidKind = "risk" | "issue" | "decision" | "blocker"
export type RaidItem = {
  id: number; kind: RaidKind; title: string; detail: string | null; impact: "low" | "medium" | "high"; likelihood: "low" | "medium" | "high" | null
  status: string; owner_id: number | null; owner_name: string | null; due_date: string | null; stage: string | null; resolution: string | null
  customer_visible: boolean; open: boolean; created_by: string; created_at: string; closed_at: string | null
}
export type RaidData = { items: RaidItem[]; owners: { id: number; name: string }[]; statuses: Record<RaidKind, string[]>; can_edit: boolean; stages: string[] }
export const raid = (id: number) => getJson<RaidData>(`/api/projects/${id}/raid`)
export const saveRaid = (projectId: number, item: Partial<RaidItem>, itemId?: number) =>
  itemId ? send<{ ok: true }>(`/api/projects/${projectId}/raid/${itemId}`, "PUT", item) : post<{ ok: true; id: number }>(`/api/projects/${projectId}/raid`, item)
export const deleteRaid = (projectId: number, itemId: number) => send<{ ok: true }>(`/api/projects/${projectId}/raid/${itemId}`, "DELETE")

// ---- scope and sign-off (services/signoff.py) ----
export type ScopeStatus = "agreed" | "delivered" | "partial" | "descoped"
export type ScopeItem = { id: number; title: string; detail: string | null; status: ScopeStatus; note: string | null; position: number }
export type ScopeData = { items: ScopeItem[]; statuses: ScopeStatus[]; can_edit: boolean }
export const scopeItems = (id: number) => getJson<ScopeData>(`/api/projects/${id}/scope`)
export const saveScope = (projectId: number, item: Partial<ScopeItem> & { move?: -1 | 1 }, itemId?: number) =>
  itemId ? send<{ ok: true }>(`/api/projects/${projectId}/scope/${itemId}`, "PUT", item) : post<{ ok: true; id: number }>(`/api/projects/${projectId}/scope`, item)
export const deleteScope = (projectId: number, itemId: number) => send<{ ok: true }>(`/api/projects/${projectId}/scope/${itemId}`, "DELETE")

export type SignoffStatus = "sent" | "signed" | "countersigned" | "uploaded" | "waived" | "rejected" | "withdrawn"
export type SignoffState = { required: boolean; status: SignoffStatus | null; version: number | null; complete: boolean; in_stage: boolean; needed: boolean; awaiting_me?: boolean }
export type Signature = { kind: "drawn"; strokes: number[][][] } | { kind: "typed"; text: string }
export type SignoffContent = {
  project: { id: number; name: string; client: string; po_number: string | null; po_date: string | null; start_date: string | null; target_end_date: string | null
             finished: string; owner_name: string; partner_name: string | null; vendor_name: string | null; product_name: string | null; delivery_mode: string; company: string }
  summary: string; scope: { title: string; detail: string | null; status: ScopeStatus; note: string | null }[]
  delivered: string[]; outstanding: string[]; terms: string[]; statement: string
  signer: { name: string; email: string; role: string } | null; countersigner: { name: string; role: string } | null; prepared_by: string; prepared_at: string
}
export type SignoffVersion = {
  version: number; status: SignoffStatus; content_hash: string; created_by: string; created_at: string; content: SignoffContent; intact: boolean
  signer_id: number | null; signer_name: string | null; signer_title: string | null; signer_email: string | null; signed_at: string | null; signature: Signature | null
  counter_id: number | null; counter_name: string | null; counter_title: string | null; counter_signed_at: string | null; counter_signature: Signature | null
  reject_comment: string | null; rejected_at: string | null; document_id: number | null; waiver_reason: string | null; waived_by: string | null; completed_at: string | null
  signed_ip?: string | null; signed_agent?: string | null; counter_ip?: string | null; counter_agent?: string | null
  link_issued_by?: string | null; link_issued_at?: string | null
}
export type SignoffDraft = { summary: string; delivered: string[]; outstanding: string[]; terms: string[]; scope: ScopeItem[]; statement: string }
export type SignoffData = {
  project: { id: number; name: string; client: string; stage: string; owner_id: number }
  state: SignoffState
  versions: { version: number; status: SignoffStatus; created_at: string; created_by: string }[]
  current: SignoffVersion | null
  can: { manage: boolean; sign: boolean; countersign: boolean; upload: boolean; withdraw: boolean; waive: boolean }
  me: { name: string }
  draft?: SignoffDraft
  candidates?: { signers: { id: number; name: string; role: string; email: string }[]; countersigners: { id: number; name: string; role: string }[]; default_counter_id: number | null }
}
export type SignBody = { name: string; title: string; accept: boolean; signature: Signature }
export const signoff = (id: number, v?: number | null, template?: number | null) =>
  getJson<SignoffData>(`/api/projects/${id}/signoff${v ? `?v=${v}` : template ? `?template=${template}` : ""}`)
export const sendSignoff = (id: number, body: { summary: string; delivered: string[]; outstanding: string[]; terms: string[]; signer_id: number; counter_id: number; template_id?: number | null }) =>
  post<{ ok: true; version: number }>(`/api/projects/${id}/signoff`, body)
export const signSignoff = (id: number, v: number, body: SignBody, counter = false) => post<{ ok: true }>(`/api/projects/${id}/signoff/${v}/${counter ? "countersign" : "sign"}`, body)
export const rejectSignoff = (id: number, v: number, comment: string) => post<{ ok: true }>(`/api/projects/${id}/signoff/${v}/reject`, { comment })
export const signoffLink = (id: number, v: number) => post<{ ok: true; link: string; minutes: number; email: string }>(`/api/projects/${id}/signoff/${v}/link`)
export const withdrawSignoff = (id: number, v: number) => post<{ ok: true }>(`/api/projects/${id}/signoff/${v}/withdraw`)
export const waiveSignoff = (id: number, reason: string) => post<{ ok: true; version: number }>(`/api/projects/${id}/signoff/waive`, { reason })
export async function uploadSignoff(id: number, v: number, form: FormData): Promise<{ ok: true }> {
  if (!csrfToken) await session()
  const res = await fetch(`/api/projects/${id}/signoff/${v}/upload`, { method: "POST", credentials: "same-origin", body: form, headers: { "X-CSRF-Token": csrfToken ?? "" } })
  const data = (await res.json().catch(() => ({}))) as { error?: string; ok?: true }
  if (!res.ok) throw new ApiError(res.status, data.error ?? `Request failed (${res.status})`)
  return data as { ok: true }
}

// ---- calendar and kibana (views on the Flow page) ----
export type CalendarData = {
  month: string; today: string; from: string; to: string
  spans: { id: number; name: string; client: string; stage: string; start_date: string; target_end_date: string | null; state: FlowState }[]
  targets: { id: number; name: string; client: string; day: string; state: FlowState }[]
  tasks: { id: number; project_id: number; title: string; day: string; done: number; project: string; who: string | null }[]
  moves: { project_id: number; project: string; day: string; prev_stage: string; stage: string; who: string }[]
  approvals: { project_id: number; project: string; stage: string; day: string; kind: "asked" | "decided"; status: ApprovalStatus; who: string | null }[]
}
export const calendar = (month: string) => getJson<CalendarData>(`/api/calendar?month=${encodeURIComponent(month)}`)
export type KibanaData = { dashboards: { name: string; url: string; per_rollout: boolean }[]; rollouts: { id: number; name: string; client: string; po_number: string | null }[]; rollout: number | null; can_manage: boolean }
export const kibana = (rollout?: number | null) => getJson<KibanaData>(`/api/kibana${rollout ? `?rollout=${rollout}` : ""}`)

// ---- dashboard ----
export type DashKey = "active" | "overdue" | "over_sla" | "due_soon" | "awaiting" | "idle"
export type Person = { id: number; name: string; avatar_url: string | null }
export type WidgetSetting = { key: string; label: string; kind: "int" | "choice" | "multi" | "text"; default: unknown; choices?: string[]; min?: number; max?: number }
export type WidgetInfo = { id: string; title: string; blurb: string; w: 1 | 2 | 3; multiple: boolean; settings: WidgetSetting[] }
export type DetailRow = { id: number; name: string; client: string; stage: string; text: string }
export type Aggregate = { key: string; count: number }[]
export type DashboardData = {
  today: string; version: number; layout: { id: string; uid?: string; w: 1 | 2 | 3; settings: Record<string, unknown> }[]; is_custom: boolean; catalogue: WidgetInfo[]; scope_full: boolean
  data: {
    kpis: { counts: Record<DashKey, number>; before: Record<DashKey, number> | null; since: string | null; moved_this_week: number; series: Record<DashKey, { day: string; v: number }[]>; detail: Record<DashKey, DetailRow[]> }
    aggregates: Record<string, Aggregate>
    timeline: { id: number; name: string; client: string; stage: string; start_date: string; target_end_date: string | null; state: FlowState; progress: number; team: Person[] }[]
    progress: { done: number; current: number; pending: number; pct: number }
    stages: { stage: string; count: number }[]
    completion: { day: string; count: number }[]
    schedule: { due: { id: number; project_id: number; title: string; due_date: string; project: string; stage: string; who: string | null; avatar_url: string | null }[]
                approvals: { project_id: number; project: string; stage: string; requested_at: string }[] }
    team: { people: { id: number; name: string; avatar_url: string | null; role: string; projects: number; open: number; late: number }[]; unassigned: number }
    activity: { kind: "move" | "note" | "approval" | "task" | "document"; at: string; who: string | null; project_id: number; project: string; text: string }[]
    alerts: { id: number; project_id: number; project: string; type: string; title: string; severity: string; created_at: string }[]
    mywork: { tasks: { id: number; title: string; project_id: number; project: string; due_date: string | null; stage: string }[]; owned: number }
    cycle: { template: string; lead_avg: number | null; lead_median: number | null; completed_count: number; throughput: [string, number][]; slowest: { stage: string; avg_days: number } | null; measured_projects: number } | null
  }
}
export const dashboard = () => getJson<DashboardData>("/api/dashboard")
export const dashboardVersion = () => getJson<{ version: number }>("/api/dashboard/version")
export const saveLayout = (layout: DashboardData["layout"], scope: "mine" | "default" = "mine") =>
  send<{ ok: true; layout: DashboardData["layout"]; is_custom?: boolean }>(scope === "default" ? "/api/dashboard/layout/default" : "/api/dashboard/layout", "PUT", { layout })
export const resetLayout = () => send<{ ok: true; layout: DashboardData["layout"]; is_custom: false }>("/api/dashboard/layout", "DELETE")

// ---- projects list ----
export type ProjectRow = {
  id: number; name: string; client: string; po_number: string | null; stage: string; stages: string[]; stage_index: number; closed: boolean
  owner_name: string; delivery_mode: string; vendor_name: string | null; product_name: string | null; target_end_date: string | null; updated_at: string
  total_tasks: number; open_tasks: number; team: { id: number; name: string; avatar_url: string | null }[]
}
export type ProjectsData = {
  rows: ProjectRow[]; total: number; page: number; total_pages: number; sort: string; dir: "asc" | "desc"
  stages: string[]; delivery_modes: string[]; can_create: boolean
}
export const projects = (query: string) => getJson<ProjectsData>(`/api/projects${query ? `?${query}` : ""}`)

// ---- project page extras (beyond the flow detail) ----
export type ProjectExtras = {
  id: number; name: string; owner_id: number
  details: Record<string, string | null>
  customer_approval: boolean
  guest_links: { customer: string | null; vendor: string | null }; guest_links_enabled: boolean
  stage_rows: { id: number; name: string; sla_days: number | null }[]
  participants: { id: number; user_id: number; name: string; role: string; email: string | null; active: boolean; avatar_url: string | null }[]
  notes: { id: number; author: string; note: string; stage: string; created_at: string; mine: boolean; edited: boolean; stage_entry: boolean }[]
  documents: { id: number; category: string; filename: string; uploaded_by: string; uploaded_at: string }[]
  doc_categories: string[]; users: { id: number; name: string }[]; roles: string[]; external_roles: string[]
  can: { manage: boolean; tasks: boolean; docs: boolean; move: boolean; note: boolean; download: boolean; create: boolean; delete_doc?: boolean; delete_project?: boolean }
}
export const projectExtras = (id: number) => getJson<ProjectExtras>(`/api/projects/${id}`)

// Post to one of Flask's form routes and read its flashes back as JSON. The
// route is unchanged (same permission, audit row and validation); only the
// answer differs because we ask for JSON.
export type FormReply = { ok: true; messages: string[]; undo: string | null; location: string | null }
export async function postForm(path: string, fields: Record<string, string> | FormData = {}): Promise<FormReply> {
  if (!csrfToken) await session()
  const body = fields instanceof FormData ? fields : new URLSearchParams(fields)
  const res = await fetch(path, { method: "POST", credentials: "same-origin", body, headers: { Accept: "application/json", "X-CSRF-Token": csrfToken ?? "" } })
  if (!res.ok) throw new ApiError(res.status, res.status === 403 ? "You cannot do that on this project" : res.status === 404 ? "Not found" : `Request failed (${res.status})`)
  const data = (await res.json().catch(() => null)) as FormReply | null
  if (!data) throw new ApiError(res.status, "Your session has ended — sign in again")
  return data
}

// ---- settings ----
export type Policy = {
  key: string; area: "general" | "security" | "people" | "workflow" | "notifications" | "integrations" | "backups" | "reports" | "audit"
  kind: "int" | "bool" | "choice" | "multi" | "text" | "url" | "domains" | "emails" | "time" | "lines"
  label: string; help: string; value: number | boolean | string | string[]; min?: number; max?: number; choices?: string[]; multiline?: boolean
}
export type BackupRun = {
  id: number; started_at: string; finished_at: string | null; trigger: string; actor: string | null; file: string | null
  size_bytes: number | null; ok: boolean; restore_ok: boolean | null; restore_detail: string | null; destinations: string | null
}
export type BackupsView = { runs: BackupRun[]; scheduler_seen: string | null; scheduler_alive: boolean; next_run: string | null }
export type SettingsData = {
  templates: { id: number; name: string; projects: number; stages: { id: number; name: string; sla_days: number | null }[] }[]
  doc_categories: { id: number; name: string }[]
  alerts: { key: string; title: string; severity: "critical" | "warning" | "info"; threshold_days: number | null; notify_email: boolean; notify_teams: boolean; notify_inapp: boolean }[]
  m365: {
    oauth_client_configured: boolean; azure_app: { client_id: string | null; tenant_id: string | null; has_secret: boolean; source: string | null }
    connected: boolean; connected_email: string | null; team_name: string | null; channel_name: string | null; channel_id: string | null
    teams: { id: string; name: string }[]; channels: { id: string; name: string }[]; team_id: string; teams_error: string | null
  }
  toggles: Record<"notify_email_enabled" | "notify_teams_enabled" | "onedrive_mirror_uploads_enabled" | "guest_links_enabled", boolean>
  backups: BackupsView | null
  api_tokens: { id: number; name: string; created_by: string; created_at: string; expires_at: string; last_used_at: string | null; revoked_at: string | null }[]
  audit_archives: { name: string; size: number }[]
  public_url_set: boolean
  policies: Policy[]
  sso: { client_id: string | null; tenant_id: string | null; has_secret: boolean; configured: boolean; enforced: boolean; redirect_uri: string; password_admins: number }
}
export const settingsData = (section: string, teamId = "") =>
  getJson<SettingsData>(`/api/settings?section=${encodeURIComponent(section)}${teamId ? `&team_id=${encodeURIComponent(teamId)}` : ""}`)

export type RbacData = { roles: string[]; permissions: string[]; matrix: Record<string, Record<string, boolean>>; locked: Record<string, string[]> }
export const rbac = () => getJson<RbacData>("/api/settings/rbac")
export type ContactsData = {
  lists: { key: string; label: string; has_email: boolean; items: { id: number; name: string; email: string | null }[] }[]
  partners: { id: number; name: string; managers: { id: number; name: string; email: string | null }[] }[]
}
export const contacts = () => getJson<ContactsData>("/api/settings/contacts")

// ---- admin: users and the audit log ----
export type AdminUser = {
  id: number; username: string; name: string; email: string | null; role: string; active: boolean; kind: "internal" | "external"
  last_login_at: string | null; created_at: string | null; avatar_url: string | null; pending: boolean; password_login: boolean; microsoft: boolean
  notify_via?: "email" | "teams"; signup_label?: string | null; signup_project?: string | null; signup_project_role?: string | null
}
export type UsersData = { users: AdminUser[]; roles: string[]; me: number; microsoft_only: boolean }
export const users = () => getJson<UsersData>("/api/users")
export type AuditRow = { id: number; timestamp: string; username: string; action: string; resource_type: string | null; resource_id: number | null; resource_name: string | null; details: string | null; ip_address: string | null }
export type AuditData = {
  rows: AuditRow[]; page: number; total: number; total_pages: number
  filters: { user: string; action: string; project_id: string; from: string; to: string }
  usernames: string[]; actions: string[]; projects: { id: number; name: string }[]
}
export const audit = (query: string) => getJson<AuditData>(`/api/audit${query ? `?${query}` : ""}`)

// ---- reports ----
export type PortfolioRow = {
  id: number; name: string; client: string; stage: string; owner_name: string; delivery_mode: string; vendor_name: string | null; product_name: string | null; target_end_date: string | null
  rag: Rag; reasons?: string[]; confidence?: string; pct_complete: number; stage_number: number; stage_count: number
  start: string; forecast: string | null; planned: string | null; baseline?: string | null; vs_target_days: number | null; vs_baseline_days?: number | null; has_plan: boolean
  open: { blocker: number; issue: number; risk: number }; report: { version: number; kind: string; created_at: string } | null
}
export type ReportAllData = {
  audience: "internal" | "customer"; generated_at: string; today: string; company: string; template?: DocConfig
  summary: { count: number; health: Partial<Record<Rag, number>>; late_vs_target: number; behind_baseline: number | null; avg_slip: number | null; blockers: number; finishing_30d: number; no_plan: number }
  rows: PortfolioRow[]
  risks: { project_id: number; project: string; kind: RaidKind; title: string; impact: string; status: string; owner_name: string | null; due_date: string | null }[]
}
export const reportAll = (template?: number | null) => getJson<ReportAllData>(`/api/reports/all${template ? `?template=${template}` : ""}`)
export type ReportData = {
  project: { id: number; name: string; client: string; owner_name: string; stage: string }
  versions: { version: number; created_by: string; created_at: string }[]
  current: { version: number; created_by: string; created_at: string } | null
  blocks: ["h" | "li" | "p", string][]; editor_text: string; can_edit: boolean; is_draft: boolean
}
export const report = (id: number, query: string) => getJson<ReportData>(`/api/projects/${id}/report${query ? `?${query}` : ""}`)

// ---- account, my work, alerts, analytics ----
export const account = () => getJson<{ username: string; name: string; email: string | null; kind: "internal" | "external"; must_change_password: boolean; theme: "system" | "light" | "dark"; accent: string; avatar_url: string | null
  email_kinds: { key: string; label: string; on: boolean }[]; mail_enabled: boolean; home: "dashboard" | "board"; activity: Activity | null; activity_viewers: string[]; notify_via: "email" | "teams"; teams_ready: boolean }>("/api/account")
// active minutes (services/activity.py): today, 7 and 30 days, one row per day
export type Activity = { today: number; week: number; month: number; days: { day: string; minutes: number }[]; last_seen_at: string | null; last_login_at: string | null }
// sign-up links (services/signup.py): admins make them; a new colleague fills /join/<token>
export type SignupLink = { id: number; label: string; role: string; project_id: number | null; project: string | null; project_role: string | null
  max_uses: number; uses: number; expires_at: string; created_by: string; created_at: string; state: "open" | "expired" | "used up" | "revoked" }
export type SignupLinks = { links: SignupLink[]; enabled: boolean; default_days: number; roles: string[]; project_roles: string[]; projects: { id: number; name: string }[] }
export const signupLinks = () => getJson<SignupLinks>("/api/signup-links")
export const createSignupLink = (b: { label: string; role: string; project_id: number | null; project_role: string | null; days: number; max_uses: number }) =>
  post<{ ok: true; link: string }>("/api/signup-links", b)
export const revokeSignupLink = (id: number) => post<{ ok: true }>(`/api/signup-links/${id}/revoke`)
export const revokeAllSignupLinks = () => post<{ ok: true; revoked: number }>("/api/signup-links/revoke-all")
export type JoinInfo = { role: string; project: string | null; project_role: string | null; expires_at: string; company: string; domains: string[] }
export const joinInfo = (token: string) => getJson<JoinInfo>(`/api/join/${token}`)
export const joinSubmit = (token: string, b: { name: string; username: string; email: string; password: string; notify_via: "email" | "teams" }) =>
  post<{ ok: true }>(`/api/join/${token}`, b)
// document templates (services/doc_templates.py)
export type DocKind = "rollout" | "portfolio" | "signoff"
export type DocConfig = { title: string; accent: string; logo: string | null; co_logo: string | null; company_line: string; footer: string
  sections: { key: string; on: boolean }[]; texts: Record<string, string> }
export type DocTemplate = { id: number; kind: DocKind; name: string; is_default: boolean; config: DocConfig; updated_at: string; updated_by: string }
export type DocTemplatesData = {
  templates: DocTemplate[]; placeholders: Record<string, string>; accents: string[]
  kinds: Record<DocKind, { label: string; sections: { key: string; label: string }[]; texts: { key: string; label: string; help: string }[]; default: DocConfig }>
}
export const docTemplates = () => getJson<DocTemplatesData>("/api/doc-templates")
export const saveDocTemplate = (kind: DocKind, name: string, config: DocConfig, id?: number) =>
  id ? send<{ ok: true }>(`/api/doc-templates/${id}`, "PUT", { kind, name, config }) : post<{ ok: true; id: number }>("/api/doc-templates", { kind, name, config })
export const deleteDocTemplate = (id: number) => send<{ ok: true }>(`/api/doc-templates/${id}`, "DELETE")
export const defaultDocTemplate = (id: number) => post<{ ok: true }>(`/api/doc-templates/${id}/default`)
export const docTemplateChoices = (kind: DocKind) => getJson<{ choices: { id: number; name: string; is_default: boolean }[] }>(`/api/doc-templates/choices?kind=${kind}`)
async function raw(path: string, body: BodyInit, json = false): Promise<Response> {
  if (!csrfToken) await session()
  const res = await fetch(path, { method: "POST", credentials: "same-origin", body, headers: { "X-CSRF-Token": csrfToken ?? "", ...(json ? { "Content-Type": "application/json" } : {}) } })
  if (!res.ok) { const d = (await res.json().catch(() => ({}))) as { error?: string }; throw new ApiError(res.status, d.error ?? `Request failed (${res.status})`) }
  return res
}
export async function uploadDocLogo(file: File): Promise<string> {
  const fd = new FormData(); fd.append("file", file)
  return ((await (await raw("/api/doc-templates/logo", fd)).json()) as { name: string }).name
}
export async function previewDocTemplate(kind: DocKind, config: DocConfig): Promise<Blob> {
  return (await raw("/api/doc-templates/preview.pdf", JSON.stringify({ kind, config }), true)).blob()
}
export const pingActivity = () => post<{ ok: true; counted: boolean }>("/api/activity")
export type WorkTask = { id: number; project_id: number; title: string; due_date: string | null; stage: string; done: number; done_at: string | null; project: string; client: string; project_stage: string }
export type WorkProject = { id: number; name: string; client: string; stage: string; state: FlowState; stage_index: number; stages: number; target_end_date: string | null; role: string; owner_name: string }
export type MyWorkData = {
  today: string; tasks: WorkTask[]; done_by_day: { day: string; count: number }[]; projects: WorkProject[]
  counts: { open: number; overdue: number; due_week: number; done_week: number; rollouts: number; stuck: number }
}
export const myWork = () => getJson<MyWorkData>("/api/my-work")

// ---- people ----
export type PersonCard = { id: number; name: string; role: string; avatar_url: string | null; last_login_at: string | null; last_seen_at: string | null; projects: number; open: number; late: number; done_30d: number }
export type PeopleData = { people: PersonCard[]; can_notify: boolean; me: number }
export type PersonData = {
  user: { id: number; name: string; role: string; email: string | null; avatar_url: string | null; last_login_at: string | null; since: string }
  today: string; can_notify: boolean; activity?: Activity
  kpis: { rollouts: number; stuck: number; open: number; late: number; done_30d: number; on_time_pct: number | null }
  projects: WorkProject[]; pending: WorkTask[]; upcoming: WorkTask[]
  contribution: { weeks: { week: string; done: number }[]; notes_30d: number; moves_30d: number }
  recent: { kind: "move" | "note" | "task"; at: string; project_id: number; project: string; text: string }[]
}
export const people = () => getJson<PeopleData>("/api/people")
export const person = (id: number) => getJson<PersonData>(`/api/people/${id}`)
export const notifyPerson = (id: number, message: string, project_id?: number | null) => post<{ ok: true }>(`/api/people/${id}/notify`, { message, project_id: project_id ?? null })
export type AlertsData = {
  rows: { id: number; project_id: number | null; project_name: string | null; alert_type: string; severity: "critical" | "warning" | "info"; title: string; description: string | null; created_at: string; resolved: boolean; resolved_at: string | null }[]
  show_resolved: boolean; alert_type: string; types: Record<string, string>; page: number; total_pages: number; total: number
}
export const alerts = (query: string) => getJson<AlertsData>(`/api/alerts${query ? `?${query}` : ""}`)
export type AnalyticsData = {
  templates: { id: number; name: string }[]; template_id: number | null; slas: Record<string, number | null>; custom_count: number
  stats: null | {
    stages: { stage: string; visits: number; avg_days: number | null; median_days: number | null; max_days: number | null; in_stage_now: number }[]
    aging: { project_id: number; project_name: string; stage: string; days: number }[]
    slowest: { stage: string; avg_days: number } | null; lead_avg: number | null; lead_median: number | null; completed_count: number
    throughput: [string, number][]; measured_projects: number
  }
}
export const analytics = (templateId?: number | null) => getJson<AnalyticsData>(`/api/analytics${templateId ? `?template=${templateId}` : ""}`)

export type ActivityRow = { when: string; who: string; action: string; label: string; details: string }
export const projectActivity = (id: number) => getJson<{ rows: ActivityRow[] }>(`/api/projects/${id}/activity`)

export type SearchResults = { projects: { id: number; name: string; client: string; stage: string }[]; tasks: { id: number; title: string; done: boolean; project_id: number; project_name: string }[] }
export const search = (q: string) => getJson<SearchResults>(`/api/search?q=${encodeURIComponent(q)}`)

// ---- notifications ----
export type Notification = { id: number; kind: string; title: string; body: string | null; link: string | null; actor: string | null; project_name: string | null; created_at: string; read: boolean }
export const notifications = () => getJson<{ unread: number; rows: Notification[] }>("/api/notifications")
export const markRead = (which: { id: number } | { all: true }) => post<{ ok: true; unread: number }>("/api/notifications/read", which)

// ---- the new / duplicate / edit project form ----
export type ProjectFormData = {
  mode: "new" | "duplicate" | "edit"; id: number | null; me: number
  project: Partial<Record<string, string | null>> & { customer_approval?: boolean; stage_template_id?: number | null; owner_id?: number }
  defaults: { stage_template_id: number | null; customer_approval: boolean }
  via_options: string[]; delivery_modes: string[]
  account_managers: { name: string; email: string | null }[]
  partners: { id: number; name: string; managers: { name: string; email: string }[] }[]
  vendors: string[]; products: string[]; outsourcers: { name: string; email: string | null }[]
  templates: { id: number; name: string }[]; users: { id: number; name: string }[]
}
export const projectForm = (query: string) => getJson<ProjectFormData>(`/api/project-form${query ? `?${query}` : ""}`)

// ---- tasks: the same Flask routes the project page posts as forms ----
export const addTask = (projectId: number, task: { title: string; stage: string; assignee_id?: number | null; due_date?: string | null }) =>
  post<{ ok: true; id: number }>(`/projects/${projectId}/tasks`, task)
export const toggleTask = (projectId: number, taskId: number) => post<{ ok: true; done: boolean }>(`/projects/${projectId}/tasks/${taskId}/toggle`, {})
export const deleteTask = (projectId: number, taskId: number) => post<{ ok: true }>(`/projects/${projectId}/tasks/${taskId}/delete`, {})
