// One thin client for Flask's JSON API. Same session cookie as the Jinja
// pages; every mutation carries the CSRF token from /api/session as a header.

export type User = {
  id: number
  name: string
  role: "Admin" | "Member" | "Contributor" | "Viewer"
  must_change_password: boolean
  permissions: string[]
  nav: Nav
}

type SessionResponse = { csrf: string; user: User | null }

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

export type Nav = { active_alert_count: number; my_open_task_count: number; projects_nav_url: string }

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
  return post<{ ok: true }>(`/api/projects/${projectId}/stage`, { stage, note })
}

export function dismissAlert(projectId: number, alertType: string) {
  return post<{ ok: true }>(`/api/alerts/${projectId}/dismiss/${alertType}`)
}
