// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import AppShell from "./AppShell"
import { admin } from "@/pages/fixtures"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  notifications: vi.fn(async () => ({ items: [], unread: 0 })),
  search: vi.fn(async () => ({ projects: [], tasks: [], mentions: [] })),
  people: vi.fn(async () => ({ people: [], can_notify: true, me: 1 })),
  settingsData: vi.fn(async () => ({ policies: [] })),
}))
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", "") }
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open") }

const mount = () => {
  render(<MemoryRouter><AppShell user={admin}><input aria-label="Any field" /></AppShell></MemoryRouter>)
  ;(document.activeElement as HTMLElement | null)?.blur()   // jsdom autofocuses the closed palette's input; a browser does not
}

describe("the ? shortcut sheet (B6)", () => {
  it("opens on ? and lists the shortcuts", async () => {
    const user = userEvent.setup()
    mount()
    await user.keyboard("?")
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument()
    expect(screen.getByText("List, Kanban, Gantt, Calendar")).toBeInTheDocument()
  })
  it("stays shut while typing in a field", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(screen.getByLabelText("Any field"))
    await user.keyboard("?")
    expect(screen.queryByRole("dialog", { name: "Keyboard shortcuts" })).toBeNull()
    expect(screen.getByLabelText("Any field")).toHaveValue("?")
  })
  it("is switched off with the single-key shortcuts, but the account menu still opens it", async () => {
    const user = userEvent.setup()
    localStorage.setItem("odin.pref.0.shortcut.slash", "false")
    mount()
    await user.keyboard("?")
    expect(screen.queryByRole("dialog", { name: "Keyboard shortcuts" })).toBeNull()
    await user.click(screen.getByRole("button", { name: "Your account" }))
    await user.click(await screen.findByRole("button", { name: /Keyboard shortcuts/ }))
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument()
  })
})
