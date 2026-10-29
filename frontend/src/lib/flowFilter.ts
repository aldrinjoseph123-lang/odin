import type { FlowRow } from "./api"

// The Flow's filters: one reading of the rollouts (all / needs attention / waiting
// on the customer) and "Mine" beside it, so "Mine" + "Needs attention" answers
// "what is late on my rollouts" (sim 28 Oct). Kept in the URL as ?filter= and ?mine=1.
export type Reading = "all" | "attention" | "customer"
export type FlowFilter = { reading: Reading; mine: boolean }
export const noFlowFilter: FlowFilter = { reading: "all", mine: false }

// attention: off track, or on track with a task past its date (critique 10 Oct; the state stays On track)
export const needsAttention = (r: Pick<FlowRow, "state" | "late_tasks">) => r.state !== "on_track" || r.late_tasks > 0

type Row = Pick<FlowRow, "state" | "late_tasks" | "approval" | "mine">
const reads = (r: Row, f: Reading) => f === "attention" ? needsAttention(r) : f === "customer" ? r.approval === "pending" : true
export const matchFlow = (r: Row, f: FlowFilter) => (!f.mine || r.mine) && reads(r, f.reading)

// From the address (or the last choice kept in this browser). `?filter=mine` is the
// old single-value form and still means Mine alone.
export function parseFlowFilter(filter: string | null, mine: string | null, kept: FlowFilter = noFlowFilter): FlowFilter {
  if (filter == null && mine == null) return kept
  const reading: Reading = filter === "attention" || filter === "customer" ? filter : "all"
  return { reading, mine: mine === "1" || filter === "mine" }
}

// The address parameters for a filter: filter=… and mine=1, each left out when it is the default.
export const flowFilterParams = (f: FlowFilter): { filter: string | null; mine: string | null } =>
  ({ filter: f.reading === "all" ? null : f.reading, mine: f.mine ? "1" : null })

// The chips with the count each would show given the other: Mine counts within the reading, a reading within Mine.
export function flowChips(rows: Row[], f: FlowFilter) {
  const n = (g: FlowFilter) => rows.filter((r) => matchFlow(r, g)).length
  return [
    { key: "all", label: "All", n: rows.length, on: f.reading === "all" && !f.mine },
    { key: "attention", label: "Needs attention", n: n({ ...f, reading: "attention" }), on: f.reading === "attention" },
    { key: "customer", label: "Waiting on customer", n: n({ ...f, reading: "customer" }), on: f.reading === "customer" },
    { key: "mine", label: "Mine", n: n({ ...f, mine: true }), on: f.mine },
  ] as const
}
