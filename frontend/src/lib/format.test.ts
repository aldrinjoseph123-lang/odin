import { describe, expect, it } from "vitest"
import { activeProjectsView, days, fmtDate, groupBlocks, initials, lateBy, localDateTime, nextUp, fitStages, fmtWhen, groupRows, deltaText, monthTicks, timelineDomain, addMonths, laneSpans, monthGrid, setDateFormat, localToday, signoffText, stageColumns, stateText, timeAgo, toLines } from "./format"

describe("initials", () => {
  it("takes the first letter of the first two words, upper-cased", () => {
    expect(initials("Ann Reyes")).toBe("AR")
    expect(initials("pm1")).toBe("P")
    expect(initials("Jane Okafor Smith")).toBe("JO")
    expect(initials(null)).toBe("?")
  })
})

describe("days", () => {
  it("rounds and marks unknown", () => {
    expect(days(8.6)).toBe("9 d")
    expect(days(0)).toBe("0 d")
    expect(days(null)).toBe("—")
  })
})

describe("fmtDate", () => {
  it("formats the date part only and dashes an empty value", () => {
    expect(fmtDate(null)).toBe("—")
    expect(fmtDate("2026-11-30T10:00:00")).toMatch(/30/)
  })
})

describe("stateText", () => {
  it("says the one thing each state needs", () => {
    expect(stateText({ state: "on_track", days_in_stage: 3.2, over_by: null, target_end_date: null })).toBe("3 d")
    expect(stateText({ state: "over_sla", days_in_stage: 9, over_by: 4, target_end_date: null })).toBe("9 d · 4 over SLA")
    expect(stateText({ state: "due_soon", days_in_stage: 1, over_by: null, target_end_date: "2026-11-30" })).toMatch(/^Due /)
    expect(stateText({ state: "overdue", days_in_stage: 1, over_by: null, target_end_date: "2020-01-01" })).toMatch(/^Overdue \d+ d$/)
  })
})

describe("localDateTime", () => {
  it("treats a naive stored timestamp as UTC and echoes junk unchanged", () => {
    expect(localDateTime("not a date")).toBe("not a date")
    expect(localDateTime("2026-09-25T03:32:31")).toMatch(/2026/)
  })
})

describe("groupBlocks", () => {
  it("runs consecutive items into one list and keeps the rest in order", () => {
    expect(groupBlocks([["h", "Timeline"], ["li", "a"], ["li", "b"], ["p", "text"], ["li", "c"]])).toEqual([
      { kind: "h", text: "Timeline" }, { kind: "ul", items: ["a", "b"] }, { kind: "p", text: "text" }, { kind: "ul", items: ["c"] },
    ])
    expect(groupBlocks([])).toEqual([])
  })
})

describe("activeProjectsView", () => {
  const from = (o: Record<string, string>) => (k: string) => o[k] ?? null
  it("lights the chip the URL means", () => {
    expect(activeProjectsView(from({}))).toBe("active")
    expect(activeProjectsView(from({ view: "overdue" }))).toBe("overdue")
    expect(activeProjectsView(from({ closed: "1" }))).toBe("closed")
    expect(activeProjectsView(from({ stage: "Scoping" }))).toBe("")
    expect(activeProjectsView(from({ view: "stale", closed: "1" }))).toBe("stale")
  })
})

describe("timeAgo", () => {
  const now = Date.parse("2026-09-27T12:00:00Z")
  it("counts up through minutes, hours and days, then gives a date", () => {
    expect(timeAgo("2026-09-27T11:59:40", now)).toBe("just now")
    expect(timeAgo("2026-09-27T11:40:00", now)).toBe("20 min ago")
    expect(timeAgo("2026-09-27T09:00:00", now)).toBe("3 h ago")
    expect(timeAgo("2026-09-26T09:00:00", now)).toBe("yesterday")
    expect(timeAgo("2026-09-23T12:00:00", now)).toBe("4 d ago")
    expect(timeAgo("2026-08-01T12:00:00", now)).toMatch(/Aug|1/)
    expect(timeAgo("2025-08-01T12:00:00", now)).toMatch(/2025/)
    expect(timeAgo("junk", now)).toBe("junk")
  })
})

