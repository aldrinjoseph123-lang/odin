// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { CommandPalette } from "./CommandPalette"
import { admin } from "@/pages/fixtures"
import type { User } from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  search: vi.fn(async () => ({ projects: [], tasks: [], mentions: [] })),
  people: vi.fn(async () => ({ people: [{ id: 5, name: "Priya Nair", role: "Member" }, { id: 6, name: "Omar Said", role: "Viewer" }], can_notify: true, me: 1 })),
  settingsData: vi.fn(async () => ({ policies: [{ key: "undo_minutes", area: "security", label: "Undo window (minutes)", group: "Sessions" }] })),
}))
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", "") }
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open") }

const pages = [{ label: "Flow", href: "/board" }, { label: "Account", href: "/account" }]
const Where = () => <p data-testid="where">{useLocation().pathname + useLocation().hash}</p>
const mount = (user: User, extra: Partial<React.ComponentProps<typeof CommandPalette>> = {}) =>
  render(<MemoryRouter><CommandPalette user={user} pages={pages} open onClose={() => {}} {...extra} /><Where /></MemoryRouter>)
const partner = { ...admin, kind: "external", role: "External", permissions: ["view_projects"] } as User

beforeEach(() => localStorage.clear())

describe("the palette (B7)", () => {
  it("offers recent rollouts, actions and pages when the box is empty", async () => {
    localStorage.setItem("odin.pref.0.recent.rollouts", JSON.stringify([{ id: 9, name: "Globex EDR" }]))
    mount(admin, { onShortcuts: () => {} })
    expect(await screen.findByRole("option", { name: /Globex EDR/ })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /New rollout/ })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /Keyboard shortcuts/ })).toBeInTheDocument()
    expect(screen.getByRole("option", { name: /Account/ })).toBeInTheDocument()
    expect(screen.getByText("Recent rollouts")).toBeInTheDocument()
  })
  it("finds a policy by its label and lands on its row", async () => {
    const user = userEvent.setup()
    mount(admin)
    await user.type(screen.getByRole("combobox"), "undo window")
    const hit = await screen.findByRole("option", { name: /Undo window/ })
    expect(hit).toHaveTextContent("Sign-in & security")
    await user.keyboard("{Enter}")
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/security#pol-undo_minutes")
  })
  it("finds a colleague for staff", async () => {
    const user = userEvent.setup()
    mount(admin)
    await user.type(screen.getByRole("combobox"), "priya")
    await waitFor(() => expect(screen.getByRole("option", { name: /Priya Nair/ })).toBeInTheDocument())
    expect(screen.queryByRole("option", { name: /Omar/ })).toBeNull()
  })
  it("shows an external partner no people, settings or staff actions", async () => {
    const user = userEvent.setup()
    mount(partner)
    expect(screen.queryByRole("option", { name: /New rollout|Notify someone/ })).toBeNull()
    await user.type(screen.getByRole("combobox"), "priya")
    expect(screen.queryByRole("option", { name: /Priya/ })).toBeNull()
    await user.clear(screen.getByRole("combobox"))
    await user.type(screen.getByRole("combobox"), "undo")
    expect(screen.queryByRole("option", { name: /Undo window/ })).toBeNull()
    expect(screen.queryByText("Settings")).toBeNull()
  })
  it("runs an action instead of navigating", async () => {
    const user = userEvent.setup(), run = vi.fn()
    mount(admin, { onShortcuts: run })
    await user.click(screen.getByRole("option", { name: /Keyboard shortcuts/ }))
    expect(run).toHaveBeenCalled()
  })
})
