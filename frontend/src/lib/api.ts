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
  prefs?: { date_format: DateFormat; undo_minutes: number }
}

export type SignIn = { microsoft: boolean; microsoft_only: boolean }
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

async function post<T>(path: string, body?: unknown): Promise<T> {
  if (!csrfToken) await session()
  const res = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken ?? "" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = (await res.json().catch(() => ({}))) as { error?: string; csrf?: string } & T
  if (data.csrf) csrfToken = data.csrf
  if (!res.ok) throw new ApiError(res.status, data.error ?? `Request failed (${res.status})`)
  return data
}

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
}
export type FlowData = { stages: string[]; rows: FlowRow[]; counts: Record<FlowState, number>; can_move: boolean }
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

// ---- projects list ----
export type ProjectRow = {
  id: number; name: string; client: string; po_number: string | null; stage: string; stages: string[]; stage_index: number; closed: boolean
  owner_name: string; delivery_mode: string; vendor_name: string | null; product_name: string | null; target_end_date: string | null; updated_at: string
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
  can: { manage: boolean; tasks: boolean; docs: boolean; move: boolean; note: boolean; download: boolean; create: boolean }
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
  key: string; area: "general" | "security" | "workflow" | "notifications" | "backups"; kind: "int" | "bool" | "choice" | "multi" | "text" | "url" | "domains" | "time"
  label: string; help: string; value: number | boolean | string | string[]; min?: number; max?: number; choices?: string[]
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
export type ReportAllData = { generated_at: string; rows: { id: number; name: string; client: string; stage: string; owner_name: string; delivery_mode: string; vendor_name: string | null; product_name: string | null; target_end_date: string | null }[] }
export const reportAll = () => getJson<ReportAllData>("/api/reports/all")
export type ReportData = {
  project: { id: number; name: string; client: string; owner_name: string; stage: string }
  versions: { version: number; created_by: string; created_at: string }[]
  current: { version: number; created_by: string; created_at: string } | null
  blocks: ["h" | "li" | "p", string][]; editor_text: string; can_edit: boolean; is_draft: boolean
}
export const report = (id: number, query: string) => getJson<ReportData>(`/api/projects/${id}/report${query ? `?${query}` : ""}`)

// ---- account, my work, alerts, analytics ----
export const account = () => getJson<{ username: string; name: string; email: string | null; kind: "internal" | "external"; must_change_password: boolean; theme: "system" | "light" | "dark"; accent: string; avatar_url: string | null
  email_kinds: { key: string; label: string; on: boolean }[]; mail_enabled: boolean }>("/api/account")
export type MyWorkData = {
  tasks: { id: number; title: string; project_id: number; project_name: string; due_date: string | null; overdue: boolean; stage: string | null }[]
  projects: { id: number; name: string; client: string; stage: string; schedule: "overdue" | "at_risk" | "on_track" | null; target_end_date: string | null }[]
}
export const myWork = () => getJson<MyWorkData>("/api/my-work")
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
