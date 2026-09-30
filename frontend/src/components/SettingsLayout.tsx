import type { ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import type { User } from "@/lib/api"
import { cn } from "@/lib/utils"

// Settings is one place with a side menu, grouped by what the setting is about.
// Every entry is its own address, so a link or a reload lands on the same area.
const SETTINGS_GROUPS: { label: string; items: { href: string; label: string }[] }[] = [
  { label: "Workspace", items: [{ href: "/settings/general", label: "General" }, { href: "/settings/security", label: "Sign-in & security" }] },
  { label: "People", items: [{ href: "/users", label: "Users" }, { href: "/settings/rbac", label: "Role permissions" },
    { href: "/settings/people", label: "Sign-up & activity" }] },
  { label: "Delivery", items: [{ href: "/settings/workflow", label: "Projects & workflow" }, { href: "/settings/contacts", label: "Contacts & partners" },
    { href: "/settings/documents", label: "Documents" }] },
  { label: "Connections", items: [{ href: "/settings/notifications", label: "Notifications" }, { href: "/settings/integrations", label: "Integrations" },
    { href: "/settings/reports", label: "Reports" }, { href: "/settings/backups", label: "Backups" }, { href: "/settings/api", label: "API tokens" }] },
  { label: "Compliance", items: [{ href: "/audit-logs", label: "Audit log" }, { href: "/settings/audit", label: "Retention" },
    { href: "/settings/map", label: "System map & changes" }] },
]

export function SettingsLayout({ user, children }: { user: User; children: ReactNode }) {
  const { pathname } = useLocation()
  // Only admins see the menu; someone who may read the audit log (or manage
  // users) without managing settings just gets that page.
  if (!user.permissions.includes("manage_settings")) return <>{children}</>
  return (
    <div className="flex min-w-0 flex-1 flex-col md:flex-row">
      <nav aria-label="Settings" className="shrink-0 md:w-52">
        {/* phones: one scrolling row of areas; md+: a grouped column */}
        <div className="flex gap-1 overflow-x-auto px-3 py-2 md:sticky md:top-0 md:grid md:gap-4 md:overflow-visible md:px-3 md:py-4">
          {SETTINGS_GROUPS.map((g) => (
            <div key={g.label} className="flex shrink-0 gap-1 md:grid md:gap-0.5">
              <p className="hidden px-2 pb-1 text-[11.5px] text-muted-foreground md:block">{g.label}</p>
              {g.items.map((i) => {
                const on = pathname === i.href
                return (
                  <Link key={i.href} to={i.href} aria-current={on ? "page" : undefined}
                    className={cn("whitespace-nowrap rounded-md px-2 py-1.5 text-[13px] font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      on ? "bg-accent text-accent-foreground" : "text-nav-fg hover:bg-muted hover:text-foreground")}>{i.label}</Link>
                )
              })}
            </div>
          ))}
        </div>
      </nav>
      <div className="min-w-0 flex-1 px-4 pb-4 md:pl-0 md:pt-3"><div className="panel min-h-full">{children}</div></div>
    </div>
  )
}