describe("lateBy", () => {
  it("counts whole days past the due date, never negative", () => {
    expect(lateBy("2026-09-25", "2026-09-27")).toBe(2)
    expect(lateBy("2026-09-27", "2026-09-27")).toBe(0)
    expect(lateBy("2026-10-01", "2026-09-27")).toBe(0)
  })
})

describe("nextUp", () => {
  const t = (title: string, stage: string, due_date: string | null) => ({ title, stage, due_date })
  it("prefers the current stage, then the earliest due date, undated last", () => {
    const open = [t("later stage", "Deploy", "2026-01-01"), t("undated", "Pilot", null), t("due late", "Pilot", "2026-10-09"), t("due soon", "Pilot", "2026-09-25")]
    expect(nextUp(open, "Pilot")?.title).toBe("due soon")
    expect(nextUp([t("a", "Deploy", null), t("b", "Deploy", null)], "Pilot")?.title).toBe("a")
    expect(nextUp([], "Pilot")).toBeUndefined()
  })
})

describe("stageColumns", () => {
  it("lines the same stage up across lists and slots project-only stages where they fall", () => {
    const generic = ["PO", "Scoping", "Kickoff", "Deploy", "Closed"]
    const edr = ["PO", "Scoping", "Pilot", "Deploy", "Rollout", "Closed"]
    expect(stageColumns([generic, edr])).toEqual(["PO", "Scoping", "Pilot", "Kickoff", "Deploy", "Rollout", "Closed"])
    expect(stageColumns([generic, generic])).toEqual(generic)
    expect(stageColumns([["A", "B"], ["B", "A"]])).toEqual(["A", "B"])   // first order wins, nothing duplicated
    expect(stageColumns([])).toEqual([])
  })
})

describe("fitStages", () => {
  const edr = ["done", "done", "current", "next", "next", "next", "next", "next"] as const
  const kinds = (items: ReturnType<typeof fitStages>) => items.map((i) => i.kind === "stage" ? i.index : `${i.kind}:${i.from}-${i.to}`)
  it("keeps every stage while they fit", () => {
    expect(kinds(fitStages([...edr], 8))).toEqual([0, 1, 2, 3, 4, 5, 6, 7])
  })
  it("folds finished stages first", () => {
    expect(kinds(fitStages([...edr], 7))).toEqual(["done:0-1", 2, 3, 4, 5, 6, 7])
  })
  it("then folds far-off stages, always ending on the last stage", () => {
    expect(kinds(fitStages([...edr], 5))).toEqual(["done:0-1", 2, 3, "later:4-6", 7])
    expect(kinds(fitStages(["current", "next", "next", "next", "next", "next", "next"], 5))).toEqual([0, 1, 2, "later:3-5", 6])
  })
  it("never folds a single finished stage into a node of one", () => {
    expect(kinds(fitStages(["done", "current", "next", "next", "next"], 4))).toEqual([0, 1, "later:2-3", 4])
  })
})

describe("fmtWhen", () => {
  it("follows the workspace date format, for dates and stored UTC timestamps", () => {
    setDateFormat("yyyy-MM-dd")
    expect(fmtWhen("2026-09-27")).toBe("2026-09-27")
    setDateFormat("dd/MM/yyyy")
    expect(fmtWhen("2026-09-27")).toBe("27/09/2026")
    expect(fmtWhen("2026-09-27T12:00:00").startsWith("27/09/2026")).toBe(true)
    expect(fmtWhen("2026-09-27T12:00:00", true)).toMatch(/^27\/09\/2026, \d/)
    expect(fmtWhen(null)).toBe("—")
    setDateFormat("d MMM yyyy")
  })
})

describe("groupRows", () => {
  const r = (name: string, stage: string, client: string, state: "overdue" | "on_track") => ({ name, stage, client, owner_name: "Ann", state })
  it("keeps the worst-first order: a group sits where its first row sat", () => {
    const rows = [r("a", "Pilot", "X", "overdue"), r("b", "PO", "Y", "overdue"), r("c", "Pilot", "Y", "on_track")]
    expect(groupRows(rows, "stage").map((g) => [g.key, g.rows.map((x) => x.name)])).toEqual([["Pilot", ["a", "c"]], ["PO", ["b"]]])
    expect(groupRows(rows, "client").map((g) => g.key)).toEqual(["X", "Y"])
    expect(groupRows(rows, "owner")).toHaveLength(1)
  })
})

