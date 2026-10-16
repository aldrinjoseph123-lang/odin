import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { usePoll } from "./usePoll"

describe("usePoll", () => {
  afterEach(() => { vi.useRealTimers() })
  it("stops after max asks, and recheck asks once and starts the count again", () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const { result } = renderHook(() => usePoll(true, fn, 1000, 3))
    expect(result.current.window).toBe(3000)
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(fn).toHaveBeenCalledTimes(3)
    act(() => { result.current.recheck() })
    expect(fn).toHaveBeenCalledTimes(4)
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(fn).toHaveBeenCalledTimes(7)
  })
})
