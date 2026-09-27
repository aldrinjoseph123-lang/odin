import { useEffect, useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { Menu, Monitor, Moon, Search, Sun } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { logout, postForm, type User } from "@/lib/api"
import { UserAvatar } from "@/components/UserAvatar"
import { CommandPalette } from "@/components/CommandPalette"
import { NotificationBell } from "@/components/NotificationBell"
import { applyTheme, type Accent, type Theme } from "@/lib/theme"
import { cn } from "@/lib/utils"

// White top bar, ink links, accent underline on the current section. Un-ported
// pages are plain anchors (full navigation to Flask); React pages use <Link>.
const REACT_PAGES = new Set(["/board", "/projects", "/users", "/audit-logs", "/settings", "/account", "/my-work", "/alerts", "/analytics"])   // header links only
type Item = { href: string; label: string; count?: number; match: (path: string) => boolean }

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

export default function AppShell({ user, children, messages = [], onDismiss }: { user: User; children: ReactNode; messages?: string[]; onDismiss?: () => void }) {
  const { pathname } = useLocation()
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
    { href: "/board", label: "Flow", match: (p) => p === "/board" },
    { href: "/my-work", label: "My work", count: user.nav.my_open_task_count, match: (p) => p === "/my-work" },
    { href: user.nav.projects_nav_url, label: "Projects", match: (p) => p.startsWith("/projects") },
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
      <header className="flex h-13 shrink-0 items-center gap-4 border-b border-border bg-background px-5 print:hidden xl:gap-6">
        <Link to="/board" className="text-[15px] font-bold tracking-tight">Odin</Link>
        {/* The full row needs ~1000 px; below lg the links fold into the menu,
            while bell, theme and avatar stay visible at every width. */}
        <nav className={cn("absolute inset-x-0 top-13 z-40 flex-col gap-3 border-b border-border bg-background px-5 py-4 lg:static lg:flex lg:flex-1 lg:flex-row lg:items-center lg:gap-4 lg:border-0 lg:p-0 xl:gap-6", open ? "flex" : "hidden")}>
          {items.map((item) => <NavLink key={item.label} item={item} current={item.match(pathname)} onClick={() => setOpen(false)} />)}
          <span className="lg:flex-1" />
          <button type="button" onClick={() => { setOpen(false); setPalette(true) }} aria-label="Search projects and tasks" aria-keyshortcuts="Control+K Meta+K /"
            className="flex h-8 w-full items-center gap-2 rounded-md border border-border bg-secondary px-2.5 text-left text-[13px] text-muted-foreground hover:border-input lg:w-40 xl:w-56">
            <Search className="h-3.5 w-3.5" /><span className="flex-1 truncate">Search…</span>
            <kbd className="rounded border border-border px-1 text-[11px]">{isMac ? "⌘K" : "Ctrl K"}</kbd>
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
        <div className="mx-5 mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-1.5 text-[12.5px] print:hidden" role="status">
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
