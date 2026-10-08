import { afterEach, describe, expect, it, vi } from "vitest"
import { currentToasts, dismissToast, toast } from "./toast"

describe("toast", () => {
  afterEach(() => { currentToasts().forEach((t) => dismissToast(t.id)); vi.useRealTimers() })
  it("keeps the newest three and leaves on its own", () => {
    vi.useFakeTimers()
    ;["a", "b", "c", "d"].forEach((x) => toast(x))
    expect(currentToasts().map((t) => t.text)).toEqual(["b", "c", "d"])
    vi.advanceTimersByTime(4000)
    expect(currentToasts()).toEqual([])
  })
  it("stays longer when it carries an action, and defaults to ok", () => {
    vi.useFakeTimers()
    toast("Moved", { action: { label: "Undo", run: () => {} } })
    vi.advanceTimersByTime(4000)
    expect(currentToasts()).toHaveLength(1)
    expect(currentToasts()[0].tone).toBe("ok")
    vi.advanceTimersByTime(4000)
    expect(currentToasts()).toEqual([])
  })
})
