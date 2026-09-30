import { describe, expect, it } from "vitest"
import { configure, keyOf, move, newUid, pctChange, remove, reorder, resize, splitWindow, type LayoutItem, pack } from "./dashboard"

const L: LayoutItem[] = [{ id: "a", w: 3, settings: {} }, { id: "b", w: 1, settings: { limit: 5 } }, { id: "c", w: 2, settings: {} }]
const ids = (l: LayoutItem[]) => l.map((x) => x.id).join("")

describe("layout edits", () => {
  it("moves a widget one step and stops at the ends", () => {
    expect(ids(move(L, "b", -1))).toBe("bac")
    expect(ids(move(L, "a", -1))).toBe("abc")
    expect(ids(move(L, "c", 1))).toBe("abc")
  })
  it("drops the dragged widget before the target, or at the end", () => {
    expect(ids(reorder(L, "c", "a"))).toBe("cab")
    expect(ids(reorder(L, "a", null))).toBe("bca")
    expect(ids(reorder(L, "a", "a"))).toBe("abc")
  })
  it("tells repeated widgets apart by their handle", () => {
    const L2: LayoutItem[] = [{ id: "custom", uid: "x1", w: 1, settings: {} }, { id: "custom", uid: "x2", w: 1, settings: {} }, { id: "kpis", w: 3, settings: {} }]
    expect(L2.map(keyOf)).toEqual(["x1", "x2", "kpis"])
    expect(remove(L2, "x1").map(keyOf)).toEqual(["x2", "kpis"])
    expect(resize(L2, "x2", 2)[1].w).toBe(2); expect(resize(L2, "x2", 2)[0].w).toBe(1)
    expect(newUid()).toMatch(/^c[a-z0-9]{6,}$/); expect(newUid()).not.toBe(newUid())
  })
  it("resizes, removes and configures without touching the others", () => {
    expect(resize(L, "b", 3)[1].w).toBe(3)
    expect(ids(remove(L, "b"))).toBe("ac")
    expect(configure(L, "b", { limit: 9 })[1].settings).toEqual({ limit: 9 })
    expect(configure(L, "b", { limit: 9 })[0]).toBe(L[0])
  })
})

describe("week-over-week", () => {
  it("gives a signed percentage, or nothing when there is no base", () => {
    expect(pctChange(12, 10)).toBe("+20%")
    expect(pctChange(8, 10)).toBe("-20%")
    expect(pctChange(10, 10)).toBe("0%")
    expect(pctChange(3, 0)).toBeNull()
    expect(pctChange(0, 0)).toBe("0%")
  })
  it("splits a series into this window and the one before", () => {
    expect(splitWindow([1, 2, 3, 4, 5, 6, 7, 8], 3)).toEqual({ now: [6, 7, 8], before: [3, 4, 5] })
  })
})

describe("pack: rows without holes", () => {
  const L = (...ws: number[]) => ws.map((w, i) => ({ id: `w${i}`, w: w as 1 | 2 | 3, settings: {} }))
  const shape = (ws: number[], cols: number) => pack(L(...ws), cols).map((x) => `${x.item.id}:${x.span}`)
  it("stretches the last widget of a short row", () => {
    expect(shape([1, 1], 3)).toEqual(["w0:1", "w1:2"])
    expect(shape([2], 3)).toEqual(["w0:3"])
  })
  it("pulls up a later widget that fits a gap", () => {
    expect(shape([2, 3, 1], 3)).toEqual(["w0:2", "w2:1", "w1:3"])   // the ⅓ fills the ⅔ row; the full one follows
  })
  it("adapts to two columns and to phones", () => {
    expect(shape([1, 2, 1], 2)).toEqual(["w0:1", "w2:1", "w1:2"])
    expect(shape([3, 1, 2], 1)).toEqual(["w0:1", "w1:1", "w2:1"])
  })
  it("every row is full", () => {
    for (const cols of [1, 2, 3]) {
      const spans = pack(L(1, 3, 2, 1, 1, 2, 1), cols).map((x) => x.span)
      let used = 0
      for (const s of spans) { used += s; if (used > cols) throw new Error("overflow"); if (used === cols) used = 0 }
      expect(used).toBe(0)
    }
  })
})
