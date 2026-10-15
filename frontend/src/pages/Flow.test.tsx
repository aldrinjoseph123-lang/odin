// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Flow from "./Flow"
import { admin, flow } from "./fixtures"
import * as api from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  flow: vi.fn(async () => flow),
  flowDetail: vi.fn(async () => { throw new Error("not in this test") }),
  flowPlan: vi.fn(async () => gantt),
}))

// two rollouts on the plan: one open into its stages, one a single bar
const gstage = (id: number, name: string, status: "done" | "current" | "next", plan: [string, string] | null, actual?: [string, string | null]) => ({
  id, name, status, sla_days: 5, plan_start: plan?.[0] ?? null, plan_end: plan?.[1] ?? null, base_start: null, base_end: null,
  actual_start: actual?.[0] ?? null, actual_end: actual?.[1] ?? null, forecast_start: plan?.[0] ?? null, forecast_end: plan?.[1] ?? null,
  suggested_start: "2026-09-01", suggested_end: "2026-09-05", slip_days: 0,
})
const gantt: api.GanttData = {
  today: "2026-09-29", calendar: null,
  rows: [1, 2, 3, 4].map((id) => ({
    id, name: flow.rows[id - 1].name, client: "Globex", stage: "Scoping", owner_name: "Admin User", start_date: "2026-09-01", target_end_date: "2026-10-20",
    forecast: "2026-10-25", pct_complete: 40, rag: "amber" as const, has_plan: true, baselined: false, can_edit: false,
    stages: [gstage(id * 10, "PO Received", "done", ["2026-09-01", "2026-09-05"], ["2026-09-01", "2026-09-04"]), gstage(id * 10 + 1, "Scoping", "current", ["2026-09-06", "2026-10-01"], ["2026-09-05", null])],
  })),
}

beforeEach(() => { localStorage.clear(); vi.mocked(api.flowPlan).mockClear() })

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

  it("the views switch is in the URL; an old Kibana link falls back to the list", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("radio", { name: "Calendar" }))
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Calendar")
    cleanup()
    const partner = { ...admin, kind: "external" as const, permissions: ["view_board"] }
    render(<MemoryRouter initialEntries={["/board?view=kibana"]}><Flow user={partner} /></MemoryRouter>)
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Active rollouts")
    expect(screen.queryByRole("radio", { name: "Kibana" })).toBeNull()   // the Kibana view was removed (13 Oct 2026)
  })

  it("Kanban: a rollout waiting on its sign-off has no grip, only the way to the sign-off", async () => {
    vi.mocked(api.flow).mockResolvedValueOnce({ ...flow, rows: flow.rows.map((r) => r.id === 3 ? { ...r, signoff_needed: true } : r) })
    mount("/board?view=kanban")
    expect(await screen.findByRole("link", { name: "Sign-off before Sensor pilot" })).toHaveAttribute("href", "/projects/3/signoff")
    expect(screen.queryByRole("button", { name: "Move Fine one to Sensor pilot" })).toBeNull()
    expect(screen.getByRole("button", { name: "Move Late one to Sensor pilot" })).toBeInTheDocument()   // the others keep theirs
  })

  it("switching views keeps the switcher and the focus; the choice is remembered (P2-42, advice B1)", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("radio", { name: "Kanban" }))
    await screen.findByRole("group", { name: "Rollouts by stage" })
    expect(document.activeElement).toBe(screen.getByRole("radio", { name: "Kanban" }))   // the header was not redrawn
    cleanup()
    mount()   // no ?view=: the last choice
    expect(await screen.findByRole("group", { name: "Rollouts by stage" })).toBeInTheDocument()
  })

  it("j/k leave Ctrl and Cmd shortcuts alone (P3-37)", async () => {
    mount()
    const list = (await screen.findByRole("list", { name: "Active rollouts, stuck first" }))
    rows()[0].focus()
    expect(fireEvent.keyDown(list, { key: "k", ctrlKey: true })).toBe(true)   // not prevented
    expect(fireEvent.keyDown(list, { key: "j" })).toBe(false)
    expect(document.activeElement).toBe(rows()[1])
  })

  it("Gantt: a table of rollouts and their stages, dates in words, and it reloads with the Flow (P2-35, P3-47)", async () => {
    const user = userEvent.setup()
    mount("/board?view=gantt&filter=attention")
    const table = await screen.findByRole("table", { name: "Rollouts on a timeline" })
    expect(table.querySelectorAll('[role="row"]')).toHaveLength(3)   // the header and the two that need attention
    await user.click(screen.getByRole("button", { name: "Stages of Late one" }))
    expect(screen.getByRole("button", { name: "Stages of Late one" })).toHaveAttribute("aria-expanded", "true")
    expect(table).toHaveTextContent("plan 6 Sep to 1 Oct; started 5 Sep")   // read-only: no bar to tab to, the dates are still said
    expect(api.flowPlan).toHaveBeenCalledTimes(1)
    fireEvent(window, new Event("focus"))   // the Flow reloads on coming back to the tab
    await waitFor(() => expect(api.flowPlan).toHaveBeenCalledTimes(2))
  })
})
