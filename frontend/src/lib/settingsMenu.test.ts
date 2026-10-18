import { describe, expect, it } from "vitest"
import { policyHref, searchSettings, settingsAreas, settingsHome } from "./settingsMenu"
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

describe("finding a setting by its words (B7, B14)", () => {
  const names = [
    { key: "undo_minutes", area: "security", label: "Undo window (minutes)", group: "Sessions" },
    { key: "ai_base_url", area: "ai", label: "AI server address", group: "Server" },
    { key: "ai_nightly", area: "ai_schedule", label: "Validate AI features at", group: "Schedule" },
    { key: "intake_token", area: "intake", label: "CRM intake token", group: "CRM intake" },
  ]
  it("finds a policy by its label and points at its row on its page", () => {
    const hit = searchSettings(as(["manage_settings"]), names, "undo window").policies[0]
    expect(hit.href).toBe("/settings/security#pol-undo_minutes")
    expect(hit.areaLabel).toBe("Sign-in & security")
  })
  it("puts the areas drawn inside another page on that page", () => {
    expect(policyHref(names[2])).toBe("/settings/ai#pol-ai_nightly")
    expect(policyHref(names[3])).toBe("/settings/integrations#pol-intake_token")
  })
  it("matches every word, in any order, and lists areas by name", () => {
    const r = searchSettings(as(["manage_settings"]), names, "server ai")
    expect(r.policies.map((p) => p.key)).toEqual(["ai_base_url"])
    expect(r.areas.map((a) => a.label)).toEqual([])
    expect(searchSettings(as(["manage_settings"]), names, "retention").areas.map((a) => a.href)).toEqual(["/settings/audit"])
  })
  it("shows a delegated user manager only the area they can open, never a setting", () => {
    const r = searchSettings(as(["manage_users"]), names, "users")
    expect(r.areas.map((a) => a.href)).toEqual(["/users"])
    expect(searchSettings(as(["manage_users"]), names, "undo").policies).toEqual([])
  })
  it("finds nothing for an empty box", () => {
    expect(searchSettings(as(["manage_settings"]), names, "  ")).toEqual({ areas: [], policies: [] })
  })
})
