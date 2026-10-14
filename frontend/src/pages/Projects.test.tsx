// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Projects from "./Projects"
import { admin, projects } from "./fixtures"

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), projects: vi.fn(async () => projects) }))

describe("Projects", () => {
  it("switches between the table and cards, and remembers it", async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Projects user={admin} /></MemoryRouter>)
    expect(await screen.findByRole("table")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Cards" }))
    expect(screen.getByRole("list", { name: "Rollouts" })).toBeInTheDocument()
    expect(screen.getByText("1 of 2 tasks done")).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "Sort by" })).toBeInTheDocument()   // cards have no column heads
    expect(localStorage.getItem("odin.projects.layout")).toBe("cards")
    await user.click(screen.getByRole("button", { name: "Table" }))
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.queryByRole("combobox", { name: "Sort by" })).toBeNull()
  })
})
