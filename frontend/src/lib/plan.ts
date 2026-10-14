// Plan editing, pure: moving one stage's dates and carrying the stages after
// it along, and filling empty stages from the suggestion. Tested in plan.test.ts.
export type PlanRow = { id: number; plan_start: string | null; plan_end: string | null; suggested_start: string; suggested_end: string }

const DAY = 864e5
const toDay = (iso: string) => Date.parse(`${iso}T00:00:00Z`)
export const addDays = (iso: string, n: number) => new Date(toDay(iso) + n * DAY).toISOString().slice(0, 10)
export const daysBetween = (a: string, b: string) => Math.round((toDay(b) - toDay(a)) / DAY)

// A stage's length as the server counts it: working days in (a, b] when the
// workspace counts them (services/workdays.py), else calendar days.
export function workDays(a: string, b: string, cal?: { working: boolean; week: number[]; off: string[] }) {
  if (!cal?.working || !cal.week.length) return daysBetween(a, b)
  const off = new Set(cal.off)
  let n = 0
  for (let i = 1; i <= daysBetween(a, b); i++) {
    const d = addDays(a, i)
    if (cal.week.includes((new Date(toDay(d)).getUTCDay() + 6) % 7) && !off.has(d)) n++
  }
  return n
}

// Set one date. Moving a start keeps the stage's length; moving an end
// changes it. With `cascade`, every later stage moves by the same number of
// days the end did, so the plan stays back to back.
export function setDate<T extends PlanRow>(rows: T[], index: number, field: "plan_start" | "plan_end", value: string, cascade: boolean): T[] {
  const out = rows.map((r) => ({ ...r }))
  const r = out[index]
  const oldEnd = r.plan_end ?? r.suggested_end
  if (field === "plan_start") {
    const length = r.plan_start && r.plan_end ? daysBetween(r.plan_start, r.plan_end) : daysBetween(r.suggested_start, r.suggested_end)
    r.plan_start = value
    r.plan_end = addDays(value, Math.max(0, length))
  } else {
    r.plan_start = r.plan_start ?? r.suggested_start
    r.plan_end = value < r.plan_start ? r.plan_start : value
  }
  const shift = daysBetween(oldEnd, r.plan_end!)
  if (cascade && shift !== 0) {
    for (let i = index + 1; i < out.length; i++) {
      const x = out[i]
      if (!x.plan_start || !x.plan_end) continue
      x.plan_start = addDays(x.plan_start, shift)
      x.plan_end = addDays(x.plan_end, shift)
    }
  }
  return out
}

// Every stage without dates takes the suggested ones (SLA or default length, back to back).
export const fillSuggested = <T extends PlanRow>(rows: T[]): T[] =>
  rows.map((r) => (r.plan_start && r.plan_end ? r : { ...r, plan_start: r.suggested_start, plan_end: r.suggested_end }))

// A drag on a planned bar (the Flow's Gantt): `move` shifts both ends,
// `end` and `start` resize one edge (never past the other). With `cascade`,
// a move or a new end carries every later stage by the same days, as setDate does.
export function dragPlan<T extends PlanRow>(rows: T[], index: number, mode: "move" | "start" | "end", days: number, cascade: boolean): T[] {
  const out = rows.map((r) => ({ ...r }))
  const r = out[index]
  const start = r.plan_start ?? r.suggested_start, end = r.plan_end ?? r.suggested_end
  if (mode === "start") {
    r.plan_start = addDays(start, days) > end ? end : addDays(start, days); r.plan_end = end
    return out
  }
  r.plan_start = mode === "move" ? addDays(start, days) : start
  r.plan_end = addDays(end, days) < r.plan_start ? r.plan_start : addDays(end, days)
  const shift = daysBetween(end, r.plan_end)
  if (cascade && shift !== 0) {
    for (let i = index + 1; i < out.length; i++) {
      const x = out[i]
      if (!x.plan_start || !x.plan_end) continue
      x.plan_start = addDays(x.plan_start, shift); x.plan_end = addDays(x.plan_end, shift)
    }
  }
  return out
}

// The stages a save must send: those whose planned dates changed.
export const changedStages = <T extends PlanRow>(before: T[], after: T[]) =>
  after.filter((a, i) => a.plan_start !== before[i].plan_start || a.plan_end !== before[i].plan_end)
    .map((a) => ({ id: a.id, plan_start: a.plan_start, plan_end: a.plan_end }))
