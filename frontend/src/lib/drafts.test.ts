// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import { installDrafts, restoreDrafts, stashDrafts } from "./drafts"

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

describe("drafts", () => {
  beforeEach(() => { sessionStorage.clear(); document.body.innerHTML = "" })

  it("stashes typed words on a sign-out and gives them back to the same fields, through an input event", () => {
    document.body.innerHTML = `<form><textarea name="note">half a note</textarea><input type="text" id="title" value="Site B"><input aria-label="Add a note" value="untyped input"><input type="password" value="secret"><input type="text" name="empty" value=""></form>`
    stashDrafts()
    const kept = JSON.parse(sessionStorage.getItem("odin.drafts")!)
    expect(kept.values).toEqual({ note: "half a note", title: "Site B", "Add a note": "untyped input" })   // never the password, never an empty field

    document.body.innerHTML = `<form><textarea name="note"></textarea><input type="text" id="title"><input aria-label="Add a note"></form>`
    const seen: string[] = []
    document.addEventListener("input", (e) => seen.push((e.target as HTMLTextAreaElement).value))
    expect(restoreDrafts()).toBe(true)
    expect((document.querySelector("textarea") as HTMLTextAreaElement).value).toBe("half a note")
    expect(seen).toEqual(["half a note", "Site B", "untyped input"])
    expect(sessionStorage.getItem("odin.drafts")).toBeNull()   // used up
  })

  it("keeps the stash for fields that have not rendered yet and across the sign-in page, and drops it after an hour", () => {
    document.body.innerHTML = `<textarea name="a">A</textarea><textarea name="b">B</textarea>`
    stashDrafts()
    document.body.innerHTML = `<textarea name="a"></textarea>`
    expect(restoreDrafts()).toBe(false)
    expect(JSON.parse(sessionStorage.getItem("odin.drafts")!).values).toEqual({ b: "B" })
    const here = location.pathname
    history.pushState({}, "", "/login")   // the way back passes through the sign-in page
    document.body.innerHTML = `<textarea name="b"></textarea>`
    expect(restoreDrafts()).toBe(true)
    expect((document.querySelector("textarea") as HTMLTextAreaElement).value).toBe("")   // not this page's words
    expect(JSON.parse(sessionStorage.getItem("odin.drafts")!).values).toEqual({ b: "B" })
    history.pushState({}, "", here)

    const old = JSON.parse(sessionStorage.getItem("odin.drafts")!)
    sessionStorage.setItem("odin.drafts", JSON.stringify({ ...old, at: Date.now() - 2 * 60 * 60 * 1000 }))
    document.body.innerHTML = `<textarea name="b"></textarea>`
    expect(restoreDrafts()).toBe(true)
    expect((document.querySelector("textarea") as HTMLTextAreaElement).value).toBe("")
    expect(sessionStorage.getItem("odin.drafts")).toBeNull()
  })

  it("installDrafts waits for the field to appear", async () => {
    sessionStorage.setItem("odin.drafts", JSON.stringify({ at: Date.now(), path: location.pathname, values: { note: "later" } }))
    installDrafts()
    document.body.innerHTML = `<textarea name="note"></textarea>`
    await new Promise((r) => setTimeout(r, 0))   // the observer runs as a microtask
    expect((document.querySelector("textarea") as HTMLTextAreaElement).value).toBe("later")
  })
})
