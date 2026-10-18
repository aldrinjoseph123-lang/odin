import type { DateFormat } from "@/lib/format"
// One thin client for Flask's JSON API. Same session cookie as the Jinja
// pages; every mutation carries the CSRF token from /api/session as a header.

export type User = {
  id: number
  name: string
  role: "Admin" | "Member" | "Contributor" | "Viewer" | "External"
  kind: "internal" | "external"
  must_change_password: boolean
  must_enroll_mfa?: boolean
  permissions: string[]
  nav: Nav
  theme: "system" | "light" | "dark"
  accent: string
  avatar_url: string | null
  home: "dashboard" | "board"
  prefs?: { date_format: DateFormat; undo_minutes: number; password_min_length?: number; activity_idle_minutes?: number }
  external_role?: string | null   // an external's project role ("Customer", "Vendor", …) when the server names it
}

export type SignIn = { microsoft: boolean; microsoft_only: boolean; link_minutes?: number; password_min_length?: number }
type SessionResponse = { csrf: string; user: User | null; messages?: string[]; signin?: SignIn; version?: string; timezone?: string }

let csrfToken: string | null = null


export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const SIGNED_OUT = "You were signed out. Sign in again to carry on (open Odin in a new tab to keep what you typed)."

// What a failed request tells the person: what went wrong and what to do,
// never "Request failed (500)" (test report UX-6, UX-7).
export function failureText(status: number): string {
  if (status === 0) return "Could not reach Odin. Check your connection and try again."
  if (status === 401) return SIGNED_OUT
  if (status === 403) return "You do not have access to this."
  if (status === 404) return "Not found. It may have been deleted, or you are not on it."
  if (status === 409) return "Someone changed this at the same moment. Reload and try again."
  if (status === 413) return "That file is too large."
  if (status === 429) return "Too many attempts. Wait a minute and try again."
  if (status >= 500) return "Odin could not do that just now. Try again in a moment."
  return `Odin could not do that (error ${status}). Reload the page and try again.`
}

// fetch, with a dropped connection as an ApiError like any other failure
async function call(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(path, { credentials: "same-origin", ...init })
  } catch {
    throw new ApiError(0, failureText(0))
  }
}

// A failed session check (a 502 page while Odin restarts, a dropped
// connection) is an ApiError like any other, so the page can offer a retry
// instead of going blank.
export async function session(): Promise<SessionResponse> {
  const res = await call("/api/session")
  const data = res.ok ? ((await res.json().catch(() => null)) as SessionResponse | null) : null
  if (!data) throw new ApiError(res.ok ? 500 : res.status, failureText(res.ok ? 500 : res.status))
  csrfToken = data.csrf
  return data
}

// The release this page was loaded with is the first /api/session answer's; a
// different one later means Odin was updated while the tab stayed open (advice A20).
let pageVersion: string | null = null
export function newerVersion(v?: string): boolean {
  if (!v) return false
  pageVersion ??= v
  return v !== pageVersion
}

// A crash the person saw reaches the server's log (never the audit log), as a
// beacon so it survives the page going away (advice A6). The server's own
// refusals (ApiError) are already in its log; a render loop sends a handful.
let reported = 0
export function reportClientError(kind: "render" | "error" | "rejection", e: unknown) {
  if (e instanceof ApiError || ++reported > 5) return
  const err = e instanceof Error ? e : new Error(String(e))
  const body = JSON.stringify({ kind, message: err.message.slice(0, 500), stack: (err.stack ?? "").slice(0, 3000), path: location.pathname, version: pageVersion })
  try { navigator.sendBeacon?.("/api/client-errors", new Blob([body], { type: "application/json" })) } catch { /* reporting never throws */ }
}

// A mutation with the CSRF token. A stale token (the session was renewed in
// another tab, Odin restarted) answers 400 with a fresh one: take it (or ask
// /api/session) and send once more, so saves do not fail until a reload.
export function csrfRejected(status: number, data: { csrf?: string; error?: string } | null): boolean {
  return status === 400 && !!data && (!!data.csrf || /csrf/i.test(data.error ?? ""))
}
async function withToken(path: string, init: RequestInit): Promise<Response> {
  if (!csrfToken) await session()
  const go = () => call(path, { ...init, headers: { ...(init.headers as Record<string, string>), "X-CSRF-Token": csrfToken ?? "" } })
  const res = await go()
  if (res.status !== 400) return res
  const data = (await res.clone().json().catch(() => null)) as { csrf?: string; error?: string } | null
  if (!csrfRejected(res.status, data)) return res
  if (data?.csrf) csrfToken = data.csrf
  else await session().catch(() => null)
  return go()
}

// The error for a failed response. A session that has ended says so (the
// server marks it); otherwise the server's own words when it gave some (a
// wrong password, a taken username); a bare 400/401 checks the session.
async function failure(res: Response, said?: string): Promise<ApiError> {
  if (res.headers.get("X-Odin-Signed-Out")) return new ApiError(401, SIGNED_OUT)
  if (said) return new ApiError(res.status, said)
  if (res.status === 400 || res.status === 401) {
    const alive = await fetch("/api/session", { credentials: "same-origin" }).then((r) => r.json()).then((d: SessionResponse) => !!d.user).catch(() => true)
    if (!alive) return new ApiError(401, SIGNED_OUT)
  }
  return new ApiError(res.status, failureText(res.status))
}

// A 200 HTML page where JSON was asked for is the sign-in page after a
// redirect: never a success.
function notJson(res: Response) {
  return res.ok && (res.headers.get("Content-Type") ?? "").includes("text/html")
}

