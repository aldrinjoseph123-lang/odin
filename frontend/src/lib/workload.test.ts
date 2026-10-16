import { describe, expect, it } from "vitest"
import { cellTitle, hrs, levelWord, pickerHint, weekLabel } from "./workload"

const cell = { week: "2026-11-02", tasks: 2, task_hours: 7, pm_hours: 4, hours: 11, pct: 37, level: "ok" as const }

describe("workload wording", () => {
  it("writes hours without a trailing .0", () => {
    expect([hrs(34), hrs(5.5), hrs(0)]).toEqual(["34 h", "5.5 h", "0 h"])
  })
  it("names the weeks and the heavy states in words, not colour alone", () => {
    expect([weekLabel("2026-11-02", 0), weekLabel("2026-11-09", 1)]).toEqual(["This week", "Week of 9 Nov"])
    expect([levelWord("ok"), levelWord("warn"), levelWord("over")]).toEqual(["", "Heavy", "Over capacity"])
  })
  it("explains a cell's hours", () => {
    expect(cellTitle(cell, 30)).toBe("11 h of 30 h (37 %): 7 h in 2 tasks, 4 h managing rollouts")
    expect(cellTitle({ ...cell, tasks: 1, pm_hours: 0 }, 30)).toBe("11 h of 30 h (37 %): 7 h in 1 task")
  })
  it("hints the hours that week in the picker", () => {
    expect(pickerHint("Priya", { hours: 34 })).toBe("Priya · 34 h that week")
    expect(pickerHint("Priya")).toBe("Priya")
  })
})
