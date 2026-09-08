import { useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { logout, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

// The Odin nav bar: dark, uppercase tracked links, red underline on the current
// section. Un-ported pages are plain anchors (full navigation to Flask);
// React pages use <Link>. Collapses behind a menu button under md.
const REACT_PAGES = new Set(["/board"])

type Item = { href: string; label: string; count?: number; match: (path: string) => boolean }

function NavLink({ item, current, onClick }: { item: Item; current: boolean; onClick?: () => void }) {
  const className = cn(
    "label-caps inline-flex min-h-6 items-center whitespace-nowrap text-nav-fg transition-colors hover:text-secondary-foreground",
    current && "border-b-2 border-primary pb-0.5 text-secondary-foreground",
  )
  const text = (
    <>
      {item.label}
      {item.count ? ` (${item.count})` : ""}
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
  const items: Item[] = [
    { href: "/board", label: "Board", match: (p) => p === "/board" },
    { href: "/my-work", label: "My Work", count: user.nav.my_open_task_count, match: (p) => p === "/my-work" },
    { href: user.nav.projects_nav_url, label: "All Projects", match: (p) => p.startsWith("/projects") },
    { href: "/analytics", label: "Cycle Time", match: (p) => p === "/analytics" },
    { href: "/alerts", label: "Alerts", count: user.nav.active_alert_count, match: (p) => p === "/alerts" },
    ...(user.role !== "Viewer" ? [{ href: "/projects/new", label: "+ New Project", match: (p: string) => p === "/projects/new" }] : []),
    ...(user.role === "Admin" ? [{ href: "/settings", label: "Settings", match: (p: string) => p.startsWith("/settings") || p === "/audit-logs" }] : []),
  ]

  async function signOut() {
    await logout()
    window.location.assign("/login")
  }

  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground">
        Skip to content
      </a>
      <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 bg-secondary px-6 py-3 text-secondary-foreground">
        <Link to="/board" className="font-heading text-base font-bold tracking-wide">Odin</Link>
        <button
          type="button"
          aria-label="Menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="ml-auto inline-flex h-10 w-10 items-center justify-center text-xl md:hidden"
        >
          ☰
        </button>
        <div className={cn("w-full flex-col gap-3 md:flex md:w-auto md:flex-1 md:flex-row md:items-center md:gap-5", open ? "flex" : "hidden")}>
          {items.map((item) => (
            <NavLink key={item.label} item={item} current={item.match(pathname)} onClick={() => setOpen(false)} />
          ))}
          <span className="hidden md:block md:flex-1" />
          <form method="get" action="/projects" className="md:w-52">
            <input
              type="search"
              name="q"
              placeholder="Search projects…"
              aria-label="Search projects"
              className="w-full border border-nav-fg/40 bg-transparent px-2 py-1 text-sm text-secondary-foreground placeholder:text-nav-fg focus-visible:border-primary focus-visible:outline-none"
            />
          </form>
          {user.role === "Viewer" && <span className="label-caps text-nav-fg">Read-only</span>}
          <a href="/account" className="text-sm text-nav-fg hover:text-secondary-foreground">{user.name}</a>
          <button type="button" onClick={signOut} className="label-caps text-nav-fg hover:text-secondary-foreground">Logout</button>
        </div>
      </nav>
      <main id="main" tabIndex={-1} className="mx-auto max-w-[1200px] p-6 outline-none">
        {children}
      </main>
    </>
  )
}