// One JSON request with the CSRF token; every mutation goes through here.
async function send<T>(path: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<T> {
  const res = await withToken(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (notJson(res)) throw new ApiError(401, SIGNED_OUT)
  const data = (await res.json().catch(() => ({}))) as { error?: string; csrf?: string } & T
  if (data.csrf) csrfToken = data.csrf
  if (!res.ok) throw await failure(res, data.error)
  return data
}
const post = <T,>(path: string, body?: unknown) => send<T>(path, "POST", body)

export function login(username: string, password: string) {
  return post<{ user?: User; csrf: string; code_needed?: boolean }>("/api/login", { username, password })
}

// After the password, when two-step sign-in is on: the authenticator code or a recovery code.
// 410 or 429 means start again from the password.
export function loginCode(code: string) {
  return post<{ user: User; csrf: string }>("/api/login/code", { code })
}

export type TwoStep = { enabled: boolean; enabled_at: string | null; required: boolean; recovery_left: number; password: boolean }
export const twoStep = () => getJson<TwoStep>("/api/account/two-step")
export const accountMicrosoft = () => getJson<{ available: boolean; linked: boolean }>("/api/account/microsoft")
export const accountEmail = () => getJson<{ email: string | null; verified: boolean; checkable: boolean }>("/api/account/email")
// re-enrolling while two-step is on also needs a current code (or a recovery code)
export const twoStepSetup = (password: string, code?: string) => post<{ secret: string; uri: string; qr_svg: string }>("/api/account/two-step/setup", code ? { password, code } : { password })
export const twoStepConfirm = (code: string) => post<{ ok: true; recovery_codes: string[] }>("/api/account/two-step/confirm", { code })
export const twoStepOff = (password: string, code: string) => post<{ ok: true }>("/api/account/two-step/off", { password, code })
export const twoStepCodes = (password: string, code: string) => post<{ ok: true; recovery_codes: string[] }>("/api/account/two-step/recovery-codes", { password, code })

export function logout() {
  return post<{ ok: true; csrf: string }>("/api/logout")
}

export type Nav = { active_alert_count: number; my_open_task_count: number; unread_notifications: number; projects_nav_url: string }

// from_stage: the stage the page showed; the server answers 409 when the rollout has moved on since.
// override: the typed reason for moving past a stage gate (Admin or the project manager)
export function changeStage(projectId: number, stage: string, note = "", fromStage?: string, override?: string) {
  return post<{ ok: true; undo: string }>(`/api/projects/${projectId}/stage`, { stage, note, from_stage: fromStage, override })
}

// ---- Flow: first screen ----
export type FlowState = "overdue" | "over_sla" | "due_soon" | "on_track"
export type ApprovalStatus = "pending" | "approved" | "declined" | "superseded"
export type FlowRow = {
  id: number; name: string; client: string; stage: string; stages: string[]; stage_index: number; owner_name: string; mine: boolean
  team: { id: number; name: string; avatar_url: string | null }[]
  approval: ApprovalStatus | null
  delivery_mode: string; target_end_date: string | null; days_in_stage: number | null; sla_days: number | null
  over_by: number | null; state: FlowState; open_tasks: number; total_tasks: number; late_tasks: number; late_since: string | null
  next_task: { title: string; due_date: string | null; assignee: string | null } | null; updated_at: string
  idle_days: number | null; stale: boolean
  // the Kanban's drag: the one stage a drop may go to, and whether this person may make the move
  start_date: string | null; next_stage: string | null; can_move: boolean; signoff_needed: boolean
  // a stage gate holds the next move (staff only; services/gates.py)
  gate_blocked: boolean; gate_reasons: string[]
}
export type FlowData = { stages: string[]; rows: FlowRow[]; counts: Record<FlowState | "late_tasks", number>; can_move: boolean; today: string
  pending?: PendingIntakeRow[] }   // CRM intakes in the List's holding lane (staff only; counted nowhere)
export type FlowStage = { name: string; status: "done" | "current" | "next"; sla_days: number | null; entered_at: string | null; days: number | null }
// waits_on: the tasks it waits on (finish-to-start); blocked_by: the open ones among them, and how late each is
export type Recurrence = "weekly" | "fortnightly" | "monthly"
export type TaskWait = { id: number; title: string; late_by: number }
export type FlowTask = { id: number; title: string; done: boolean; done_at?: string | null; due_date: string | null; assignee: string | null; assignee_id: number | null; assignee_avatar_url: string | null; stage: string
  estimate_hours?: number | null; waits_on?: number[]; blocked_by?: TaskWait[]
  recurrence?: Recurrence | null; recur_until?: string | null } & TaskAsk
// What a task asks for (services/asks.py): a tick, a document of one category, or a short form.
// On someone outside (a customer, reseller or contractor) it is an ask: theirs alone.
export type AskKind = "task" | "upload" | "form"
export type AskQuestionKind = "text" | "number" | "date" | "choice" | "yesno"
export type AskQuestion = { key?: string; label: string; kind: AskQuestionKind; choices?: string[]; required?: boolean }
export type TaskAsk = { kind?: AskKind; ask_category?: string | null; questions?: AskQuestion[] }
export type Ask = {
  id: number; title: string; kind: AskKind; done: boolean; done_at: string | null; due_date: string | null; assignee: string; assignee_role: string
  category: string | null; questions: AskQuestion[]; answers: { key: string; label: string; value: string }[]
  answered_by: string | null; answered_at: string | null; file: { id: number; filename: string; review: DocReview } | null
}
// an outside party's upload waits for staff review (services/doc_review.py): it cannot be opened until accepted
export type DocReview = "accepted" | "pending"
// the customer's rating at sign-off: staff only (an external's list is always empty)
export type Rating = { signoff_version: number; rating: number; comment: string | null; by_name: string; at: string }
export type AsksData = { asks: Ask[]; ratings: Rating[] }
export const asks = (id: number) => getJson<AsksData>(`/api/projects/${id}/asks`)
export const answerAsk = (id: number, taskId: number, answers: Record<string, string | boolean>) => post<{ ok: true }>(`/api/projects/${id}/asks/${taskId}/answers`, { answers })
// an upload ask goes through the documents route, into the ask's own category
export function uploadAsk(id: number, taskId: number, file: File) {
  const form = new FormData()
  form.append("file", file); form.append("ask_id", String(taskId))
  return postForm(`/projects/${id}/documents`, form)
}
export type FlowDetail = {
  id: number; name: string; client: string; vendor_name: string | null; product_name: string | null; delivery_mode: string
  outsourcer_name: string | null; owner_name: string; stage: string; stage_index: number; next_stage: string | null
  state: FlowState; over_by: number | null; start_date: string; target_end_date: string | null; days_left: number | null; today: string
  stages: FlowStage[]; tasks: FlowTask[]; documents: number
  recent_notes: { author: string; note: string; stage: string; created_at: string }[]; can_move: boolean
  participants: { id: number; user_id: number; name: string; role: string; avatar_url: string | null }[]
  assignable: { id: number; name: string }[]; can_edit: boolean; me: number; can_override?: boolean; doc_categories?: string[]
  customer_approval: boolean; can_approve: boolean
  approval: { id: number; stage: string; status: ApprovalStatus; decided_by: string | null; comment: string | null; chases?: number } | null
  signoff?: SignoffState
  // reminders Odin sent the signatory (services/chasers.py), staff only; mute or follow (services/notifications.py)
  signoff_chases?: number
  watch?: Watch
  // what holds the next move (services/gates.py); null for partners and customers
  gate?: { blocked: GateReason[]; can_override: boolean } | null
}
export type Watch = { can: "mute" | "follow" | null; on: boolean }
export const setWatch = (projectId: number, on: boolean) => post<Watch>(`/api/projects/${projectId}/watch`, { on })
export type GateReason = { stage: string; kind: "tasks" | "document"; count?: number; category?: string; text: string }
// what a stage asks before a rollout leaves it
export type StageGate = { gate_tasks: boolean; required_docs: string[] }
export const decideApproval = (projectId: number, approvalId: number, decision: "approved" | "declined", comment = "") =>
  post<{ ok: true }>(`/api/projects/${projectId}/approvals/${approvalId}`, { decision, comment })
async function getJson<T>(path: string): Promise<T> {
  const res = await call(path)
  // the server's own words when it gave some (review P3-30); a proxy's HTML error page gives none
  if (!res.ok) throw await failure(res, ((await res.json().catch(() => null)) as { error?: string } | null)?.error)
  if (notJson(res)) throw new ApiError(401, SIGNED_OUT)
  return res.json()
}
export const flow = () => getJson<FlowData>("/api/flow")
export const flowDetail = (id: number) => getJson<FlowDetail>(`/api/projects/${id}/flow`)

// ---- the plan and the RAID register (services/plan.py, services/raid.py) ----
export type Rag = "green" | "amber" | "red" | "done"
// working: stage lengths count working days; week: Python weekday numbers (Mon = 0); off: holidays
export type WorkCalendar = { working: boolean; week: number[]; off: string[] }
export type PlanStage = {
  id: number; name: string; position: number; sla_days: number | null; status: "done" | "skipped" | "current" | "next"
  plan_start: string | null; plan_end: string | null; base_start: string | null; base_end: string | null
  actual_start: string | null; actual_end: string | null; forecast_start: string | null; forecast_end: string | null
  planned_days: number; actual_days: number | null; slip_days: number | null; suggested_start: string; suggested_end: string
  forecast_reason?: string | null   // the task that moved the forecast through its links, when one did
}
export type PlanData = {
  stages: PlanStage[]; has_plan: boolean; baseline_at: string | null; today: string; closed: boolean; default_days: number; pct_complete: number; calendar?: WorkCalendar
  finish: { forecast: string | null; planned: string | null; baseline: string | null; target: string | null; vs_target_days: number | null; vs_baseline_days: number | null; days_to_target: number | null }
  health: { rag: Rag; reasons: string[]; confidence: "high" | "medium" | "low" }
  changes: { stage: string | null; field: string; old: string | null; new: string | null; reason: string | null; author: string; created_at: string }[]
  can_edit: boolean; project: { id: number; name: string; start_date: string | null; target_end_date: string | null }
}
export const plan = (id: number) => getJson<PlanData>(`/api/projects/${id}/plan`)
// the Flow's Gantt: every open rollout's stages at once (staff only)
export type GanttStage = Pick<PlanStage, "id" | "name" | "status" | "sla_days" | "plan_start" | "plan_end" | "base_start" | "base_end" | "actual_start" | "actual_end" | "forecast_start" | "forecast_end" | "suggested_start" | "suggested_end" | "slip_days">
export type GanttRow = {
  id: number; name: string; client: string; stage: string; owner_name: string; start_date: string | null; target_end_date: string | null
  forecast: string | null; pct_complete: number; rag: Rag; has_plan: boolean; baselined: boolean; can_edit: boolean; stages: GanttStage[]
}
export type GanttData = { today: string; calendar: { working: boolean; week: number[]; off: string[] } | null; rows: GanttRow[] }
export const flowPlan = () => getJson<GanttData>("/api/flow/plan")
export const savePlan = (id: number, stages: { id: number; plan_start: string | null; plan_end: string | null }[], reason: string) =>
  send<{ ok: true; changed: number; baselined: boolean; warning?: string }>(`/api/projects/${id}/plan`, "PUT", { stages, reason })
export const rebaseline = (id: number, reason: string) => post<{ ok: true }>(`/api/projects/${id}/plan/baseline`, { reason })
export type ReportWords = { summary: string; next_steps: string; asks: string; suggested?: { summary: string; next_steps: string; asks: string }; blocks?: ["h" | "li" | "p", string][] }
export type ReportPayload = {
  audience: "internal" | "customer"; generated_at: string; today: string; company: string
  template?: DocConfig
  project: { id: number; name: string; client: string; po_number: string | null; stage: string; owner_name: string; start_date: string; target_end_date: string | null; vendor_name: string | null; product_name: string | null; delivery_mode: string; stage_number: number; stage_count: number }
  health: PlanData["health"]; pct_complete: number; finish: Partial<PlanData["finish"]>; baseline_at: string | null; elapsed_days: number; has_plan: boolean
  stages: PlanStage[]; milestones: { stage: string; start: string | null; end: string | null; planned_end: string | null; gate?: string }[]
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
  fields?: { name: string; kind: FieldKind; value: FieldValue; customer_visible: boolean }[]   // absent from versions saved before custom fields
  project_milestones?: Milestone[]   // the rollout's own (the customer's copy: those marked for them); absent from versions saved before 2.0
  asks?: Ask[]; csat?: Rating[]   // internal only, absent from versions saved before 2.0
}
export type RolloutReport = {
  audience: "internal" | "customer"; words: ReportWords; data: ReportPayload | null; is_live: boolean
  version: { version: number; kind: "text" | "snapshot"; created_by: string; created_at: string } | null
  versions: { version: number; kind: "text" | "snapshot"; created_by: string; created_at: string }[]; can_edit: boolean; project: { id: number; name: string; client: string }
}
export const rolloutReport = (id: number, audience: string, v?: number | null, template?: number | null) =>
  getJson<RolloutReport>(`/api/projects/${id}/rollout-report?${new URLSearchParams({ audience, ...(v ? { v: String(v) } : {}), ...(template ? { template: String(template) } : {}) })}`)
export const saveRolloutReport = (id: number, words: { summary: string; next_steps: string; asks: string }, template_id?: number | null, ai_suggestion?: number | null, share = false) =>
  post<{ ok: true; version: number; shared: number }>(`/api/projects/${id}/rollout-report`, { ...words, template_id: template_id ?? null, ai_suggestion: ai_suggestion ?? null, share })
// An AI feature on one rollout (routes/ai.py): can it run, its latest unused
// draft, and the job writing a new one. Drafts are used or dismissed by a person.
export type AISuggestion<T> = { id: number; payload: T; model: string | null; seconds: number | null; created_at: string; status: string }
export type ProjectAI<T> = {
  available: boolean; reason: string | null; label: string; suggestion: AISuggestion<T> | null
  options?: { documents?: SowDocument[]; waiting?: WaitingItem[]; contact?: { name: string; email: string | null } | null } | null
  job: { id: number; status: "queued" | "running" | "done" | "failed"; error: string | null; result: { skipped?: string; suggestion?: number } | null; created_at: string
    progress?: { ahead: number; started_at: string | null; expected_s: number } | null } | null
}
export type WeeklyWordsDraft = { summary: string; next_steps: string[]; asks: string[] }
export const projectAI = <T,>(id: number, key: string) => getJson<ProjectAI<T>>(`/api/projects/${id}/ai/${key}`)
export const requestProjectAI = (id: number, key: string, input?: unknown) => post<{ ok: true; job: number }>(`/api/projects/${id}/ai/${key}`, input === undefined ? undefined : { input })
export const cancelAIJob = (id: number, job: number) => post<{ ok: true }>(`/api/projects/${id}/ai/jobs/${job}/cancel`)
export const dismissAISuggestion = (id: number, suggestion: number) => post<{ ok: true }>(`/api/projects/${id}/ai/suggestions/${suggestion}/dismiss`)
export type WaitingItem = { what: string; since?: string; days_waiting?: number; due?: string; days_overdue?: number }
export type ChaseDraft = { subject: string; body: string }
export type SlaProposal = { key: string; template_id: number; template: string; stage_id: number; stage: string; current: number | null; proposed: number
  visits: number; median: number; p80: number; unit: string; reason: string | null }
export const slaProposals = () => getJson<{ proposals: SlaProposal[]; model: string | null }>("/api/settings/sla-proposals")
export type Lesson = { id?: number; kind: "avoid" | "repeat"; text: string; evidence: string | null }
export type SimilarRollout = { id: number; name: string; client: string; stage: string; why: string[]; lessons: Lesson[]
  risks: { kind: string; title: string; impact: string; status: string; resolution: string | null }[] }
export type LessonsData = { lessons: (Lesson & { id: number; created_by: string; created_at: string })[]; similar: SimilarRollout[]; can_edit: boolean; can_add_risk: boolean }
export const lessonsOf = (id: number) => getJson<LessonsData>(`/api/projects/${id}/lessons`)
export const saveLessons = (id: number, items: Lesson[], ai_suggestion?: number | null) => post<{ ok: true; saved: number }>(`/api/projects/${id}/lessons`, { items, ai_suggestion: ai_suggestion ?? null })
export const deleteLesson = (id: number, lesson: number) => post<{ ok: true }>(`/api/projects/${id}/lessons/${lesson}/delete`)
export type MinutesTask = { title: string; owner: string | null; assignee_id: number | null; stage: string | null; due_date: string | null; due_text: string; quote: string }
export type AskAnswer = { question: string; answer: string; found: boolean; sources: { n: number; kind: string; from: string; href: string }[] }
export type CatchUp = { where_it_stands: string; who_is_who: string; what_changed: string; waiting: string[]; watch_out: string[] }
export type SowItem = { title: string; detail?: string; stage?: string | null; quote?: string }
export type SowPlan = { scope_items: SowItem[]; tasks: SowItem[]; customer_obligations: SowItem[]; key_dates: { what: string; date: string }[]; exclusions: string[] }
export type SowDocument = { id: number; filename: string; category: string; likely: boolean }
export const closeAISuggestion = (id: number, suggestion: number, taken: number) => post<{ ok: true }>(`/api/projects/${id}/ai/suggestions/${suggestion}/close`, { taken })
export type RaidProposal = { kind: "risk" | "issue" | "blocker" | "decision"; title: string; detail: string; impact: "low" | "medium" | "high"; likelihood: "low" | "medium" | "high" | null; evidence: string }
export type RaidProposals = { proposals: RaidProposal[]; decisions?: Record<string, { decision: "accepted" | "dismissed"; by: string; raid_id: number | null }> }
export const decideAIProposal = (id: number, suggestion: number, index: number, decision: "accepted" | "dismissed", raid_id?: number) =>
  post<{ ok: true; status: string }>(`/api/projects/${id}/ai/suggestions/${suggestion}/items/${index}`, { decision, raid_id: raid_id ?? null })
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

// ---- milestones (services/milestones.py): dated commitments; partners and customers read the ones marked for the customer ----
export type Milestone = {
  id: number; project_id: number; name: string; date: string; stage: string | null; customer_visible: boolean
  done: boolean; done_at: string | null; missed: boolean; created_by: string; created_at: string
}
export type MilestonesData = { items: Milestone[]; stages: string[]; can_edit: boolean; can_delete: boolean }
export const milestones = (id: number) => getJson<MilestonesData>(`/api/projects/${id}/milestones`)
export const saveMilestone = (projectId: number, m: { name: string; date: string; stage: string | null; customer_visible: boolean; done?: boolean }, milestoneId?: number) =>
  milestoneId ? send<{ ok: true }>(`/api/projects/${projectId}/milestones/${milestoneId}`, "PUT", m) : post<{ ok: true; id: number }>(`/api/projects/${projectId}/milestones`, m)
export const deleteMilestone = (projectId: number, milestoneId: number) => send<{ ok: true }>(`/api/projects/${projectId}/milestones/${milestoneId}`, "DELETE")

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
  superseded_at?: string | null   // set when the rollout was reopened after this version was signed: it stays on record but closes nothing
}
export type SignoffDraft = { summary: string; delivered: string[]; outstanding: string[]; terms: string[]; scope: ScopeItem[]; statement: string }
export type SignoffData = {
  not_yet?: string | null
  project: { id: number; name: string; client: string; stage: string; owner_id: number }
  state: SignoffState
  versions: { version: number; status: SignoffStatus; created_at: string; created_by: string }[]
  current: SignoffVersion | null
  can: { manage: boolean; sign: boolean; countersign: boolean; upload: boolean; withdraw: boolean; waive: boolean }
  me: { name: string }
  draft?: SignoffDraft
  candidates?: { signers: { id: number; name: string; role: string; email: string }[]; countersigners: { id: number; name: string; role: string }[]; default_counter_id: number | null }
}
export type SignBody = { name: string; title: string; accept: boolean; signature: Signature; rating?: number | null; rating_comment?: string }
export const signoff = (id: number, v?: number | null, template?: number | null) =>
  getJson<SignoffData>(`/api/projects/${id}/signoff${v ? `?v=${v}` : template ? `?template=${template}` : ""}`)
export const sendSignoff = (id: number, body: { summary: string; delivered: string[]; outstanding: string[]; terms: string[]; signer_id: number; counter_id: number; template_id?: number | null; ai_suggestion?: number | null }) =>
  post<{ ok: true; version: number }>(`/api/projects/${id}/signoff`, body)
export const signSignoff = (id: number, v: number, body: SignBody, counter = false) => post<{ ok: true }>(`/api/projects/${id}/signoff/${v}/${counter ? "countersign" : "sign"}`, body)
export const rejectSignoff = (id: number, v: number, comment: string) => post<{ ok: true }>(`/api/projects/${id}/signoff/${v}/reject`, { comment })
// link is null when the server emailed it instead (or will not hand it out): then `message` says what happened
export type SignoffLink = { ok: true; link: string | null; minutes: number; email: string; emailed?: boolean; message?: string }
export const signoffLink = (id: number, v: number) => post<SignoffLink>(`/api/projects/${id}/signoff/${v}/link`)
export const withdrawSignoff = (id: number, v: number) => post<{ ok: true }>(`/api/projects/${id}/signoff/${v}/withdraw`)
export const waiveSignoff = (id: number, reason: string) => post<{ ok: true; version: number }>(`/api/projects/${id}/signoff/waive`, { reason })
export async function uploadSignoff(id: number, v: number, form: FormData): Promise<{ ok: true }> {
  const res = await withToken(`/api/projects/${id}/signoff/${v}/upload`, { method: "POST", body: form })
  const data = (await res.json().catch(() => ({}))) as { error?: string; ok?: true }
  if (!res.ok) throw await failure(res, data.error)
  return data as { ok: true }
}

// ---- calendar (a view on the Flow page) ----
export type CalendarData = {
  month: string; today: string; from: string; to: string
  spans: { id: number; name: string; client: string; stage: string; start_date: string; target_end_date: string | null; state: FlowState }[]
  targets: { id: number; name: string; client: string; day: string; state: FlowState }[]
  tasks: { id: number; project_id: number; title: string; day: string; done: number; project: string; who: string | null; can_edit: boolean }[]
  moves: { project_id: number; project: string; day: string; prev_stage: string; stage: string; who: string }[]
  approvals: { project_id: number; project: string; stage: string; day: string; kind: "asked" | "decided"; status: ApprovalStatus; who: string | null }[]
  milestones: { id: number; project_id: number; project: string; name: string; day: string; stage: string | null; done: number; customer_visible: boolean }[]
}
export const calendar = (month: string) => getJson<CalendarData>(`/api/calendar?month=${encodeURIComponent(month)}`)

// ---- dashboard ----
export type DashKey = "active" | "overdue" | "over_sla" | "due_soon" | "awaiting" | "idle"
export type Person = { id: number; name: string; avatar_url: string | null }
export type WidgetSetting = { key: string; label: string; kind: "int" | "choice" | "multi" | "text"; default: unknown; choices?: string[]; min?: number; max?: number }
export type WidgetInfo = { id: string; title: string; blurb: string; w: 1 | 2 | 3; multiple: boolean; settings: WidgetSetting[] }
export type DetailRow = { id: number; name: string; client: string; stage: string; text: string }
export type Aggregate = { key: string; count: number }[]
export type AttentionKind = "overdue" | "over_sla" | "due_soon" | "late_task" | "awaiting" | "idle"
export type DashboardData = {
  today: string; version: number; layout: { id: string; uid?: string; w: 1 | 2 | 3; settings: Record<string, unknown> }[]; is_custom: boolean; catalogue: WidgetInfo[]; scope_full: boolean
  data: {
    kpis: { counts: Record<DashKey, number>; before: Record<DashKey, number> | null; since: string | null; moved_this_week: number; series: Record<DashKey, { day: string; v: number }[]>; detail: Record<DashKey, DetailRow[]> }
    aggregates: Record<string, Aggregate>
    attention: { id: number; name: string; client: string; stage: string; worst: AttentionKind; reasons: { kind: AttentionKind; text: string }[] }[]
    timeline: { id: number; name: string; client: string; stage: string; start_date: string; target_end_date: string | null; state: FlowState; progress: number; team: Person[]
                milestones: { name: string; date: string; done: boolean; missed: boolean }[] }[]
    progress: { done: number; current: number; pending: number; pct: number }
    stages: { stage: string; count: number; late: number; warn: number }[]
    completion: { day: string; count: number }[]
    schedule: { due: { id: number; project_id: number; title: string; due_date: string; project: string; stage: string | null; who: string | null; avatar_url: string | null }[]
                approvals: { project_id: number; project: string; stage: string; requested_at: string }[] }
    team: { people: { id: number; name: string; avatar_url: string | null; role: string; projects: number; open: number; late: number }[]; unassigned: number }
    activity: { kind: "move" | "note" | "approval" | "task" | "document"; at: string; who: string | null; project_id: number; project: string; text: string }[]
    alerts: { id: number; project_id: number; project: string; type: string; title: string; severity: string; created_at: string }[]
    mywork: { tasks: { id: number; title: string; project_id: number; project: string; due_date: string | null; stage: string | null }[]; owned: number }
    workload: WorkloadData
    since: SinceData
    cycle: { template: string; lead_avg: number | null; lead_median: number | null; completed_count: number; throughput: [string, number][]; slowest: { stage: string; avg_days: number } | null; measured_projects: number } | null
  }
}
export type SinceItem = { kind: string; at: string; who: string | null; project_id: number; project: string; text: string }
export type SinceData = { from: string; items: SinceItem[] }
export const dashboard = () => getJson<DashboardData>("/api/dashboard")
export const dashboardVersion = () => getJson<{ version: number }>("/api/dashboard/version")
export const saveLayout = (layout: DashboardData["layout"], scope: "mine" | "default" = "mine") =>
  send<{ ok: true; layout: DashboardData["layout"]; is_custom?: boolean }>(scope === "default" ? "/api/dashboard/layout/default" : "/api/dashboard/layout", "PUT", { layout })
export const resetLayout = () => send<{ ok: true; layout: DashboardData["layout"]; is_custom: false }>("/api/dashboard/layout", "DELETE")

// ---- custom fields (services/fields.py): defined in Settings, a value per rollout ----
export type FieldKind = "text" | "number" | "date" | "choice" | "yesno"
export type FieldValue = string | number | boolean | null
export type CustomField = { id: number; name: string; kind: FieldKind; choices: string[]; required: boolean; customer_visible: boolean; show_in_list: boolean; position: number }
export type ProjectField = CustomField & { value: FieldValue }
export type FieldsData = { fields: CustomField[]; kinds: Record<FieldKind, string>; max: number }
export type FieldDraft = Pick<CustomField, "name" | "kind" | "choices" | "required" | "customer_visible" | "show_in_list">
export const customFields = () => getJson<FieldsData>("/api/fields")
export const createField = (f: FieldDraft) => post<{ ok: true; id: number }>("/api/fields", f)
export const updateField = (id: number, f: FieldDraft) => send<{ ok: true }>(`/api/fields/${id}`, "PUT", f)
export const moveField = (id: number, step: -1 | 1) => post<{ ok: true }>(`/api/fields/${id}/move`, { step })
export const deleteField = (id: number, confirm: string) => send<{ ok: true }>(`/api/fields/${id}`, "DELETE", { confirm })
export const projectFields = (id: number) => getJson<{ fields: ProjectField[]; can_edit: boolean }>(`/api/projects/${id}/fields`)
export const saveProjectFields = (id: number, values: Record<string, FieldValue>) =>
  send<{ ok: true; changed: number }>(`/api/projects/${id}/fields`, "PUT", { values })

// ---- automations (services/rules.py): Settings › Automations, admins (manage_rules) ----
export type RuleEvent = "rollout_created" | "stage_entered" | "stage_sla_breached" | "task_overdue" | "ask_completed" | "document_uploaded" | "field_set" | "stage_declined" | "milestone_missed"
export type RuleConditionKind = "stage" | "delivery_mode" | "field" | "client"
// a field's value is held as Odin stores it (yes / no as "1" / "0")
export type RuleCondition = { kind: RuleConditionKind; value: string | null; field_id?: number }
export type RuleAction =
  | { kind: "notify"; roles: string[]; user_ids: number[]; email: boolean; message: string }
  | { kind: "add_task"; template_task_id: number }
  | { kind: "add_raid"; raid_kind: string; title: string; impact: string }
  | { kind: "set_field"; field_id: number; value: string }
  | { kind: "teams"; message: string }
export type RuleActionKind = RuleAction["kind"]
export type RuleDraft = { name: string; event: RuleEvent; event_config: { category?: string; field_id?: number; value?: string | null }; conditions: RuleCondition[]; actions: RuleAction[] }
export type Rule = RuleDraft & { id: number; paused: boolean; created_by: string; created_at: string; updated_at: string; runs: number; last_run: { at: string; ok: boolean } | null }
export type RuleOptions = {
  stages: string[]; delivery_modes: string[]; categories: string[]; roles: string[]; raid_kinds: string[]; raid_levels: string[]
  fields: { id: number; name: string; kind: FieldKind; choices: string[] }[]; users: { id: number; name: string }[]; template_tasks: { id: number; label: string }[]
}
export type RulesData = {
  rules: Rule[]; max: number; keep_days: number; options: RuleOptions
  events: Record<RuleEvent, string>; conditions: Record<RuleConditionKind, string>; actions: Record<RuleActionKind, string>
}
export type RuleRun = { id: number; at: string; ok: boolean; project_id: number | null; project: string | null; what: string; actions: { kind: string; ok: boolean; said: string }[] }
export type DryRun = { matches: { project_id: number; name: string; client: string; times: number; last_at: string; last: string }[]; total: number; replayed: string; caveat: string }
export const rulesData = () => getJson<RulesData>("/api/rules")
export const createRule = (r: RuleDraft) => post<{ ok: true; id: number }>("/api/rules", r)
export const updateRule = (id: number, r: RuleDraft) => send<{ ok: true }>(`/api/rules/${id}`, "PUT", r)
export const pauseRule = (id: number, paused: boolean) => post<{ ok: true }>(`/api/rules/${id}/pause`, { paused })
export const deleteRule = (id: number) => send<{ ok: true }>(`/api/rules/${id}`, "DELETE")
export const ruleRuns = (id: number) => getJson<{ runs: RuleRun[]; keep_days: number }>(`/api/rules/${id}/runs`)
export const dryRunRule = (r: RuleDraft) => post<DryRun>("/api/rules/dry-run", r)

// ---- projects list ----
export type ProjectRow = {
  id: number; name: string; client: string; po_number: string | null; stage: string; stages: string[]; stage_index: number; closed: boolean; state: FlowState
  owner_name: string; delivery_mode: string; vendor_name: string | null; product_name: string | null; target_end_date: string | null; updated_at: string
  total_tasks: number; open_tasks: number; team: { id: number; name: string; avatar_url: string | null }[]
  fields: FieldValue[]   // the list's custom-field columns, in the order of ProjectsData.fields
}
export type ProjectsData = {
  rows: ProjectRow[]; total: number; page: number; total_pages: number; sort: string; dir: "asc" | "desc"
  stages: string[]; delivery_modes: string[]; can_create: boolean
  fields: { id: number; name: string; kind: FieldKind }[]; field_filters: { id: number; name: string; choices: string[] }[]
  pending: number   // CRM intakes waiting for a project manager (the "Pending intake" filter)
}
export const projects = (query: string) => getJson<ProjectsData>(`/api/projects${query ? `?${query}` : ""}`)

// ---- CRM intake (services/intake.py): deals the CRM sent, waiting for a project manager ----
export type PendingIntakeRow = {
  id: number; name: string; client: string; source: string | null; deal_id: string | null; delivery_mode: string
  vendor_name: string | null; product_name: string | null; po_number: string | null; target_end_date: string | null
  contacts: string[]; owner_name: string; created_at: string
}
export type PendingIntake = { rows: PendingIntakeRow[]; can_confirm: boolean; can_lead: boolean; leads: { id: number; name: string }[]; po_category: string }
export const pendingIntake = () => getJson<PendingIntake>("/api/intake/pending")
// the confirm: the PO file, the project manager (when the confirmer cannot move stages) and the PO number
export const confirmIntake = (id: number, form: FormData) => postForm(`/projects/${id}/intake/confirm`, form)
// correct what the CRM sent before confirming (name, client, vendor, product, delivery, target, PO number, field_<id>); audited old → new
export const editIntake = (id: number, fields: Record<string, string>) => postForm(`/projects/${id}/intake/edit`, fields)
export type IntakeCall = {
  id: number; token_name: string; at: string; status: number; result: "created" | "duplicate" | "refused" | "rate_limited"
  deal_id: string | null; project_id: number | null; detail: string | null
}
export type IntakeSettingsData = {
  tokens: { id: number; name: string; created_by: string; created_at: string; expires_at: string; last_used_at: string | null; revoked_at: string | null }[]
  calls: IntakeCall[]; policies: Policy[]; keep: number; templates: { id: number; name: string }[]; owners: { id: number; name: string }[]; endpoint: string
}
export const intakeSettings = () => getJson<IntakeSettingsData>("/api/settings/intake")

// ---- project page extras (beyond the flow detail) ----
export type ProjectExtras = {
  id: number; name: string; owner_id: number
  details: Record<string, string | null>
  customer_approval: boolean
  guest_links: { customer: string | null; vendor: string | null }; guest_links_enabled: boolean; guest_links_expire: string | null
  intake_pending?: boolean   // a CRM intake waiting for a project manager (staff only)
  stage_rows: ({ id: number; name: string; sla_days: number | null } & StageGate)[]
  participants: { id: number; user_id: number; name: string; role: string; email: string | null; active: boolean; avatar_url: string | null }[]
  notes: { id: number; author: string; note: string; stage: string; created_at: string; mine: boolean; edited: boolean; stage_entry: boolean }[]
  documents: { id: number; category: string; filename: string; uploaded_by: string; uploaded_at: string; review: DocReview }[]
  doc_categories: string[]; users: { id: number; name: string }[]; roles: string[]; external_roles: string[]
  can: { manage: boolean; tasks: boolean; docs: boolean; move: boolean; note: boolean; download: boolean; create: boolean; delete_doc?: boolean; delete_project?: boolean }
}
export const projectExtras = (id: number) => getJson<ProjectExtras>(`/api/projects/${id}`)

// Post to one of Flask's form routes and read its flashes back as JSON. The
// route is unchanged (same permission, audit row and validation); only the
// answer differs because we ask for JSON.
export type FormReply = { ok: true; messages: string[]; undo: string | null; location: string | null; token?: string }
// `keepalive`: a save sent as the page goes (the header's theme), which must outlive it
export async function postForm(path: string, fields: Record<string, string> | FormData = {}, keepalive = false): Promise<FormReply> {
  const body = fields instanceof FormData ? fields : new URLSearchParams(fields)
  const res = await withToken(path, { method: "POST", body, headers: { Accept: "application/json" }, keepalive })
  if (!res.ok) {
    // a refused form answers 400 {ok: false, error, messages}: its own words
    const d = (await res.json().catch(() => null)) as { error?: string; messages?: string[] } | null
    // the server's words first: a 403 may be "set up two-step sign-in", not a rollout right (review P3-30)
    throw await failure(res, d?.messages?.join(" ") || d?.error || (res.status === 403 ? "You cannot do that on this rollout" : undefined))
  }
  const data = notJson(res) ? null : (await res.json().catch(() => null)) as (FormReply | { ok: false; error?: string; messages?: string[] }) | null
  if (!data) throw new ApiError(401, SIGNED_OUT)
  if (data.ok === false) throw new ApiError(400, data.messages?.join(" ") || data.error || "That did not save")
  return data
}

// ---- settings ----
export type Policy = {
  key: string; area: "general" | "security" | "people" | "workflow" | "notifications" | "integrations" | "intake" | "ai" | "ai_schedule" | "backups" | "reports" | "audit"
  kind: "int" | "bool" | "choice" | "multi" | "text" | "url" | "domains" | "emails" | "time" | "dates"
  label: string; help: string; value: number | boolean | string | string[]; min?: number; max?: number; choices?: string[]; multiline?: boolean
  group: string; hint?: string  // the card it sits on; the one plain line shown under it (help then sits behind "What is this?")
  secret?: boolean; saved?: boolean  // write-only (value always ""): whether one is saved; blank keeps it
}
export type BackupRun = {
  id: number; started_at: string; finished_at: string | null; trigger: string; actor: string | null; file: string | null
  size_bytes: number | null; ok: boolean; restore_ok: boolean | null; restore_detail: string | null; destinations: string | null
}
export type BackupsView = { runs: BackupRun[]; scheduler_seen: string | null; scheduler_alive: boolean; next_run: string | null }
export type SettingsData = {
  templates: { id: number; name: string; projects: number; stages: ({ id: number; name: string; sla_days: number | null } & StageGate)[] }[]
  doc_categories: { id: number; name: string; partners: boolean }[]
  alerts: { key: string; title: string; severity: "critical" | "warning" | "info"; threshold_days: number | null; notify_email: boolean; notify_teams: boolean; notify_inapp: boolean }[]
  m365: {
    oauth_client_configured: boolean; azure_app: { client_id: string | null; tenant_id: string | null; has_secret: boolean; source: string | null }
    connected: boolean; connected_email: string | null; team_name: string | null; channel_name: string | null; channel_id: string | null
    teams: { id: string; name: string }[]; channels: { id: string; name: string }[]; team_id: string; teams_error: string | null
  }
  backups: BackupsView | null
  api_tokens: { id: number; name: string; created_by: string; created_at: string; expires_at: string; last_used_at: string | null; revoked_at: string | null; scope: string }[]
  audit_archives: { name: string; size: number }[]
  public_url_set: boolean
  policies: Policy[]
  sso: { client_id: string | null; tenant_id: string | null; has_secret: boolean; configured: boolean; enforced: boolean; redirect_uri: string; password_admins: number }
}
// Settings → AI (routes/ai.py): the server's state, each feature's latest
// validation and the last validation runs.
export type AIState = "off" | "unknown" | "up" | "down"
export type AIFeatureView = {
  key: string; label: string; description: string; runs: string; on: boolean; forced: boolean
  state: "passed" | "slow" | "failed" | "pending"; current: boolean; checked_at: string | null; model: string | null
  seconds: number | null; detail: string | null; output: unknown; prompt: string; prompt_hash: string
}
export type AIView = {
  status: { state: AIState; since?: string; checked_at?: string; misses?: number; fingerprint?: string; model?: string; error?: string | null; seconds?: number | null; stale?: boolean }
  has_key: boolean; scheduler_alive: boolean
  usage: { calls: number; failed: number | null; avg_s: number | null; max_s: number | null; tokens_in: number | null; tokens_out: number | null }
  features: AIFeatureView[]
  jobs: { id: number; status: "queued" | "running" | "done" | "failed"; requested_by: string | null; created_at: string; started_at: string | null; finished_at: string | null
    result: { ok: boolean; reason?: string; model?: string; seconds?: number; features?: Record<string, string> } | null; error: string | null; payload: { reason?: string } | null }[]
  run_checks: { kind: "connect" | "smoke"; state: string; seconds: number | null; detail: string | null; model: string | null; created_at: string }[]
}
export type AICheck = { ok: boolean; reason?: string | null; model?: string; fingerprint?: string; models?: string[] }
export const aiSettings = () => getJson<AIView>("/api/settings/ai")
export const settingsData = (section: string, teamId = "") =>
  getJson<SettingsData>(`/api/settings?section=${encodeURIComponent(section)}${teamId ? `&team_id=${encodeURIComponent(teamId)}` : ""}`)

// locked: always on for that role; forbidden: never allowed for it (e.g. External), both shown and not editable
export type RbacData = { roles: string[]; permissions: string[]; matrix: Record<string, Record<string, boolean>>; locked: Record<string, string[]>; forbidden?: Record<string, string[]> }
export const rbac = () => getJson<RbacData>("/api/settings/rbac")
// `used` = the live projects that name the entry; a product may name its vendor (null = any vendor)
export type ProjectRef = { id: number; name: string }
export type ContactItem = { id: number; name: string; email: string | null; used: ProjectRef[]; vendor_id?: number | null }
export type ContactsData = {
  lists: { key: string; label: string; has_email: boolean; items: ContactItem[] }[]
  partners: { id: number; name: string; used: ProjectRef[]; managers: ContactItem[] }[]
}
export const contacts = () => getJson<ContactsData>("/api/settings/contacts")

// ---- admin: users and the audit log ----
export type AdminUser = {
  id: number; username: string; name: string; email: string | null; role: string; active: boolean; kind: "internal" | "external"
  last_login_at: string | null; created_at: string | null; avatar_url: string | null; pending: boolean; password_login: boolean; two_step: boolean; microsoft: boolean
  signup_label?: string | null; signup_project?: string | null; signup_project_role?: string | null; declined_reason?: string | null
  capacity_hours: number | null   // hours a week; null takes the workspace default
  holds: { tasks: number; rollouts: number; raid: number }   // the open work a hand-over on leave would move
  review: string[]   // why the access review flags this account (services/access_review.py); empty when it does not
}
export type UsersData = { users: AdminUser[]; roles: string[]; me: number; microsoft_only: boolean; capacity_default: number; review_days: number }
export const users = () => getJson<UsersData>("/api/users")
export type AuditRow = { id: number; timestamp: string; username: string; user_name?: string | null; action: string; resource_type: string | null; resource_id: number | null; resource_name: string | null; details: string | null; ip_address: string | null }
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
  milestones?: { total: number; done: number; missed: number; next: { name: string; date: string } | null }
}
export type ReportAllData = {
  audience: "internal" | "customer"; generated_at: string; today: string; company: string; template?: DocConfig
  summary: { count: number; health: Partial<Record<Rag, number>>; late_vs_target: number; behind_baseline: number | null; avg_slip: number | null; blockers: number; finishing_30d: number; no_plan: number
    csat?: number | null; csat_count?: number }   // the customers' ratings at sign-off: internal only
  rows: PortfolioRow[]
  risks: { project_id: number; project: string; kind: RaidKind; title: string; impact: string; status: string; owner_name: string | null; due_date: string | null }[]
}
export const reportAll = (template?: number | null) => getJson<ReportAllData>(`/api/reports/all${template ? `?template=${template}` : ""}`)

