// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { RuleEditor } from "./RuleEditor"
import type { RulesData } from "@/lib/api"
import { BLANK_RULE } from "@/lib/rules"

const data: RulesData = {
  rules: [], max: 50, keep_days: 90,
  events: { rollout_created: "A rollout is created", stage_entered: "A rollout enters a stage", stage_sla_breached: "A stage goes over its SLA", task_overdue: "A task becomes overdue",
    ask_completed: "A customer or partner completes an ask", document_uploaded: "A document is uploaded", field_set: "A custom field is set",
    stage_declined: "The customer declines a stage", milestone_missed: "A milestone is missed" },
  conditions: { stage: "Stage is", delivery_mode: "Delivery mode is", field: "Field equals", client: "Client is" },
  actions: { notify: "Tell people (bell and email)", add_task: "Add a task from a template task", add_raid: "Add a RAID item", set_field: "Set a field", teams: "Post to Teams" },
  options: {
    stages: ["Scoping", "Deployment"], delivery_modes: ["Distribution/MSSP", "Outsourced"], categories: ["Client PO", "Deliverable"],
    roles: ["Project manager", "Sales", "Coordinator"], raid_kinds: ["risk", "issue"], raid_levels: ["low", "medium", "high"],
    fields: [{ id: 3, name: "Region", kind: "choice", choices: ["UAE", "KSA"] }], users: [{ id: 2, name: "Priya" }], template_tasks: [],
  },
}
const api = vi.hoisted(() => ({ dryRunRule: vi.fn() }))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }))

beforeEach(() => {
  vi.clearAllMocks()
  api.dryRunRule.mockResolvedValue({ matches: [{ project_id: 4, name: "Globex EDR", client: "Globex", times: 2, last_at: "2026-10-12T09:00:00", last: "Entered Deployment" }],
    total: 1, replayed: "Stage moves in the stage history of the last 30 days.", caveat: "A dry run sends nothing and changes nothing." })
})
afterEach(cleanup)

describe("RuleEditor", () => {
  it("builds a rule in three columns and saves it", async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<RuleEditor data={data} start={BLANK_RULE} busy={false} onSave={onSave} onCancel={() => {}} />)
    expect(screen.getByRole("region", { name: "When" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "If" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Then" })).toBeInTheDocument()
    expect(screen.queryByRole("option", { name: "Add a task from a template task" })).toBeNull()   // no template tasks to pick
    await user.type(screen.getByLabelText("Name"), "Deployment starts")
    await user.selectOptions(screen.getByLabelText("Add a condition"), "stage")
    await user.selectOptions(screen.getByLabelText("Condition 1 stage"), "Deployment")
    await user.selectOptions(screen.getByLabelText("Add a condition"), "field")
    await user.selectOptions(screen.getByLabelText("Condition 2 value"), "KSA")
    await user.selectOptions(screen.getByLabelText("Add an action"), "notify")
    await user.click(screen.getByRole("checkbox", { name: "Coordinator" }))
    await user.click(screen.getByRole("checkbox", { name: "Email too (the bell always)" }))
    await user.selectOptions(screen.getByLabelText("Add an action"), "add_raid")
    await user.type(screen.getByLabelText("Action 2 title"), "Window to book")
    await user.click(screen.getByRole("button", { name: "Remove condition 2" }))
    await user.click(screen.getByRole("button", { name: "Save rule" }))
    expect(onSave).toHaveBeenCalledWith({
      name: "Deployment starts", event: "stage_entered", event_config: {}, conditions: [{ kind: "stage", value: "Deployment" }],
      actions: [{ kind: "notify", roles: ["Project manager", "Coordinator"], user_ids: [], email: false, message: "" },
        { kind: "add_raid", raid_kind: "risk", title: "Window to book", impact: "medium" }],
    })
  })

  it("asks for a field and an optional value when a field being set starts it", async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(<RuleEditor data={data} start={BLANK_RULE} busy={false} onSave={onSave} onCancel={() => {}} />)
    await user.type(screen.getByLabelText("Name"), "Moved to KSA")
    await user.selectOptions(screen.getByLabelText("Trigger"), "field_set")
    expect(screen.getByLabelText("Trigger value")).toHaveValue("")   // any value
    await user.selectOptions(screen.getByLabelText("Trigger value"), "KSA")
    await user.selectOptions(screen.getByLabelText("Add an action"), "teams")
    await user.click(screen.getByRole("button", { name: "Save rule" }))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ event: "field_set", event_config: { field_id: 3, value: "KSA" }, actions: [{ kind: "teams", message: "" }] }))
  })

  it("dry runs the rule as written and says what it replayed", async () => {
    const user = userEvent.setup()
    render(<RuleEditor data={data} start={{ ...BLANK_RULE, name: "Try" }} busy={false} onSave={() => {}} onCancel={() => {}} />)
    await user.click(screen.getByRole("button", { name: "Dry run" }))
    const out = await screen.findByRole("region", { name: "Dry run" })
    expect(api.dryRunRule).toHaveBeenCalledWith(expect.objectContaining({ name: "Try", event: "stage_entered" }))
    expect(within(out).getByRole("link", { name: "Globex EDR" })).toHaveAttribute("href", "/projects/4")
    expect(within(out).getByText(/2 times · latest: Entered Deployment/)).toBeInTheDocument()
    expect(within(out).getByText(/sends nothing and changes nothing/)).toBeInTheDocument()
  })
})
