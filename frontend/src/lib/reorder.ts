// A drag in a list is saved as the one-step moves the reorder routes take
// (the same ones the up / down arrows post): dropping row `from` onto row `to`
// is |to - from| steps in one direction.
export type Step = "up" | "down"
export function dragSteps(ids: number[], activeId: number, overId: number): Step[] {
  const from = ids.indexOf(activeId), to = ids.indexOf(overId)
  if (from < 0 || to < 0 || from === to) return []
  return Array<Step>(Math.abs(to - from)).fill(to < from ? "up" : "down")
}