// ---- account, my work, alerts, analytics ----
// how a person takes a kind of notification by email and Teams (Account page)
export type Delivery = "instant" | "summary" | "off"
// the personal calendar feed (routes/feeds.py): the address is shown once, when made or rotated
export const makeCalendarFeed = () => post<{ ok: true; url: string }>("/account/calendar")
export const calendarFeedOff = () => post<{ ok: true }>("/account/calendar/off")
// what's new in this release (services/whats_new.py), once per person
export type WhatsNew = { show: boolean; version: string; title: string; items: string[] }
export const whatsNew = () => getJson<WhatsNew>("/api/whats-new")
export const whatsNewSeen = () => post<{ ok: true }>("/api/whats-new/seen")
export const account = () => getJson<{ username: string; name: string; email: string | null; kind: "internal" | "external"; must_change_password: boolean; has_password: boolean; theme: "system" | "light" | "dark"; accent: string; avatar_url: string | null
  email_kinds: { key: string; label: string; on: boolean; mode: Delivery }[]; mail_enabled: boolean; calendar: { created_at: string | null; last_read_at: string | null; idle_days: number } | null; home: "dashboard" | "board"; activity: Activity | null; activity_viewers: string[] }>("/api/account")
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
export const joinSubmit = (token: string, b: { name: string; username: string; email: string; password: string }) =>
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
  const res = await withToken(path, { method: "POST", body, headers: json ? { "Content-Type": "application/json" } : {} })
  if (!res.ok) { const d = (await res.json().catch(() => ({}))) as { error?: string }; throw await failure(res, d.error) }
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
export type WorkTask = { blocked_by?: TaskWait[]; can_edit?: boolean; id: number; project_id: number; title: string; due_date: string | null; stage: string; done: number; done_at: string | null; project: string; client: string; project_stage: string }
export type WorkProject = { id: number; name: string; client: string; stage: string; state: FlowState; stage_index: number; stages: string[]; target_end_date: string | null; role: string; owner_name: string
  days_in_stage?: number | null; over_by?: number | null }
