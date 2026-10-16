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
    { href: "/settings/documents", label: "Documents" }] },
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
