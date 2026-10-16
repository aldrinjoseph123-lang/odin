import { afterEach, describe, expect, it, vi } from "vitest"
import { currentToasts, dismissToast, holdToast, releaseToast, toast } from "./toast"

describe("toast", () => {
  afterEach(() => { currentToasts().forEach((t) => dismissToast(t.id)); vi.useRealTimers() })
  it("keeps the newest three and a plain one leaves on its own", () => {
    vi.useFakeTimers()
    ;["a", "b", "c", "d"].forEach((x) => toast(x))
    expect(currentToasts().map((t) => t.text)).toEqual(["b", "c", "d"])
    vi.advanceTimersByTime(4000)
    expect(currentToasts()).toEqual([])
  })
  it("stays until used or dismissed when it carries an action or an error", () => {
    vi.useFakeTimers()
    toast("Moved", { action: { label: "Undo", run: () => {} } })
    toast("Could not save", { tone: "bad" })
    vi.advanceTimersByTime(600_000)
    expect(currentToasts().map((t) => t.tone)).toEqual(["ok", "bad"])
    currentToasts().forEach((t) => dismissToast(t.id))
    expect(currentToasts()).toEqual([])
  })
  it("waits while it is held, then gets at least two seconds", () => {
    vi.useFakeTimers()
    const id = toast("Saved")
    vi.advanceTimersByTime(3500)
    holdToast(id)
    vi.advanceTimersByTime(60_000)
    expect(currentToasts()).toHaveLength(1)
    releaseToast(id)
    vi.advanceTimersByTime(1900)
    expect(currentToasts()).toHaveLength(1)
    vi.advanceTimersByTime(200)
    expect(currentToasts()).toEqual([])
  })
})