export type MyWorkData = {
  today: string; tasks: WorkTask[]; done_by_day: { day: string; count: number }[]; projects: (WorkProject & { can_add_task: boolean })[]
  counts: { open: number; overdue: number; due_week: number; done_week: number; rollouts: number; stuck: number }
}
export const myWork = () => getJson<MyWorkData>("/api/my-work")

// ---- people ----
export type PersonCard = { id: number; name: string; role: string; avatar_url: string | null; last_login_at: string | null; last_seen_at: string | null; projects: number; open: number; late: number; done_30d: number
  csat?: number | null; csat_count?: number }   // the customers' rating of the rollouts they managed
export type PeopleData = { people: PersonCard[]; can_notify: boolean; me: number }
export type PersonData = {
  user: { id: number; name: string; role: string; email: string | null; avatar_url: string | null; last_login_at: string | null; since: string }
  today: string; can_notify: boolean; activity?: Activity
  kpis: { rollouts: number; stuck: number; open: number; late: number; done_30d: number; on_time_pct: number | null; csat?: number | null; csat_count?: number }
  projects: WorkProject[]; pending: WorkTask[]; upcoming: WorkTask[]
  contribution: { weeks: { week: string; done: number }[]; notes_30d: number; moves_30d: number }
  recent: { kind: "move" | "note" | "task"; at: string; project_id: number; project: string; text: string }[]
}
export const people = () => getJson<PeopleData>("/api/people")
export const person = (id: number) => getJson<PersonData>(`/api/people/${id}`)
export const notifyPerson = (id: number, message: string, project_id?: number | null) => post<{ ok: true }>(`/api/people/${id}/notify`, { message, project_id: project_id ?? null })
// workload (services/workload.py): hours per person per week against capacity
export type WorkloadCell = { week: string; tasks: number; task_hours: number; pm_hours: number; hours: number; pct: number; level: "ok" | "warn" | "over" }
export type WorkloadPerson = { id: number; name: string; role: string; avatar_url: string | null; capacity: number; custom_capacity: boolean; rollouts: number; weeks: WorkloadCell[]; peak: number }
export type WorkloadData = { today: string; weeks: string[]; capacity_default: number; warn_pct: number; over: number; heavy: number; people: WorkloadPerson[] }
export const workload = () => getJson<WorkloadData>("/api/workload")
// each person's hours in the week holding `date`: the assignee picker's "34 h that week"
export type WorkloadWeek = { week: string; people: Record<string, { hours: number; capacity: number; level: WorkloadCell["level"] }> }
export const workloadWeek = (date: string) => getJson<WorkloadWeek>(`/api/workload/week?date=${date}`)
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

