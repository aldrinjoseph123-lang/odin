import { describe, expect, it } from "vitest"
import type { RulesData } from "@/lib/api"
import { blankAction, blankCondition, ruleSummary, valueWords } from "@/lib/rules"

const options: RulesData["options"] = {
  stages: ["Scoping", "Deployment"], delivery_modes: ["Distribution/MSSP", "Outsourced"], categories: ["Client PO", "Deliverable"],
  roles: ["Project manager", "Sales", "Coordinator"], raid_kinds: ["risk", "issue"], raid_levels: ["low", "medium", "high"],
  fields: [{ id: 3, name: "Region", kind: "choice", choices: ["UAE", "KSA"] }, { id: 4, name: "Managed", kind: "yesno", choices: [] }],
  users: [{ id: 2, name: "Priya" }], template_tasks: [{ id: 7, label: "Standard › Kickoff › Book the call" }],
}
const words: Pick<RulesData, "events" | "conditions" | "actions" | "options"> = {
  events: { rollout_created: "A rollout is created", stage_entered: "A rollout enters a stage", stage_sla_breached: "A stage goes over its SLA", task_overdue: "A task becomes overdue",
    ask_completed: "A customer or partner completes an ask", document_uploaded: "A document is uploaded", field_set: "A custom field is set",
    stage_declined: "The customer declines a stage", milestone_missed: "A milestone is missed" },
  conditions: { stage: "Stage is", delivery_mode: "Delivery mode is", field: "Field equals", client: "Client is" },
  actions: { notify: "Tell people (bell and email)", add_task: "Add a task from a template task", add_raid: "Add a RAID item", set_field: "Set a field", teams: "Post to Teams" },
  options,
}

describe("rules", () => {
  it("reads a rule as one sentence", () => {
    expect(ruleSummary({ name: "x", event: "stage_entered", event_config: {}, conditions: [{ kind: "stage", value: "Deployment" }, { kind: "field", field_id: 4, value: "1" }],
      actions: [blankAction("notify", options), blankAction("teams", options)] }, words))
      .toBe("When a rollout enters a stage, if stage is Deployment and Managed is Yes, then tell people, post to Teams.")
    expect(ruleSummary({ name: "x", event: "field_set", event_config: { field_id: 3, value: null }, conditions: [], actions: [] }, words))
      .toBe("When Region is set, then nothing.")
    expect(ruleSummary({ name: "x", event: "document_uploaded", event_config: { category: "Deliverable" }, conditions: [], actions: [blankAction("add_raid", options)] }, words))
      .toBe("When a document is uploaded in Deliverable, then add a RAID item.")
  })

  it("starts each condition and action on a sensible value", () => {
    expect(blankCondition("stage", options)).toEqual({ kind: "stage", value: "Scoping" })
    expect(blankCondition("field", options)).toEqual({ kind: "field", field_id: 3, value: "UAE" })
    expect(blankAction("set_field", options)).toEqual({ kind: "set_field", field_id: 3, value: "UAE" })
    expect(blankAction("add_task", options)).toEqual({ kind: "add_task", template_task_id: 7 })
    expect(valueWords(options.fields[1], "0")).toBe("No")
    expect(valueWords(options.fields[0], null)).toBe("any value")
  })
})
