import { describe, expect, it } from "vitest"
import { dragSteps } from "./reorder"

describe("dragSteps", () => {
  const ids = [10, 11, 12, 13]
  it("counts the one-step moves from the dragged row to the row it was dropped on", () => {
    expect(dragSteps(ids, 10, 13)).toEqual(["down", "down", "down"])
    expect(dragSteps(ids, 13, 11)).toEqual(["up", "up"])
    expect(dragSteps(ids, 11, 12)).toEqual(["down"])
  })
  it("does nothing for a drop on itself or on an unknown row", () => {
    expect(dragSteps(ids, 11, 11)).toEqual([])
    expect(dragSteps(ids, 11, 99)).toEqual([])
  })
})
