// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Workload from "./Workload"
import { WorkloadRows } from "@/components/WorkloadWidget"
import { admin } from "./fixtures"
import type { WorkloadCell, WorkloadData, WorkloadPerson } from "@/lib/api"

const weeks = ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]
const cell = (week: string, hours: number, level: WorkloadCell["level"], cap = 30): WorkloadCell => ({ week, tasks: 2, task_hours: hours - 4, pm_hours: 4, hours, pct: Math.round(100 * hours / cap), level })
const person = (id: number, name: string, hours: number[], level: WorkloadCell["level"][], capacity = 30, custom = false): WorkloadPerson => ({
  id, name, role: "Member", avatar_url: null, capacity, custom_capacity: custom, rollouts: 1, weeks: weeks.map((w, i) => cell(w, hours[i], level[i], capacity)), peak: 0,
})
const data: WorkloadData = {
  today: "2026-11-04", weeks, capacity_default: 30, warn_pct: 90, over: 1, heavy: 1,
  people: [
    person(2, "Priya Nair", [34, 20, 10, 8], ["over", "ok", "ok", "ok"]),
    person(3, "Omar Haddad", [28, 12, 6, 6], ["warn", "ok", "ok", "ok"]),
    person(4, "Lena Fox", [6, 4, 4, 4], ["ok", "ok", "ok", "ok"], 12, true),
  ],
}

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), workload: vi.fn(async () => data) }))

const mount = () => render(<MemoryRouter><Workload user={admin} /></MemoryRouter>)
const names = () => within(screen.getByRole("region", { name: "Workload by person" })).queryAllByRole("rowheader").map((r) => /(Priya|Omar|Lena)/.exec(r.textContent ?? "")?.[1])

describe("People › Workload", () => {
  it("draws four weeks per person with the state in words and the own capacity marked", async () => {
    mount()
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Workload")
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Person", "This week", "Week of 9 Nov", "Week of 16 Nov", "Week of 23 Nov"])
    const link = screen.getByRole("link", { name: /Week of 2 Nov: 34 h of 30 h \(113 %\).*Over capacity$/ })
    expect(link).toHaveAttribute("href", "/people/2")                       // click through to the tasks
    expect(screen.getByRole("link", { name: /^Week of 2 Nov: 28 h of 30 h.*Heavy$/ })).toBeInTheDocument()
    expect(screen.getByText(/12 h a week \(own\)/)).toBeInTheDocument()
    expect(screen.getByText("1 over capacity · 1 heavy")).toBeInTheDocument()
  })

  it("filters by name and to the heavy or over", async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByRole("heading", { level: 1 })
    expect(names()).toHaveLength(3)
    await user.click(screen.getByRole("radio", { name: "Heavy or over (2)" }))
    expect(names()).toEqual(["Priya", "Omar"])
    await user.type(screen.getByLabelText("Find a person"), "omar")
    expect(names()).toEqual(["Omar"])
    await user.clear(screen.getByLabelText("Find a person"))
    await user.type(screen.getByLabelText("Find a person"), "lena")
    expect(screen.getByText("Nobody matches “lena”.")).toBeInTheDocument()
  })
})

describe("Dashboard workload widget", () => {
  it("lists the busiest first, capped at the limit, with this week against capacity", () => {
    render(<MemoryRouter><WorkloadRows w={data} limit={2} /></MemoryRouter>)
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
    expect(screen.getByText(/34 h of 30 h this week/)).toBeInTheDocument()
    expect(screen.getByText("Over capacity")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Priya Nair" })).toHaveAttribute("href", "/people/2")
    expect(screen.queryByText("Lena Fox")).toBeNull()
  })

  it("says so when nobody is on the list", () => {
    render(<MemoryRouter><WorkloadRows w={{ ...data, people: [] }} limit={6} /></MemoryRouter>)
    expect(screen.getByText("Nobody to plan yet.")).toBeInTheDocument()
  })
})
