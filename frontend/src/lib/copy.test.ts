import { afterEach, describe, expect, it, vi } from "vitest"
import { copyText, copyWithToast } from "./copy"

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

describe("copyWithToast", () => {
  afterEach(() => { vi.unstubAllGlobals() })
  it("says how it went, in one wording", async () => {
    const { currentToasts } = await import("./toast")
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
    expect(await copyWithToast("abc", "link")).toBe(true)
    expect(currentToasts().at(-1)).toMatchObject({ text: "Copied the link", tone: "ok" })
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("no")) } })
    vi.stubGlobal("document", { createElement: () => ({ setAttribute() {}, style: {}, select() {}, remove() {} }), body: { append() {} }, execCommand: () => false })
    expect(await copyWithToast("abc", "link")).toBe(false)
    expect(currentToasts().at(-1)).toMatchObject({ text: "Select the link and copy it", tone: "bad" })
  })
})
