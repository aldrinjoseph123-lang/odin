// @vitest-environment jsdom
// What the 28 Oct simulation asked of the Flow: filters that combine, a closed list for outsiders, a note box.
import { beforeEach, describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Flow from "./Flow"
import { admin, flow, flowRow } from "./fixtures"
import * as api from "@/lib/api"
import { toast } from "@/lib/toast"

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  flow: vi.fn(async () => flow),
  flowDetail: vi.fn(),
  postForm: vi.fn(async () => ({ ok: true, messages: [] })),
  requestApproval: vi.fn(async () => ({ id: 9, stage: "Scoping", status: "pending", decided_by: null, comment: null, chases: 0 })),
  pendingIntake: vi.fn(async () => ({ rows: [], can_confirm: true, can_lead: true, leads: [], po_category: "Client PO" })),
}))

beforeEach(() => { localStorage.clear() })

const names = () => screen.getAllByRole("button", { name: /, (Globex|Initech)\./ }).map((r) => r.getAttribute("aria-label")?.split(",")[0])
const mount = (url: string, user: api.User = admin) => render(<MemoryRouter initialEntries={[url]}><Flow user={user} /></MemoryRouter>)
// Stuck one is nobody's but the first reader's colleague
const someoneElses = { ...flow, rows: flow.rows.map((r) => (r.id === 2 ? { ...r, mine: false } : r)) }

describe("Mine combines with the other filters", () => {
  it("Mine + Needs attention shows what is late on my rollouts; each chip toggles", async () => {
    vi.mocked(api.flow).mockResolvedValue(someoneElses)
    const user = userEvent.setup()
    mount("/board")
    await screen.findByText("Late one")
    expect(names()).toEqual(["Late one", "Stuck one"])                      // needs attention, anyone's
    await user.click(screen.getByRole("button", { name: /^Mine, / }))
    await user.click(screen.getByRole("button", { name: /^Needs attention, / }))
    expect(names()).toEqual(["Late one"])                                   // both at once
    expect(screen.getByRole("button", { name: /^Mine, / })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: /^Needs attention, / })).toHaveAttribute("aria-pressed", "true")
    await user.click(screen.getByRole("button", { name: /^Needs attention, / }))   // a second click clears the reading, Mine stays
    expect(screen.getByRole("button", { name: /^Mine, / })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByRole("button", { name: /^Needs attention, / })).toHaveAttribute("aria-pressed", "false")
  })

  it("the address carries both, and the old ?filter=mine still means Mine", async () => {
    vi.mocked(api.flow).mockResolvedValue(someoneElses)
    mount("/board?filter=attention&mine=1")
    await screen.findByText("Late one")
    expect(names()).toEqual(["Late one"])
    mount("/board?filter=mine")
    await waitFor(() => expect(screen.getAllByRole("button", { name: /^Mine, / }).at(-1)).toHaveAttribute("aria-pressed", "true"))
  })
})

describe("an outsider keeps closed rollouts", () => {
  const partner = { ...admin, kind: "external" as const, permissions: ["view_board"] }
  it("lists them under Closed with the sign-off and report links, not as 'not shared'", async () => {
    vi.mocked(api.flow).mockResolvedValue({ ...flow, rows: [], closed: [
      { id: 7, name: "Globex EDR", client: "Globex", closed_on: "2026-10-20", signed_off: true, report: true },
      { id: 8, name: "Initech SIEM", client: "Initech", closed_on: "2026-09-02", signed_off: false, report: false },
    ] })
    mount("/board", partner)
    const closed = await screen.findByRole("region", { name: /Closed/ })
    expect(screen.queryByText(/No rollout is shared with you yet/)).toBeNull()
    expect(within(closed).getByRole("link", { name: "Globex EDR" })).toHaveAttribute("href", "/projects/7")
    expect(within(closed).getByText("Closed 20 Oct")).toBeInTheDocument()
    expect(within(closed).getAllByRole("link", { name: "Sign-off" })).toHaveLength(1)
    expect(within(closed).getByRole("link", { name: "Sign-off" })).toHaveAttribute("href", "/projects/7/signoff")
    expect(within(closed).getByRole("link", { name: "Report" })).toHaveAttribute("href", "/projects/7/report")
  })

  it("with nothing closed either, the old words stay", async () => {
    vi.mocked(api.flow).mockResolvedValue({ ...flow, rows: [], closed: [] })
    mount("/board", partner)
    expect(await screen.findByText(/No rollout is shared with you yet/)).toBeInTheDocument()
  })
})

