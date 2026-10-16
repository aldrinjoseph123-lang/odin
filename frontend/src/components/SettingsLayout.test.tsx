// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { SettingsLayout } from "./SettingsLayout"
import { admin } from "@/pages/fixtures"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  settingsData: vi.fn(async () => ({ policies: [{ key: "undo_minutes", area: "security", label: "Undo window (minutes)", group: "Sessions" }] })),
}))
const Where = () => <p data-testid="where">{useLocation().pathname + useLocation().hash}</p>
const mount = () => render(<MemoryRouter initialEntries={["/settings/general"]}><SettingsLayout user={admin}><Where /></SettingsLayout></MemoryRouter>)

describe("the Settings menu filter (B14)", () => {
  it("narrows the menu to matching areas and settings, and Enter jumps to the first", async () => {
    const user = userEvent.setup()
    mount()
    expect(screen.getByRole("link", { name: "Backups" })).toBeInTheDocument()
    await user.click(screen.getByLabelText("Filter settings"))
    await user.keyboard("undo")
    expect(await screen.findByRole("link", { name: /Undo window/ })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Backups" })).toBeNull()
    await user.keyboard("{Enter}")
    expect(screen.getByTestId("where")).toHaveTextContent("/settings/security#pol-undo_minutes")
    expect(screen.getByRole("link", { name: "Backups" })).toBeInTheDocument()   // the filter clears after a jump
  })
  it("says so when nothing matches, and Esc restores the menu", async () => {
    const user = userEvent.setup()
    mount()
    await user.type(screen.getByLabelText("Filter settings"), "zzzz")
    expect(screen.getByText(/No setting matches/)).toBeInTheDocument()
    await user.keyboard("{Escape}")
    expect(screen.getByRole("link", { name: "Backups" })).toBeInTheDocument()
  })
  it("matches an area by its name", async () => {
    const user = userEvent.setup()
    mount()
    await user.type(screen.getByLabelText("Filter settings"), "backup")
    expect(screen.getByRole("link", { name: "Backups" })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Reports" })).toBeNull()
  })
})
