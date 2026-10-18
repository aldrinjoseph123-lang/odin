import { describe, expect, it } from "vitest"
import { datePresets } from "./datePresets"

const at = (y: number, m: number, d: number) => Object.fromEntries(datePresets(new Date(y, m - 1, d, 13)).map((p) => [p.label, p.value]))

describe("the date picker's quick picks (B4)", () => {
  it("counts from a Wednesday", () => {
    expect(at(2026, 10, 14)).toEqual({ Tomorrow: "2026-10-15", "Next Monday": "2026-10-19", "+1 week": "2026-10-21" })
  })
  it("sends a Monday to the next Monday, not to itself", () => {
    expect(at(2026, 10, 12)["Next Monday"]).toBe("2026-10-19")
  })
  it("takes a Sunday to the following day", () => {
    expect(at(2026, 10, 18)["Next Monday"]).toBe("2026-10-19")
  })
  it("rolls over the month and year", () => {
    expect(at(2026, 12, 30)).toEqual({ Tomorrow: "2026-12-31", "Next Monday": "2027-01-04", "+1 week": "2027-01-06" })
  })
})
