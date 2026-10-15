import { afterEach, describe, expect, it, vi } from "vitest"
import { copyText } from "./copy"

describe("copyText", () => {
  afterEach(() => { vi.unstubAllGlobals() })
  it("uses the clipboard when it answers", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText } })
    expect(await copyText("abc")).toBe(true)
    expect(writeText).toHaveBeenCalledWith("abc")
  })
  it("falls back to a selected text area when there is no clipboard, and says false when that fails too", async () => {
    vi.stubGlobal("navigator", {})
    const exec = vi.fn().mockReturnValue(true)
    vi.stubGlobal("document", { createElement: () => ({ setAttribute() {}, style: {}, select() {}, remove() {} }), body: { append() {} }, execCommand: exec })
    expect(await copyText("abc")).toBe(true)
    exec.mockReturnValue(false)
    expect(await copyText("abc")).toBe(false)
  })
})
