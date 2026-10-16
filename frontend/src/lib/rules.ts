import type { RuleAction, RuleActionKind, RuleCondition, RuleConditionKind, RuleDraft, RuleOptions, RulesData } from "@/lib/api"

// Settings › Automations (services/rules.py): the pure parts of the editor —
// a fresh condition or action of a kind, a field value in words, and the one
// sentence a rule reads as in the list.

export const BLANK_RULE: RuleDraft = { name: "", event: "stage_entered", event_config: {}, conditions: [], actions: [] }

type Field = RuleOptions["fields"][number]

// the first sensible value of a field's kind, as Odin stores it (yes / no as "1" / "0")
export const firstValue = (f: Field | undefined): string => f?.kind === "choice" ? f.choices[0] ?? "" : f?.kind === "yesno" ? "1" : ""

export function blankCondition(kind: RuleConditionKind, o: RuleOptions): RuleCondition {
  if (kind === "field") return { kind, field_id: o.fields[0]?.id, value: firstValue(o.fields[0]) }
  return { kind, value: kind === "stage" ? o.stages[0] ?? "" : kind === "delivery_mode" ? o.delivery_modes[0] ?? "" : "" }
}

export function blankAction(kind: RuleActionKind, o: RuleOptions): RuleAction {
  switch (kind) {
    case "notify": return { kind, roles: ["Project manager"], user_ids: [], email: true, message: "" }
    case "add_task": return { kind, template_task_id: o.template_tasks[0]?.id ?? 0 }
    case "add_raid": return { kind, raid_kind: o.raid_kinds[0] ?? "risk", title: "", impact: "medium" }
    case "set_field": return { kind, field_id: o.fields[0]?.id ?? 0, value: firstValue(o.fields[0]) }
    case "teams": return { kind, message: "" }
  }
}

// a stored value as a person reads it
export function valueWords(f: Field | undefined, v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "any value"
  if (f?.kind === "yesno") return v === "1" ? "Yes" : "No"
  return v
}

const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1)

// "When a rollout enters a stage, if stage is Deployment, then tell people and post to Teams."
export function ruleSummary(r: RuleDraft, d: Pick<RulesData, "events" | "conditions" | "actions" | "options">): string {
  const field = (id?: number) => d.options.fields.find((f) => f.id === id)
  let when = lower(d.events[r.event] ?? r.event)
  if (r.event === "document_uploaded") when += r.event_config.category ? ` in ${r.event_config.category}` : ""
  if (r.event === "field_set") {
    const f = field(r.event_config.field_id)
    when = `${f?.name ?? "a field"} is set${r.event_config.value ? ` to ${valueWords(f, r.event_config.value)}` : ""}`
  }
  const ifs = r.conditions.map((c) => c.kind === "field"
    ? `${field(c.field_id)?.name ?? "a field"} is ${valueWords(field(c.field_id), c.value)}`
    : `${lower(d.conditions[c.kind])} ${c.value}`)
  const thens = r.actions.map((a) => lower(d.actions[a.kind]).replace(/ \(.*\)$/, ""))
  return `When ${when}${ifs.length ? `, if ${ifs.join(" and ")}` : ""}, then ${thens.join(", ") || "nothing"}.`
}
