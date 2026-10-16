import { describe, expect, it } from "vitest"
import { settingsAreas, settingsHome } from "./settingsMenu"
import type { User } from "./api"

const as = (permissions: string[]) => ({ permissions }) as User

describe("the Settings menu follows the session's permissions (P3-16)", () => {
  it("shows a settings manager only what answers them", () => {
    const hrefs = settingsAreas(as(["manage_settings"])).flatMap((g) => g.items.map((i) => i.href))
    expect(hrefs).toContain("/settings/general")
    expect(hrefs).not.toContain("/users")
    expect(hrefs).not.toContain("/settings/contacts")
  })
  it("gives a delegated user manager a way to Users, and nobody else a Settings link", () => {
    expect(settingsHome(as(["manage_users"]))).toBe("/users")
    expect(settingsHome(as(["manage_contacts"]))).toBe("/settings/contacts")
    expect(settingsHome(as(["view_board"]))).toBeNull()
  })
})