describe("the note box in the Flow detail", () => {
  const detail = {
    id: 1, name: "Late one", client: "Globex", vendor_name: null, product_name: null, delivery_mode: "Direct", outsourcer_name: null, owner_name: "Admin User",
    stage: "Scoping", stage_index: 1, next_stage: "Sensor pilot", state: "on_track", over_by: null, start_date: "2026-09-01", target_end_date: "2026-12-01", days_left: 60,
    today: "2026-09-29", stages: flowRow({}).stages.map((name, i) => ({ name, status: i < 1 ? "done" : i === 1 ? "current" : "next", sla_days: null, entered_at: null, days: null })),
    tasks: [], documents: 0, recent_notes: [], can_move: false, participants: [], assignable: [], can_edit: false, me: 1, customer_approval: false, can_approve: false, approval: null,
  } as unknown as api.FlowDetail
  const withNote = { ...admin, permissions: [...admin.permissions, "add_project_note"] }

  it("posts the note to the existing route, shared on request, and toasts", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue(detail)
    mount("/board?rollout=1", withNote)
    const box = await screen.findByRole("textbox", { name: "Status note" })
    // fireEvent: jsdom has no layout, so the resizable handle swallows pointer clicks inside the pane
    fireEvent.change(box, { target: { value: "Waiting on the PO" } })
    fireEvent.click(screen.getByRole("switch", { name: "Visible to the customer" }))
    fireEvent.click(screen.getByRole("button", { name: "Add note" }))
    await waitFor(() => expect(api.postForm).toHaveBeenCalledWith("/projects/1/note", { note: "Waiting on the PO", share: "1" }))
    expect(toast).toHaveBeenCalledWith("Note added, visible to the customer")
    expect(box).toHaveValue("")
    fireEvent.change(box, { target: { value: "Internal only" } })
    fireEvent.click(screen.getByRole("button", { name: "Add note" }))
    await waitFor(() => expect(api.postForm).toHaveBeenLastCalledWith("/projects/1/note", { note: "Internal only" }))
  })

  it("is not drawn for someone who may not add notes", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue(detail)
    mount("/board?rollout=1", admin)
    await screen.findByRole("heading", { name: /Late one/ })
    expect(screen.queryByRole("textbox", { name: "Status note" })).toBeNull()
  })

  it("keeps the words and shows the server's reason when the note is refused", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue(detail)
    vi.mocked(api.postForm).mockRejectedValueOnce(new api.ApiError(400, "Write the note first"))
    mount("/board?rollout=1", withNote)
    const box = await screen.findByRole("textbox", { name: "Status note" })
    fireEvent.change(box, { target: { value: "x" } })
    fireEvent.click(screen.getByRole("button", { name: "Add note" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Write the note first")
    expect(box).toHaveValue("x")
  })
})

