import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { RECHECK, usePoll } from "./usePoll"

describe("usePoll", () => {
  afterEach(() => { vi.useRealTimers() })
  it("stops after max asks, and a RECHECK asks once and starts the count again", () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    renderHook(() => usePoll(true, fn, 1000, 3))
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(fn).toHaveBeenCalledTimes(3)
    act(() => { window.dispatchEvent(new Event(RECHECK)) })
    expect(fn).toHaveBeenCalledTimes(4)
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(fn).toHaveBeenCalledTimes(7)
  })
})