export type SearchMention = { kind: "note" | "risk" | "scope" | "document"; project_id: number; project_name: string; snippet: string; href: string }
export type SearchResults = { projects: { id: number; name: string; client: string; stage: string }[]; tasks: { id: number; title: string; done: boolean; project_id: number; project_name: string }[]; mentions?: SearchMention[] }
export const search = (q: string) => getJson<SearchResults>(`/api/search?q=${encodeURIComponent(q)}`)

// ---- notifications ----
export type Notification = { id: number; kind: string; title: string; body: string | null; link: string | null; actor: string | null; project_name: string | null; created_at: string; read: boolean; muted?: boolean }
export const notifications = () => getJson<{ unread: number; rows: Notification[] }>("/api/notifications")
export const markRead = (which: { id: number } | { all: true }) => post<{ ok: true; unread: number }>("/api/notifications/read", which)

// ---- the new / duplicate / edit project form ----
export type ProjectFormData = {
  mode: "new" | "duplicate" | "edit"; id: number | null; me: number
  // who may manage a project (they can move stages); can_lead: whether you can yourself
  leads: { id: number; name: string }[]; can_lead: boolean
  project: Partial<Record<string, string | null>> & { customer_approval?: boolean; stage_template_id?: number | null; owner_id?: number }
  defaults: { stage_template_id: number | null; customer_approval: boolean }
  via_options: string[]; delivery_modes: string[]
  account_managers: { name: string; email: string | null }[]
  partners: { id: number; name: string; managers: { name: string; email: string }[] }[]
  vendors: string[]; products: { name: string; vendor: string }[]; outsourcers: { name: string; email: string | null }[]
  templates: { id: number; name: string }[]; users: { id: number; name: string }[]
  custom_fields: ProjectField[]
}
export const projectForm = (query: string) => getJson<ProjectFormData>(`/api/project-form${query ? `?${query}` : ""}`)

