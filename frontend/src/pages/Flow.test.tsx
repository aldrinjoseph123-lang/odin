// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Flow from "./Flow"
import { admin, flow } from "./fixtures"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  flow: vi.fn(async () => flow),
  flowDetail: vi.fn(async () => { throw new Error("not in this test") }),
}))

const mount = (url = "/board") => render(<MemoryRouter initialEntries={[url]}><Flow user={admin} /></MemoryRouter>)
const rows = () => screen.getAllByRole("button", { name: /, (Globex|Initech)\./ })

describe("Flow list", () => {
  it("lists the stuck rows and folds the on-track ones", async () => {
    mount()
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Active rollouts")
    expect(rows().map((r) => r.getAttribute("aria-label")?.split(",")[0])).toEqual(["Late one", "Stuck one"])
    expect(screen.getByRole("button", { name: "Show 2 on-track rollouts" })).toBeInTheDocument()
    expect(screen.getAllByText("Next:").length).toBeGreaterThan(0)               // the next-task line
  })

  it("filters, stage pills and grouping read from and write to the URL", async () => {
    const user = userEvent.setup()
    mount("/board?filter=customer")
    expect((await screen.findAllByRole("button", { name: /, (Globex|Initech)\./ })).map((r) => r.getAttribute("aria-label")?.split(",")[0])).toEqual(["Other fine"])
    await user.click(screen.getByRole("button", { name: /^All, 4/ }))
    await user.click(screen.getByRole("button", { name: "Show 2 on-track rollouts" }))
    expect(rows()).toHaveLength(4)
    await user.click(screen.getByRole("button", { name: /^Deployment: 1\./ }))
    expect(rows()).toHaveLength(1)
    await user.click(screen.getByRole("button", { name: /^Deployment: 1\./ }))
    await user.selectOptions(screen.getByRole("combobox", { name: "Group rollouts by" }), "client")
    const headers = [...document.querySelectorAll("ul[aria-label] > li > p")].map((p) => p.textContent)
    expect(headers.some((h) => h?.startsWith("Globex"))).toBe(true)
    expect(headers.some((h) => h?.startsWith("Initech"))).toBe(true)
  })

  it("the views switch is in the URL; the Kibana view is kept from partners", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("radio", { name: "Calendar" }))
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Calendar")
    cleanup()
    const partner = { ...admin, kind: "external" as const, permissions: ["view_board"] }
    render(<MemoryRouter initialEntries={["/board?view=kibana"]}><Flow user={partner} /></MemoryRouter>)
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Active rollouts")
    expect(screen.queryByRole("radio", { name: "Kibana" })).toBeNull()
  })
})
