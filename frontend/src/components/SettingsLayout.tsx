import { useMemo, useState, type ReactNode } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import type { User } from "@/lib/api"
import { Input } from "@/components/ui/input"
import { policyIndex } from "@/lib/policyIndex"
import { searchSettings, settingsAreas, type PolicyRef } from "@/lib/settingsMenu"
import { cn } from "@/lib/utils"

export function SettingsLayout({ user, children }: { user: User; children: ReactNode }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const groups = settingsAreas(user)
  // the filter (advice B14): areas by name and, for a settings manager, every setting by its label
  const [q, setQ] = useState("")
  const [names, setNames] = useState<PolicyRef[]>([])
  const found = useMemo(() => searchSettings(user, names, q), [user, names, q])
  const firstHit = found.areas[0]?.href ?? found.policies[0]?.href
  // one area is a page, not a menu
  if (groups.flatMap((g) => g.items).length < 2) return <>{children}</>
  return (
    <div className="flex min-w-0 flex-1 flex-col md:flex-row">
      <nav aria-label="Settings" className="shrink-0 md:w-52">
        {/* phones: one scrolling row of areas; md+: a grouped column */}
        <div className="flex gap-1 overflow-x-auto px-3 py-2 md:sticky md:top-0 md:grid md:gap-4 md:overflow-visible md:px-3 md:py-4">
          <Input type="search" value={q} aria-label="Filter settings" placeholder="Filter settings" className="hidden h-8 text-[13px] md:block"
            onFocus={() => { if (user.permissions.includes("manage_settings")) void policyIndex().then(setNames) }}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && q) { e.stopPropagation(); setQ("") }
              else if (e.key === "Enter" && firstHit) { e.preventDefault(); setQ(""); navigate(firstHit) }
            }} />
          {q.trim() ? (
            <div className="grid gap-1" aria-live="polite">
              {[...found.areas.map((a) => ({ href: a.href, label: a.label, hint: "" })), ...found.policies.map((p) => ({ href: p.href, label: p.label, hint: p.areaLabel }))].map((r) => (
                <Link key={r.href} to={r.href} onClick={() => setQ("")} className="rounded-lg px-3 py-2 text-[13px] font-medium text-nav-fg outline-none hover:bg-card/60 hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50">
                  {r.label}{r.hint && <span className="block text-[12px] font-normal text-muted-foreground">{r.hint}</span>}
                </Link>
              ))}
              {!firstHit && <p className="px-3 py-2 text-[13px] text-muted-foreground">No setting matches “{q.trim()}”.</p>}
            </div>
          ) : groups.map((g) => (
            <div key={g.label} className="flex shrink-0 gap-1 md:grid md:gap-1">
              <p className="hidden px-2 pb-1 text-[12px] text-muted-foreground md:block">{g.label}</p>
              {g.items.map((i) => {
                const on = pathname === i.href
                return (
                  <Link key={i.href} to={i.href} aria-current={on ? "page" : undefined}
                    // the open area reads at a glance: a card-coloured block with
                    // the accent bar on its left, bold ink text
                    className={cn("relative whitespace-nowrap rounded-lg px-3 py-2 text-[13px] font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      on ? "bg-card font-semibold text-foreground shadow-card before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-full before:bg-primary-text md:before:block before:hidden"
                        : "text-nav-fg hover:bg-card/60 hover:text-foreground")}>{i.label}</Link>
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
