import { describe, expect, it } from "vitest"
import { filterUsers, noFilter } from "./userFilter"
import type { AdminUser } from "./api"

const u = (o: Partial<AdminUser>) => ({ id: 1, username: "x", name: "X", email: null, role: "Member", active: true, kind: "internal", review: [], ...o }) as AdminUser
const people = [
  u({ id: 1, name: "Ada Lovelace", username: "ada", email: "ada@corp.example", role: "Admin" }),
  u({ id: 2, name: "Bo Chen", username: "bo", email: "bo@corp.example", active: false }),
  u({ id: 3, name: "Cy Partner", username: "cy@acme.example", email: "cy@acme.example", role: "External", kind: "external", review: ["All their rollouts have closed"] }),
  u({ id: 4, name: "Di Quiet", username: "di", review: ["No sign-in for 90+ days"] }),
]
const ids = (f: Partial<typeof noFilter>) => filterUsers(people, { ...noFilter, ...f }).map((p) => p.id)

describe("filterUsers", () => {
  it("shows everyone with no filter", () => expect(ids({})).toEqual([1, 2, 3, 4]))
  it("matches name, username, email and role words, all of them", () => {
    expect(ids({ q: "lovelace" })).toEqual([1])
    expect(ids({ q: "acme" })).toEqual([3])
    expect(ids({ q: "corp admin" })).toEqual([1])
    expect(ids({ q: "external" })).toEqual([3])
    expect(ids({ q: "deactivated" })).toEqual([2])
  })
  it("filters by role and status", () => {
    expect(ids({ role: "External" })).toEqual([3])
    expect(ids({ role: "Member" })).toEqual([2, 4])
    expect(ids({ status: "inactive" })).toEqual([2])
    expect(ids({ status: "active", role: "Member" })).toEqual([4])
  })
  it("the access review keeps only flagged accounts", () => expect(ids({ review: true })).toEqual([3, 4]))
})
