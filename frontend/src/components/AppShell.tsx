import { useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { Menu } from "lucide-react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { logout, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

// White top bar, ink links, accent underline on the current section. Un-ported
// pages are plain anchors (full navigation to Flask); React pages use <Link>.
const REACT_PAGES = new Set(["/board", "/projects"])
type Item = { href: string; label: string; count?: number; match: (path: string) => boolean }

function initials(name: string) {
  return name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()
}

function NavLink({ item, current, onClick }: { item: Item; current: boolean; onClick?: () => void }) {
  const className = cn(
    "relative inline-flex min-h-8 items-center gap-1.5 whitespace-nowrap text-[13px] font-medium text-nav-fg transition-colors hover:text-foreground",
    current && "text-foreground after:absolute after:inset-x-0 after:-bottom-[15px] after:h-0.5 after:bg-primary",
  )
  const text = (
    <>
      {item.label}
      {item.count ? <Badge className="h-5 min-w-5 justify-center rounded-full bg-bad-soft px-1.5 text-[11px] text-bad" variant="secondary">{item.count}</Badge> : null}
    </>
  )
  return REACT_PAGES.has(item.href) ? (
    <Link to={item.href} className={className} onClick={onClick}>{text}</Link>
  ) : (
    <a href={item.href} className={className}>{text}</a>
  )
}

export default function AppShell({ user, children }: { user: User; children: ReactNode }) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const all: Item[] = [
    { href: "/board", label: "Flow", match: (p) => p === "/board" },
    { href: "/my-work", label: "My work", count: user.nav.my_open_task_count, match: (p) => p === "/my-work" },
    { href: user.nav.projects_nav_url, label: "Projects", match: (p) => p.startsWith("/projects") },
    { href: "/analytics", label: "Cycle time", match: (p) => p === "/analytics" },
    { href: "/alerts", label: "Alerts", count: user.nav.active_alert_count, match: (p) => p === "/alerts" },
    ...(user.role === "Admin" ? [{ href: "/settings", label: "Settings", match: (p: string) => p.startsWith("/settings") || p === "/audit-logs" }] : []),
  ]
  // External partners get their projects and the flow — nothing product-wide.
  const items = all.filter((item) => user.kind !== "external" || ["Flow", "Projects"].includes(item.label))
  async function signOut() {
    await logout()
    window.location.assign("/login")
  }
  return (
    <div className="flex min-h-svh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground">Skip to content</a>
      <header className="flex h-13 shrink-0 items-center gap-6 border-b border-border bg-background px-5">
        <Link to="/board" className="text-[15px] font-bold tracking-tight">Odin</Link>
        <button type="button" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-md text-nav-fg hover:bg-muted md:hidden"><Menu className="h-5 w-5" /></button>
        <nav className={cn("absolute inset-x-0 top-13 z-40 flex-col gap-3 border-b border-border bg-background px-5 py-4 md:static md:flex md:flex-1 md:flex-row md:items-center md:gap-6 md:border-0 md:p-0", open ? "flex" : "hidden")}>
          {items.map((item) => <NavLink key={item.label} item={item} current={item.match(pathname)} onClick={() => setOpen(false)} />)}
          <span className="md:flex-1" />
          <form method="get" action="/projects" className="md:w-56">
            <input type="search" name="q" placeholder="Search projects…" aria-label="Search projects" className="h-8 w-full rounded-md border border-border bg-secondary px-2.5 text-[13px] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30" />
          </form>
          {user.role !== "Viewer" && user.kind !== "external" && <a href="/projects/new" className={buttonVariants({ size: "sm" })}>New project</a>}
          {user.role === "Viewer" && <Badge variant="secondary">Read-only</Badge>}
          {user.kind === "external" && <Badge variant="secondary">Partner access</Badge>}
          <a href="/account" className="flex items-center gap-2 text-[13px] text-nav-fg hover:text-foreground" title={user.name}>
            <Avatar className="h-7 w-7"><AvatarFallback className="bg-accent text-[11px] font-semibold text-accent-foreground">{initials(user.name)}</AvatarFallback></Avatar>
          </a>
          <button type="button" onClick={signOut} className="text-[13px] font-medium text-nav-fg hover:text-foreground">Log out</button>
        </nav>
      </header>
      <main id="main" tabIndex={-1} className="flex min-h-0 flex-1 flex-col outline-none">{children}</main>
    </div>
  )
}
