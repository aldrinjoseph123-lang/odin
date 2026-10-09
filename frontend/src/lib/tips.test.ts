// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import { tipText } from "./tips"

describe("tipText", () => {
  it("moves a title into data-tip once, naming an otherwise unnamed element", () => {
    document.body.innerHTML = `<button title="Delete Sensor pilot"><svg></svg></button><span title="A very long project name">A very long…</span>`
    const [btn, span] = [document.querySelector("button")!, document.querySelector("span")!]
    expect(tipText(btn)).toBe("Delete Sensor pilot")
    expect(btn.hasAttribute("title")).toBe(false)
    expect(btn.getAttribute("aria-label")).toBe("Delete Sensor pilot")
    expect(tipText(btn)).toBe("Delete Sensor pilot")                 // second hover reads data-tip
    expect(tipText(span)).toBe("A very long project name")
    expect(span.hasAttribute("aria-label")).toBe(false)               // it has visible text
  })
  it("shows an icon-only control's aria-label, and nothing for a labelled text button", () => {
    document.body.innerHTML = `<button aria-label="Notifications"><svg></svg><span>27</span></button><button aria-label="Manage Omar">Manage</button>`
    const [icon, text] = document.querySelectorAll("button")
    expect(tipText(icon as HTMLElement)).toBe("Notifications")                // an icon with a count
    expect(tipText(text as HTMLElement)).toBeNull()
  })
})