// ---- tasks: the same Flask routes the project page posts as forms ----
// blocks (add only): the tasks that wait on the new one, as the undo of a delete gives them back
export type TaskLinks = { waits_on?: number[]; blocks?: number[]; estimate_hours?: number | null; recurrence?: Recurrence | null; recur_until?: string | null }
export const addTask = (projectId: number, task: { title: string; stage: string; assignee_id?: number | null; due_date?: string | null; done?: boolean; done_at?: string | null } & TaskLinks & TaskAsk) =>
  post<{ ok: true; id: number }>(`/projects/${projectId}/tasks`, task)
// done: the state wanted, never a blind flip (a tick from a stale tab must not reopen the task)
export const toggleTask = (projectId: number, taskId: number, done: boolean) => post<{ ok: true; done: boolean }>(`/projects/${projectId}/tasks/${taskId}/toggle`, { done })
// a task corrected in place: the route takes the whole task (title, assignee, due date)
export const editTask = (projectId: number, taskId: number, task: { title: string; assignee_id: number | null; due_date: string | null } & TaskLinks & TaskAsk) =>
  post<{ ok: true }>(`/projects/${projectId}/tasks/${taskId}/edit`, task)
// only the due date changes (the calendar's drag): whoever manages the rollout's tasks
export const moveTaskDue = (projectId: number, taskId: number, due_date: string) => post<{ ok: true }>(`/projects/${projectId}/tasks/${taskId}/edit`, { due_date })
export const deleteTask = (projectId: number, taskId: number) => post<{ ok: true }>(`/projects/${projectId}/tasks/${taskId}/delete`, {})
// the tasks a template's stages bring to a new rollout (Settings): links name another row's key
export type TemplateTask = { id: number; stage_id: number; title: string; role: string | null; offset_days: number; waits_on_id: number | null; estimate_hours: number | null }
export type TemplateTaskInput = { key: string; stage_id: number; title: string; role: string | null; offset_days: number; waits_on: string | null; estimate_hours: number | null }
export const templateTasks = (templateId: number) => getJson<{ tasks: TemplateTask[]; roles: string[] }>(`/api/settings/templates/${templateId}/tasks`)
export const saveTemplateTasks = (templateId: number, tasks: TemplateTaskInput[]) => send<{ tasks: TemplateTask[]; roles: string[] }>(`/api/settings/templates/${templateId}/tasks`, "PUT", { tasks })