describe("dashboard timeline", () => {
  it("spans the earliest start to the latest target, a week past today at least", () => {
    const rows = [{ start_date: "2026-09-01", target_end_date: "2026-12-01" }, { start_date: "2026-09-20", target_end_date: "2026-01-15" }]
    const { t0, t1 } = timelineDomain(rows, "2026-09-29")
    expect(new Date(t0).toISOString().slice(0, 10)).toBe("2026-01-15")   // an overdue target sits before its start
    expect(new Date(t1).toISOString().slice(0, 10)).toBe("2026-12-01")
    const empty = timelineDomain([], "2026-09-29")
    expect(new Date(empty.t0).toISOString().slice(0, 10)).toBe("2026-09-22")
    expect(new Date(empty.t1).toISOString().slice(0, 10)).toBe("2026-10-06")
  })
  it("ticks the first of each month inside the domain", () => {
    const ticks = monthTicks(Date.UTC(2026, 8, 15), Date.UTC(2026, 11, 1))
    expect(ticks.map((t) => new Date(t.t).toISOString().slice(0, 10))).toEqual(["2026-10-01", "2026-11-01"])
    expect(monthTicks(Date.UTC(2024, 0, 1), Date.UTC(2027, 0, 1)).length).toBeLessThanOrEqual(8)
  })
})

describe("deltaText", () => {
  it("signs the change and says when there is none, or no history", () => {
    expect(deltaText(5, 3)).toBe("+2")
    expect(deltaText(3, 5)).toBe("−2")
    expect(deltaText(3, 3)).toBe("no change")
    expect(deltaText(3, null)).toBe("")
  })
})

describe("calendar grid", () => {
  it("shifts months across a year end", () => {
    expect(addMonths("2026-12", 1)).toBe("2027-01")
    expect(addMonths("2026-01", -1)).toBe("2025-12")
  })
  it("lays six Monday-first weeks over the month", () => {
    const weeks = monthGrid("2026-09")   // 1 Sep 2026 is a Tuesday
    expect(weeks).toHaveLength(6); expect(weeks[0]).toHaveLength(7)
    expect(weeks[0][0]).toBe("2026-08-31"); expect(weeks[0][1]).toBe("2026-09-01"); expect(weeks[5][6]).toBe("2026-10-11")
  })
  it("gives each span a lane and counts what no longer fits", () => {
    const week = monthGrid("2026-09")[1]   // 7–13 Sep
    const span = (id: number, from: string, to: string | null) => ({ id, name: `s${id}`, client: "c", stage: "x", start_date: from, target_end_date: to, state: "on_track" as const })
    const { segments, overflow } = laneSpans([span(1, "2026-09-01", "2026-09-30"), span(2, "2026-09-09", "2026-09-10"), span(3, "2026-09-09", null), span(4, "2026-09-20", "2026-09-25")], week, 2)
    expect(segments.map((s) => [s.id, s.startCol, s.cols, s.lane, s.startsHere, s.endsHere])).toEqual([[1, 0, 7, 0, false, false], [3, 2, 5, 1, true, false]])
    expect([...overflow]).toEqual([["2026-09-09", 1], ["2026-09-10", 1]])   // span 2 had no lane left
  })
})

describe("sign-off words", () => {
  it("names every state, and an unsent one", () => {
    expect(signoffText(null)).toBe("Not sent yet")
    expect(signoffText("signed")).toMatch(/countersignature/)
    expect(signoffText("rejected")).toMatch(/new version/)
  })
  it("turns a textarea into lines", () => {
    expect(toLines("  a \n\n b\n")).toEqual(["a", "b"])
  })
})

describe("localToday", () => {
  it("is the device's calendar day, not the UTC one", () => {
    expect(localToday(new Date(2026, 8, 30, 1, 30))).toBe("2026-09-30")
  })
})
