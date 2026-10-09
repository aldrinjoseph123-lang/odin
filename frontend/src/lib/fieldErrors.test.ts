// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import { installFieldErrors } from "./fieldErrors"

describe("installFieldErrors", () => {
  it("marks the first invalid field, explains it underneath, and clears once fixed", () => {
    installFieldErrors(document)
    document.body.innerHTML = `<form><input id="a" required><input id="b" required></form>`
    const form = document.querySelector("form")!, a = document.getElementById("a") as HTMLInputElement, b = document.getElementById("b") as HTMLInputElement
    form.checkValidity()
    const note = document.getElementById("field-error")!
    expect(note.getAttribute("role")).toBe("alert")
    expect(note.textContent).toBe(a.validationMessage)
    expect(a.getAttribute("aria-invalid")).toBe("true")
    expect(a.getAttribute("aria-errormessage")).toBe("field-error")
    expect(b.hasAttribute("aria-invalid")).toBe(false)              // one note per submit
    a.value = "x"; a.dispatchEvent(new Event("input", { bubbles: true }))
    expect(document.getElementById("field-error")).toBeNull()
    expect(a.hasAttribute("aria-invalid")).toBe(false)
  })
})
