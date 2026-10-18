// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MoveConfirm } from "./MoveConfirm"
import * as api from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), changeStage: vi.fn(async () => ({ ok: true as const, undo: "/undo" })) }))
afterEach(cleanup)

const detail = (gate: api.FlowDetail["gate"]): api.FlowDetail => ({
  id: 5, name: "EDR", client: "Globex", vendor_name: null, product_name: null, delivery_mode: "Direct", outsourcer_name: null, owner_name: "Admin User",
  stage: "Scoping", stage_index: 1, next_stage: "Kickoff", state: "on_track", over_by: null, start_date: "2026-09-01", target_end_date: null, days_left: null,
  today: "2026-10-01", stages: [], documents: 1, recent_notes: [], can_move: true, participants: [], assignable: [], can_edit: true, me: 1,
  customer_approval: false, can_approve: false, approval: null,
  tasks: [{ id: 1, title: "Survey", done: false, due_date: null, assignee: null, assignee_id: null, assignee_avatar_url: null, stage: "Scoping" }],
  gate,
})
const held = [{ stage: "Scoping", kind: "tasks" as const, count: 1, text: "1 open task" }, { stage: "Scoping", kind: "document" as const, category: "Client PO", text: "Client PO missing" }]

describe("MoveConfirm and a stage gate", () => {
  it("names what holds the move and keeps it shut for someone who may not override", () => {
    render(<MoveConfirm d={detail({ blocked: held, can_override: false })} onMoved={() => {}} onStale={() => {}} />)
    expect(screen.getByText("Before leaving Scoping: 1 open task · Client PO missing")).toBeInTheDocument()
    expect(screen.queryByText(/open task still in Scoping/)).toBeNull()   // said once, by the gate
    expect(screen.getByRole("button", { name: /Move to Kickoff/ })).toHaveAttribute("aria-disabled", "true")
    expect(screen.queryByRole("button", { name: "Override with a reason" })).toBeNull()
  })

  it("opens with a typed reason for an admin or the project manager, and sends it", async () => {
    const moved = vi.fn()
    render(<MoveConfirm d={detail({ blocked: held, can_override: true })} onMoved={moved} onStale={() => {}} />)
    await userEvent.click(screen.getByRole("button", { name: "Override with a reason" }))
    const go = screen.getByRole("button", { name: /Move to Kickoff/ })
    expect(go).toHaveAttribute("aria-disabled", "true")   // no reason yet
    await userEvent.type(screen.getByRole("textbox", { name: /Reason for moving past the gate/ }), "PO by email")
    await userEvent.click(go)
    await new Promise((r) => setTimeout(r, 450))                        // the double-click guard
    await userEvent.click(screen.getByRole("button", { name: "Move past the gate" }))
    expect(api.changeStage).toHaveBeenCalledWith(5, "Kickoff", "", "Scoping", "PO by email")
    expect(moved).toHaveBeenCalled()
  })

  it("moves as before when nothing holds it", () => {
    render(<MoveConfirm d={detail({ blocked: [], can_override: false })} onMoved={() => {}} onStale={() => {}} />)
    expect(screen.getByRole("button", { name: /Move to Kickoff/ })).not.toHaveAttribute("aria-disabled", "true")
    expect(screen.getByText("1 open task still in Scoping")).toBeInTheDocument()
  })
})
