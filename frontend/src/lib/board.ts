import type { FlowRow } from "@/lib/api"

// The Kanban's rules, pure (tested in board.test.ts). Columns are stages in the
// shared order; a card sits in its rollout's stage, and the only move a drag may
// make is to that rollout's next stage (13 Oct 2026, the user's call), which the
// server checks again.

export function boardColumns(rows: FlowRow[], columns: string[]): Record<string, FlowRow[]> {
  const out: Record<string, FlowRow[]> = Object.fromEntries(columns.map((c) => [c, [] as FlowRow[]]))
  for (const r of rows) (out[r.stage] ??= []).push(r)
  return out
}

// Why this card may not go to this column, or null when it may.
export function dropRefusal(r: FlowRow, column: string): string | null {
  if (column === r.stage) return null
  if (!r.next_stage) return `${r.name} is in its last stage`
  if (column !== r.next_stage) return `${r.name} can only move to ${r.next_stage}, its next stage`
  if (!r.can_move) return `You cannot move ${r.name}`
  if (r.signoff_needed) return `${r.next_stage} waits for the signed sign-off`
  if (r.gate_blocked) return `Before leaving ${r.stage}: ${r.gate_reasons.join(" · ")}`
  return null
}

// no grip while the next move waits for a sign-off or a stage gate: the card links to it instead
export const canDrag = (r: FlowRow) => r.can_move && !!r.next_stage && !r.signoff_needed && !r.gate_blocked

// The column a card ended up in, after the board's own preview moved it.
export function columnOf(value: Record<string, FlowRow[]>, id: number): string | undefined {
  return Object.keys(value).find((c) => value[c].some((r) => r.id === id))
}
