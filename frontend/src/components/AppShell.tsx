import { useEffect, useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { Menu, Monitor, Moon, Search, Sun } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { logout, postForm, type User } from "@/lib/api"
import { Logo } from "@/components/Brand"
import { UserAvatar } from "@/components/UserAvatar"
import { CommandPalette } from "@/components/CommandPalette"
import { NotificationBell } from "@/components/NotificationBell"
import { applyTheme, type Accent, type Theme } from "@/lib/theme"
import { cn } from "@/lib/utils"
import { useActivityPing } from "@/lib/useActivityPing"

// White top bar, ink links, accent underline on the current section. Un-ported
// pages are plain anchors (full navigation to Flask); React pages use <Link>.
const REACT_PAGES = new Set(["/board", "/dashboard", "/people", "/projects", "/users", "/audit-logs", "/settings", "/account", "/my-work", "/alerts", "/analytics"])   // header links only
type Item = { href: string; label: string; count?: number; match: (path: string) => boolean }

function NavLink({ item, current, onClick }: { item: Item; current: boolean; onClick?: () => void }) {
  const className = cn(
    "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-[13px] font-medium transition-colors",
    current ? "bg-primary text-primary-foreground" : "text-nav-fg hover:bg-muted hover:text-foreground",
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

export default function AppShell({ user, children, messages = [], onDismiss }: { user: User; children: ReactNode; messages?: string[]; onDismiss?: () => void }) {
  const { pathname } = useLocation()
  useActivityPing()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>(user.theme)
  const [palette, setPalette] = useState(false)
  // Ctrl/⌘ K anywhere; "/" when not typing in a field
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName))
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setPalette(true) }
      else if (e.key === "/" && !typing) { e.preventDefault(); setPalette(true) }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
  // the saved choice wins over whatever this browser last painted
  useEffect(() => { applyTheme(user.theme, user.accent as Accent) }, [user.theme, user.accent])
  async function cycleTheme() {
    const next: Theme = theme === "system" ? "light" : theme === "light" ? "dark" : "system"
    setTheme(next); applyTheme(next, user.accent as Accent)
    try { await postForm("/account/appearance", { theme: next, accent: user.accent }) } catch { /* stays local until the next save */ }
  }
  const all: Item[] = [
    { href: "/dashboard", label: "Dashboard", match: (p) => p === "/dashboard" },
    { href: "/board", label: "Flow", match: (p) => p === "/board" },
    { href: "/my-work", label: "My work", count: user.nav.my_open_task_count, match: (p) => p === "/my-work" },
    { href: user.nav.projects_nav_url, label: "Projects", match: (p) => p.startsWith("/projects") },
    { href: "/people", label: "People", match: (p) => p.startsWith("/people") },
    { href: "/analytics", label: "Cycle time", match: (p) => p === "/analytics" },
    { href: "/alerts", label: "Alerts", count: user.nav.active_alert_count, match: (p) => p === "/alerts" },
    ...(user.role === "Admin" ? [{ href: "/settings", label: "Settings", match: (p: string) => p.startsWith("/settings") || p === "/audit-logs" || p === "/users" }] : []),
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
      <header className="flex h-14 shrink-0 items-center gap-4 px-5 print:hidden xl:gap-6">
        <Link to={user.home === "board" ? "/board" : "/dashboard"} aria-label="Odin, home" className="shrink-0"><Logo markClass="h-7 w-7" wordClass="h-[15px]" /></Link>
        {/* The full row needs ~1000 px; below lg the links fold into the menu,
            while bell, theme and avatar stay visible at every width. */}
        <nav className={cn("absolute inset-x-0 top-14 z-40 mx-3 flex-col gap-3 rounded-2xl bg-card p-4 shadow-pop lg:static lg:mx-0 lg:flex lg:flex-1 lg:flex-row lg:items-center lg:gap-4 lg:rounded-none lg:bg-transparent lg:p-0 lg:shadow-none xl:gap-6", open ? "flex" : "hidden")}>
          <span className="flex flex-col gap-1 lg:flex-row lg:rounded-full lg:bg-card lg:p-1 lg:shadow-card">
            {items.map((item) => <NavLink key={item.label} item={item} current={item.match(pathname)} onClick={() => setOpen(false)} />)}
          </span>
          <span className="lg:flex-1" />
          <button type="button" onClick={() => { setOpen(false); setPalette(true) }} aria-label="Search projects and tasks" aria-keyshortcuts="Control+K Meta+K /"
            className="flex h-9 w-full items-center gap-2 rounded-full bg-card px-3 text-left text-[13px] text-muted-foreground shadow-card hover:text-foreground lg:w-40 xl:w-56">
            <Search className="h-3.5 w-3.5" /><span className="flex-1 truncate">Search…</span>
            <kbd className="rounded-md border border-border px-1 text-[11px]">{isMac ? "⌘K" : "Ctrl K"}</kbd>
          </button>
          {user.role !== "Viewer" && user.kind !== "external" && <a href="/projects/new" className={buttonVariants({ size: "sm" })}>New project</a>}
          {user.role === "Viewer" && <Badge variant="secondary">Read-only</Badge>}
          {user.kind === "external" && <Badge variant="secondary">Partner access</Badge>}
          <button type="button" onClick={signOut} className="text-left text-[13px] font-medium text-nav-fg hover:text-foreground lg:hidden">Log out</button>
        </nav>
        <div className="ml-auto flex items-center gap-1.5 lg:ml-0 xl:gap-3">
          <NotificationBell initialUnread={user.nav.unread_notifications ?? 0} />
          <button type="button" onClick={cycleTheme} aria-label={`Theme: ${theme}. Switch`} title={`Theme: ${theme}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-nav-fg hover:bg-muted hover:text-foreground">
            {theme === "dark" ? <Moon className="h-4 w-4" /> : theme === "light" ? <Sun className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
          </button>
          <a href="/account" className="flex items-center text-[13px] text-nav-fg hover:text-foreground" title={user.name} aria-label="Your account">
            <UserAvatar name={user.name} url={user.avatar_url} className="h-7 w-7" textClass="text-[11px] bg-accent text-accent-foreground" />
          </a>
          <button type="button" onClick={signOut} className="hidden text-[13px] font-medium text-nav-fg hover:text-foreground lg:ml-1.5 lg:inline">Log out</button>
          <button type="button" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="inline-flex h-9 w-9 items-center justify-center rounded-md text-nav-fg hover:bg-muted lg:hidden"><Menu className="h-5 w-5" /></button>
        </div>
      </header>
      {messages.length > 0 && (
        <div className="mx-5 mt-3 flex items-center justify-between gap-3 rounded-full bg-card px-4 py-2 text-[12.5px] shadow-card print:hidden" role="status">
          <span>{messages.join(" ")}</span>
          <button type="button" className="font-medium" onClick={onDismiss} aria-label="Dismiss">×</button>
        </div>
      )}
      <main id="main" tabIndex={-1} className="flex min-h-0 flex-1 flex-col outline-none">{children}</main>
      <CommandPalette open={palette} onClose={() => setPalette(false)}
        pages={[...items.map((i) => ({ label: i.label, href: i.href })), { label: "Account", href: "/account" },
          ...(user.role !== "Viewer" && user.kind !== "external" ? [{ label: "New project", href: "/projects/new" }] : [])]} />
    </div>
  )
}
