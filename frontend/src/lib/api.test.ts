import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError, SIGNED_OUT, csrfRejected, failureText, markRead, postForm, session } from "./api"

describe("failureText", () => {
  it("says what went wrong and what to do, never a bare status (test report UX-6)", () => {
    expect(failureText(0)).toMatch(/connection/)
    expect(failureText(401)).toBe(SIGNED_OUT)
    expect(failureText(404)).toMatch(/^Not found/)
    expect(failureText(500)).toMatch(/Try again/)
    expect(failureText(503)).toBe(failureText(500))
    expect(failureText(418)).toMatch(/error 418\)\. Reload/)
    for (const s of [0, 400, 401, 403, 404, 413, 429, 500]) expect(failureText(s)).not.toMatch(/Request failed/)
  })
})

describe("the CSRF token and the session check", () => {
  const reply = (status: number, body: unknown) => new Response(typeof body === "string" ? body : JSON.stringify(body), { status })
  afterEach(() => { vi.unstubAllGlobals() })

  it("tells a stale-token 400 from any other 400", () => {
    expect(csrfRejected(400, { error: "CSRF token missing or invalid" })).toBe(true)
    expect(csrfRejected(400, { error: "x", csrf: "fresh" })).toBe(true)
    expect(csrfRejected(400, { error: "Task needs a title" })).toBe(false)
    expect(csrfRejected(403, { csrf: "fresh" })).toBe(false)
    expect(csrfRejected(400, null)).toBe(false)
  })

  it("takes the fresh token from a CSRF 400 and sends once more (FE7)", async () => {
    const tokens: string[] = []
    vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/session") return reply(200, { csrf: "old", user: null })
      tokens.push((init?.headers as Record<string, string>)["X-CSRF-Token"])
      return tokens.length === 1 ? reply(400, { error: "CSRF token missing or invalid", csrf: "new" }) : reply(200, { ok: true })
    }))
    await expect(markRead({ all: true })).resolves.toEqual({ ok: true })
    expect(tokens).toEqual(["old", "new"])
  })

  it("a refused form says the server's own words, not 'error 400'", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => path === "/api/session"
      ? reply(200, { csrf: "t", user: { id: 1 } })
      : reply(400, { ok: false, error: "Username already taken", messages: ["Username already taken"] })))
    await expect(postForm("/users", { username: "x" })).rejects.toThrow("Username already taken")
  })

  it("a save after the session ended is never a success (sim PM-1)", async () => {
    const page = () => new Response("<!doctype html><title>Sign in</title>", { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } })
    vi.stubGlobal("fetch", vi.fn(async (path: string) => path === "/api/session" ? reply(200, { csrf: "t", user: null }) : page()))
    await expect(markRead({ all: true })).rejects.toThrow(SIGNED_OUT)
    await expect(postForm("/projects/1/note", { note: "x" })).rejects.toThrow(SIGNED_OUT)
  })

  it("an ended session says so; any other refusal keeps the server's words (sim roles-5)", async () => {
    vi.stubGlobal("fetch", vi.fn(async (path: string) => path === "/api/session"
      ? reply(200, { csrf: "t", user: null })
      : path === "/api/notifications/read"
        ? new Response(JSON.stringify({ error: "Your session has ended", signed_out: true }), { status: 401, headers: { "X-Odin-Signed-Out": "1" } })
        : reply(401, { error: "Bad username or password" })))
    await expect(markRead({ all: true })).rejects.toThrow(SIGNED_OUT)
    const { login } = await import("./api")
    await expect(login("x", "y")).rejects.toThrow("Bad username or password")
  })

  it("a 502 page from /api/session is an ApiError, not a crash (FE3)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(502, "<html>Bad gateway</html>")))
    await expect(session()).rejects.toBeInstanceOf(ApiError)
  })
})
