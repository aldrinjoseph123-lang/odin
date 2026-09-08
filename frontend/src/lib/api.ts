// One thin client for Flask's JSON API. Same session cookie as the Jinja
// pages; every mutation carries the CSRF token from /api/session as a header.

export type User = {
  id: number
  name: string
  role: "Admin" | "Member" | "Contributor" | "Viewer"
  must_change_password: boolean
  permissions: string[]
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
