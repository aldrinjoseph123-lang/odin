import { describe, expect, it } from "vitest"
import { pushRecent, rolloutName } from "./recentRollouts"

describe("recent rollouts for the palette (B7)", () => {
  it("puts the newest first, once, and keeps five", () => {
    let l = [1, 2, 3, 4, 5].map((id) => ({ id, name: `R${id}` }))
    l = pushRecent(l, { id: 3, name: "R3 renamed" })
    expect(l.map((r) => r.id)).toEqual([3, 1, 2, 4, 5])
    expect(pushRecent(l, { id: 9, name: "R9" }).map((r) => r.id)).toEqual([9, 3, 1, 2, 4])
  })
  it("reads the name off the page title, and ignores the loading and missing states", () => {
    expect(rolloutName("EDR Rollout - Globex · Odin")).toBe("EDR Rollout - Globex")
    expect(rolloutName("Rollout · Odin")).toBeNull()
    expect(rolloutName("Rollout not found · Odin")).toBeNull()
  })
})
