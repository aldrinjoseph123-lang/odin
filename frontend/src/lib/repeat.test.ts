import { describe, expect, it } from "vitest"
import { existsSync, readFileSync } from "node:fs"
import { EVERY, repeatFields } from "./repeat"

// The wording of "repeats every week" lives here and, while the server keeps one,
// in its recurrence module; the repeats the server accepts are the ones drawn.
// Read the Python source (it moved from services/milestones.py to services/recurrence.py),
// so the two cannot drift apart unnoticed.
const root = new URL("../../../services/", import.meta.url)
const source = ["recurrence.py", "milestones.py"].map((f) => new URL(f, root)).filter((u) => existsSync(u)).map((u) => readFileSync(u, "utf8") as string).join("\n")
const dict = (name: string) => {
  const body = source.match(new RegExp(`^${name} = \\{([^}]*)\\}`, "m"))?.[1]
  return body === undefined ? null : [...body.matchAll(/"(\w+)":\s*([^,}]+)/g)].map(([, k, v]) => [k, v.trim().replace(/^"|"$/g, "")] as const)
}

describe("repeat wording", () => {
  it("offers exactly the repeats the server accepts", () => {
    const server = dict("RECURRENCES")
    expect(server).not.toBeNull()
    expect(Object.keys(EVERY).sort()).toEqual(server!.map(([k]) => k).sort())
  })
  it("reads the same as the server's own words, when it keeps any", () => {
    const words = dict("EVERY")
    if (words) expect(Object.fromEntries(words)).toEqual(EVERY)
  })
  it("a task that does not repeat clears both fields", () => {
    expect(repeatFields({ repeat: "", until: "2026-12-01" })).toEqual({ recurrence: null, recur_until: null })
    expect(repeatFields({ repeat: "weekly", until: "stage" })).toEqual({ recurrence: "weekly", recur_until: "stage" })
  })
})