describe("customer approval in the Flow detail (one approver, a decline pauses)", () => {
  const base = {
    id: 1, name: "Late one", client: "Globex", vendor_name: null, product_name: null, delivery_mode: "Direct", outsourcer_name: null, owner_name: "Admin User",
    stage: "Scoping", stage_index: 1, next_stage: "Sensor pilot", state: "on_track", over_by: null, start_date: "2026-09-01", target_end_date: "2026-12-01", days_left: 60,
    today: "2026-09-29", stages: flowRow({}).stages.map((name, i) => ({ name, status: i < 1 ? "done" : i === 1 ? "current" : "next", sla_days: null, entered_at: null, days: null })),
    tasks: [], documents: 0, recent_notes: [], participants: [], assignable: [], can_edit: false, me: 1,
    customer_approval: true, approver: { id: 5, name: "Ann" },
  }

  it("the project manager re-requests a declined stage, and the move offers the override", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue({ ...base, can_move: true, can_approve: false,
      approval: { id: 3, stage: "Scoping", status: "declined", decided_by: "Ann", comment: "Not yet", chases: 0 },
      gate: { blocked: [{ stage: "Scoping", kind: "declined", text: "The customer declined Scoping: Not yet. Ask again, or override with a reason" }], can_override: true },
    } as unknown as api.FlowDetail)
    mount("/board?rollout=1")
    fireEvent.click(await screen.findByRole("button", { name: "Re-request approval" }))
    await waitFor(() => expect(api.requestApproval).toHaveBeenCalledWith(1))
    expect(toast).toHaveBeenCalledWith("Asked Ann to approve Scoping")
    expect(screen.getAllByText(/The customer declined Scoping: Not yet\. Ask again/).length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: "Override with a reason" })).toBeInTheDocument()
  })

  it("another customer contact sees who it waits on, with no way to decide", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue({ ...base, can_move: false, can_approve: false,
      approval: { id: 3, stage: "Scoping", status: "pending", decided_by: null, comment: null },
    } as unknown as api.FlowDetail)
    mount("/board?rollout=1")
    expect(await screen.findByText("Waiting on Ann to approve Scoping")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull()
    expect(screen.queryByRole("button", { name: /request approval/i })).toBeNull()
  })

  it("the approver gets the decision card", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue({ ...base, can_move: false, can_approve: true,
      approval: { id: 3, stage: "Scoping", status: "pending", decided_by: null, comment: null },
    } as unknown as api.FlowDetail)
    mount("/board?rollout=1")
    expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument()
    expect(screen.queryByText(/Waiting on Ann/)).toBeNull()
  })
})

describe("a repeating task nobody ticks", () => {
  const task = (id: number, stalled: boolean) => ({ id, title: `Weekly call ${id}`, done: false, due_date: "2026-09-20", assignee: null, assignee_id: null, assignee_avatar_url: null, stage: "Scoping",
    recurrence: "weekly", recur_until: null, stalled, kind: "task", ask_category: null, questions: [], waits_on: [], blocked_by: [] })
  const detail = {
    id: 1, name: "Late one", client: "Globex", vendor_name: null, product_name: null, delivery_mode: "Direct", outsourcer_name: null, owner_name: "Admin User",
    stage: "Scoping", stage_index: 1, next_stage: "Sensor pilot", state: "on_track", over_by: null, start_date: "2026-09-01", target_end_date: "2026-12-01", days_left: 60,
    today: "2026-09-29", stages: flowRow({}).stages.map((name, i) => ({ name, status: i < 1 ? "done" : i === 1 ? "current" : "next", sla_days: null, entered_at: null, days: null })),
    tasks: [task(1, false), task(2, true)], documents: 0, recent_notes: [], can_move: false, participants: [], assignable: [], can_edit: false, me: 1, customer_approval: false, can_approve: false, approval: null,
  } as unknown as api.FlowDetail

  it("says so on the stalled row only, in the warn colour", async () => {
    vi.mocked(api.flowDetail).mockResolvedValue(detail)
    mount("/board?rollout=1")
    const stalled = await screen.findByText(/stalled: an earlier one is still open/)
    expect(stalled).toHaveTextContent("repeats every week · stalled: an earlier one is still open")
    expect(stalled).toHaveClass("text-warn")
    expect(screen.getAllByText(/^repeats every week/)).toHaveLength(2)
    expect(screen.getAllByText(/stalled/)).toHaveLength(1)
  })
})
