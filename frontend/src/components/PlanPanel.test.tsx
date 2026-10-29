// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import { PlanPanel } from "./PlanPanel"
import type { PlanData } from "@/lib/api"
import staff from "@/lib/__contract__/PlanData.json"

const api = vi.hoisted(() => ({ plan: vi.fn() }))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }))
vi.mock("@/components/AIHealthWhy", () => ({ AIHealthWhy: () => null }))
vi.mock("@/components/PlanGantt", () => ({ PlanGantt: () => null }))
afterEach(cleanup)

// the customer's cut, as routes/api.py api_plan makes it for an external: no SLA, baseline or slip
const outsider = (): PlanData => {
  const d = structuredClone(staff) as unknown as PlanData
  d.stages = d.stages.map(({ sla_days: _s, planned_days: _p, slip_days: _x, base_start: _b, base_end: _e, ...s }) => s as PlanData["stages"][number])
  const { vs_baseline_days: _v, baseline: _bl, ...finish } = d.finish
  return { ...d, finish: finish as PlanData["finish"], baseline_at: null, changes: [], can_edit: false }
}

const headers = async () => (await screen.findAllByRole("columnheader")).map((h) => h.textContent)

describe("PlanPanel", () => {
  it("shows staff the SLA and Slip columns and the baseline tile", async () => {
    api.plan.mockResolvedValue(staff)
    render(<PlanPanel projectId={1} />)
    expect(await headers()).toEqual(expect.arrayContaining(["SLA", "Slip"]))
    expect(screen.getByText("Against baseline")).toBeInTheDocument()
  })

  it("shows an outsider no SLA, Slip or baseline at all", async () => {
    api.plan.mockResolvedValue(outsider())
    render(<PlanPanel projectId={1} />)
    const h = await headers()
    expect(h).toContain("Forecast end")
    expect(h).not.toContain("SLA"); expect(h).not.toContain("Slip")
    expect(screen.queryByText("Against baseline")).toBeNull()
  })
})
