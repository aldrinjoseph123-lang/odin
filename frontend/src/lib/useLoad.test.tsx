import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ApiError } from "./api"
import { useLoad } from "./useLoad"
import { readPref, setPrefUser, usePref } from "./usePref"
import { cycleTheme, syncAppearance, useAppearance } from "./theme"
import { currentToasts } from "./toast"

const later = <T,>() => { let done!: (v: T) => void, fail!: (e: unknown) => void; const p = new Promise<T>((a, b) => { done = a; fail = b }); return { p, done, fail } }

describe("useLoad (review P2-29)", () => {
  it("drops an answer that lands after a newer question", async () => {
    const first = later<string>(), second = later<string>()
    const { result, rerender } = renderHook(({ k }) => useLoad(k, () => (k === "a" ? first.p : second.p)), { initialProps: { k: "a" } })
    rerender({ k: "b" })
    await act(async () => { second.done("B"); await second.p })
    await act(async () => { first.done("A"); await first.p })
    expect(result.current.data).toBe("B")
  })

  it("keeps the page on a failed refresh, says so once, and clears it on success", async () => {
    let n = 0
    const fn = vi.fn(async () => { n++; if (n === 2 || n === 3) throw new ApiError(502, "gone"); return n })
    const { result } = renderHook(() => useLoad("x", fn))
    await waitFor(() => expect(result.current.data).toBe(1))
    const toasts = currentToasts().length
    await act(() => result.current.reload())
    await act(() => result.current.reload())
    expect(result.current).toMatchObject({ data: 1, error: null, stale: true })
    expect(currentToasts().length).toBe(toasts + 1)
    await act(() => result.current.reload())
    expect(result.current).toMatchObject({ data: 4, error: null, stale: false })
  })

  it("a failed first load is the error; a new key never shows the last key's record", async () => {
    const { result, rerender } = renderHook(({ k }) => useLoad(k, async () => { if (k === "bad") throw new ApiError(404, "Not here"); return k }), { initialProps: { k: "one" } })
    await waitFor(() => expect(result.current.data).toBe("one"))
    rerender({ k: "bad" })
    expect(result.current.data).toBeNull()
    await waitFor(() => expect(result.current.error?.status).toBe(404))
    rerender({ k: "two" })
    expect(result.current.error).toBeNull()   // errors do not stick
    await waitFor(() => expect(result.current.data).toBe("two"))
  })

  it("with keep, a filter change shows the old rows until the new ones arrive", async () => {
    const next = later<string>()
    const { result, rerender } = renderHook(({ k }) => useLoad(k, () => (k === "a" ? Promise.resolve("A") : next.p), { keep: true }), { initialProps: { k: "a" } })
    await waitFor(() => expect(result.current.data).toBe("A"))
    rerender({ k: "b" })
    expect(result.current.data).toBe("A")
    await act(async () => { next.done("B"); await next.p })
    expect(result.current.data).toBe("B")
  })
})

describe("usePref (advice B1)", () => {
  it("remembers a choice per person", () => {
    setPrefUser(7)
    const { result } = renderHook(() => usePref<number | null>("mywork.project", null))
    act(() => result.current[1](42))
    expect(readPref("mywork.project", null)).toBe(42)
    setPrefUser(8)
    expect(readPref("mywork.project", null)).toBeNull()
  })
})

describe("the theme (review P2-33)", () => {
  it("one source for the header and the Account page; clicks save once, after they stop", async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => undefined)
    syncAppearance("dark", "blue")   // the Account page saved dark
    const { result } = renderHook(() => useAppearance())
    expect(result.current.theme).toBe("dark")
    act(() => { cycleTheme(save); cycleTheme(save) })   // dark → system → light
    expect(result.current.theme).toBe("light")
    syncAppearance("dark", "blue")   // a session answer from before the save: ignored while one is waiting
    expect(result.current.theme).toBe("light")
    act(() => { vi.advanceTimersByTime(1000) })
    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith("light", "blue")
    vi.useRealTimers()
  })
})
