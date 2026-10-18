import type { User } from "@/lib/api"

// Settings is one place with a side menu, grouped by what the setting is about.
// Every entry is its own address, so a link or a reload lands on the same area.
// An entry names the permission its page needs (manage_settings unless said), and
// the menu shows only what the session may open (review P3-16).
type Area = { href: string; label: string; perm?: string }
const SETTINGS_GROUPS: { label: string; items: Area[] }[] = [
  { label: "Workspace", items: [{ href: "/settings/general", label: "General" }, { href: "/settings/security", label: "Sign-in & security" }] },
  { label: "People", items: [{ href: "/users", label: "Users", perm: "manage_users" }, { href: "/settings/rbac", label: "Role permissions" },
    { href: "/settings/people", label: "Sign-up & activity" }] },
  { label: "Delivery", items: [{ href: "/settings/workflow", label: "Rollouts & workflow" }, { href: "/settings/contacts", label: "Contacts & partners", perm: "manage_contacts" },
    { href: "/settings/documents", label: "Documents" }, { href: "/settings/automations", label: "Automations", perm: "manage_rules" }] },
  { label: "Connections", items: [{ href: "/settings/notifications", label: "Notifications" }, { href: "/settings/integrations", label: "Integrations" },
    { href: "/settings/ai", label: "AI" },
    { href: "/settings/reports", label: "Reports" }, { href: "/settings/backups", label: "Backups" }, { href: "/settings/api", label: "API tokens" }] },
  { label: "Compliance", items: [{ href: "/audit-logs", label: "Audit log" }, { href: "/settings/audit", label: "Retention" },
    { href: "/settings/map", label: "System map & changes" }] },
]

export function settingsAreas(user: User) {
  return SETTINGS_GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => user.permissions.includes(i.perm ?? "manage_settings")) })).filter((g) => g.items.length > 0)
}
// where the header's Settings link goes: the first area this person may open, or nowhere
export const settingsHome = (user: User): string | null => settingsAreas(user)[0]?.items[0].href ?? null

// ---- finding a setting by its words (advice B7, B14): the side menu's filter and the palette ----
// A policy lives on the page of its area; two areas are drawn inside another's page.
const SECTION_OF: Record<string, string> = { ai_schedule: "ai", intake: "integrations" }
export type PolicyRef = { key: string; area: string; label: string; group: string }
export type PolicyHit = PolicyRef & { href: string; areaLabel: string }
// where a policy is drawn; the hash names the row, which the Settings page scrolls to and marks
export const policyHref = (p: Pick<PolicyRef, "key" | "area">) => `/settings/${SECTION_OF[p.area] ?? p.area}#pol-${p.key}`
// every word typed must be in the text, in any order
export const hasWords = (text: string, q: string) => { const t = text.toLowerCase(); return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => t.includes(w)) }

export function searchSettings(user: User, policies: PolicyRef[], q: string, limit = 8): { areas: Area[]; policies: PolicyHit[] } {
  if (!q.trim()) return { areas: [], policies: [] }
  const items = settingsAreas(user).flatMap((g) => g.items)
  const hits = user.permissions.includes("manage_settings")
    ? policies.filter((p) => hasWords(`${p.label} ${p.group}`, q)).slice(0, limit).map((p) => {
      const href = policyHref(p)
      return { ...p, href, areaLabel: items.find((i) => i.href === href.split("#")[0])?.label ?? "Settings" }
    }) : []
  return { areas: items.filter((i) => hasWords(i.label, q)), policies: hits }
}
