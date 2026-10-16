import { useEffect, useRef, useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { Menu, Monitor, Moon, Search, Sun } from "lucide-react"
import { Tag } from "@/components/ui/tag"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { buttonVariants } from "@/components/ui/button"
import { logout, postForm, type User } from "@/lib/api"
import { Logo } from "@/components/Brand"
import { UserAvatar } from "@/components/UserAvatar"
import { CommandPalette } from "@/components/CommandPalette"
import { ShortcutSheet } from "@/components/ShortcutSheet"
import { Toaster } from "@/components/Toaster"
import { ConfirmHost } from "@/components/ConfirmHost"
import { TitleTips } from "@/components/TitleTips"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { NotificationBell } from "@/components/NotificationBell"
import { cycleTheme as cycle, flushAppearance, syncAppearance, useAppearance, type Accent } from "@/lib/theme"
import { cn } from "@/lib/utils"
import { Kbd } from "@/components/ui/kbd"
import { useActivityPing } from "@/lib/useActivityPing"
import { readPref } from "@/lib/usePref"
import { settingsHome } from "@/lib/settingsMenu"

// White top bar, ink links, accent underline on the current section. Un-ported
// pages are plain anchors (full navigation to Flask); React pages use <Link>.
const REACT_PAGES = new Set(["/board", "/dashboard", "/people", "/projects", "/users", "/audit-logs", "/settings", "/settings/general", "/settings/contacts", "/account", "/my-work", "/alerts", "/analytics"])   // header links only
type Item = { href: string; label: string; count?: number; match: (path: string) => boolean }

function NavLink({ item, current, onClick }: { item: Item; current: boolean; onClick?: () => void }) {
  const className = cn(
    "inline-flex h-9 items-center gap-2 whitespace-nowrap rounded-full px-4 text-[13px] font-medium transition-colors",
    current ? "bg-primary text-primary-foreground" : "text-nav-fg hover:bg-muted hover:text-foreground",
  )
  const text = (
    <>
      {item.label}{item.count ? " " : ""}
      {item.count ? <Tag className="min-w-5 justify-center">{item.count > 99 ? "99+" : item.count}<span className="sr-only"> open</span></Tag> : null}
    </>
  )
  return REACT_PAGES.has(item.href) ? (
    <Link to={item.href} className={className} onClick={onClick} aria-current={current ? "page" : undefined}>{text}</Link>
  ) : (
    <a href={item.href} className={className} aria-current={current ? "page" : undefined}>{text}</a>
  )
}

export default function AppShell({ user, children, messages = [], onDismiss }: { user: User; children: ReactNode; messages?: string[]; onDismiss?: () => void }) {
  const { pathname, search } = useLocation()
  useActivityPing(user.prefs?.activity_idle_minutes ?? 5)
  const [open, setOpen] = useState(false)
  const navRef = useRef<HTMLElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  // the phone menu: focus moves into it, Escape closes it and returns to the button (test report UX-12)
  // a tap outside closes it, and Tab cycles inside it (the menu button included)
  useEffect(() => {
    if (!open) return
    navRef.current?.querySelector<HTMLElement>("a, button")?.focus()
    const inside = (t: EventTarget | null) => t instanceof Node && (!!navRef.current?.contains(t) || !!menuButton.current?.contains(t))
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); menuButton.current?.focus(); return }
      if (e.key !== "Tab" || !navRef.current) return
      const stops = [...navRef.current.querySelectorAll<HTMLElement>("a[href], button:not(:disabled)"), menuButton.current!].filter((el) => el && el.offsetParent !== null)
      const at = stops.indexOf(document.activeElement as HTMLElement)
      const to = e.shiftKey ? (at <= 0 ? stops.length - 1 : at - 1) : (at === stops.length - 1 || at < 0 ? 0 : at + 1)
      e.preventDefault(); stops[to]?.focus()
    }
    const onDown = (e: PointerEvent) => { if (!inside(e.target)) setOpen(false) }
    window.addEventListener("keydown", onKey)
    document.addEventListener("pointerdown", onDown)
    return () => { window.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown) }
  }, [open])
  const { theme } = useAppearance()   // one theme for the header and the Account page (review P2-33)
  const [account, setAccount] = useState(false)   // the avatar menu
  const [palette, setPalette] = useState(false)
  const [sheet, setSheet] = useState(false)   // the "?" shortcut sheet
  // Ctrl/⌘ K anywhere; "/" when not typing in a field, unless the person turned it
  // off on their Account page (WCAG 2.1.4: a single-key shortcut can be switched off)
  const slash = readPref("shortcut.slash", true)
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName))
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); setPalette(true) }
      else if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey && readPref("shortcut.slash", true)) { e.preventDefault(); setPalette(true) }
      // "?" is a single-key shortcut too, so the same switch turns it off (the avatar menu still opens the sheet)
      else if (e.key === "?" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey && readPref("shortcut.slash", true)) { e.preventDefault(); setSheet(true) }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
  // the saved choice wins over whatever this browser last painted
  useEffect(() => { syncAppearance(user.theme, user.accent as Accent) }, [user.theme, user.accent])
  function cycleTheme() {
    cycle((t, a, keepalive) => postForm("/account/appearance", { theme: t, accent: a }, keepalive))
  }
  const all: Item[] = [
    { href: "/dashboard", label: "Dashboard", match: (p) => p === "/dashboard" },
    { href: "/board", label: "Flow", match: (p) => p === "/board" },
    { href: "/my-work", label: "My work", count: user.nav.my_open_task_count, match: (p) => p === "/my-work" },
    { href: user.nav.projects_nav_url, label: "Rollouts", match: (p) => p.startsWith("/projects") },
    { href: "/people", label: "People", match: (p) => p.startsWith("/people") },
    { href: "/analytics", label: "Cycle time", match: (p) => p === "/analytics" },
    { href: "/alerts", label: "Alerts", count: user.nav.active_alert_count, match: (p) => p === "/alerts" },
    // any area of Settings this person may open (a delegated user manager lands on Users: P3-16)
    ...(settingsHome(user) ? [{ href: settingsHome(user)!, label: "Settings", match: (p: string) => p.startsWith("/settings") || p === "/audit-logs" || p === "/users" }] : []),
  ]
  // External partners get their projects and the flow — nothing product-wide.
  const items = all.filter((item) => user.kind !== "external" || ["Flow", "Rollouts"].includes(item.label))
  async function signOut() {
    await flushAppearance()   // a theme click still waiting to save
    await logout()
    window.location.assign("/login")
  }
  return (
    <div className="flex min-h-svh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground">Skip to content</a>
      {/* a roomier bar: 72 px tall, pills 36 px, the account and Log out in the avatar menu */}
      <header className="flex h-18 shrink-0 items-center gap-4 px-5 print:hidden">
        <Link to={user.home === "board" ? "/board" : "/dashboard"} aria-label="Odin, home" className="shrink-0"><Logo markClass="h-7 w-7" wordClass="h-[15px]" /></Link>
        {/* The admin's full row needs ~1,250 px (test report UX-1): below xl the
            links fold into the menu, and up to 2xl search is just its icon;
            bell, theme and avatar stay visible at every width. */}
        <nav ref={navRef} aria-label="Main" className={cn("absolute inset-x-0 top-14 z-40 mx-3 flex-col gap-3 rounded-2xl bg-card p-4 shadow-pop xl:static xl:mx-0 xl:flex xl:flex-1 xl:flex-row xl:items-center xl:gap-4 xl:rounded-none xl:bg-transparent xl:p-0 xl:shadow-none xl:gap-6", open ? "flex" : "hidden")}>
          <span className="flex flex-col gap-1 xl:flex-row xl:gap-0 xl:rounded-full xl:bg-card xl:p-1.5 xl:shadow-card">
            {items.map((item) => <NavLink key={item.label} item={item} current={item.match(pathname)} onClick={() => setOpen(false)} />)}
          </span>
          <span className="xl:flex-1" />
          <button type="button" onClick={() => { setOpen(false); setPalette(true) }} aria-label="Search rollouts and tasks" aria-keyshortcuts={slash ? "Control+K Meta+K /" : "Control+K Meta+K"}
            className="flex h-9 w-full items-center gap-2 rounded-full bg-card px-3 text-left text-[13px] text-muted-foreground shadow-card hover:text-foreground xl:w-9 xl:justify-center xl:px-0 2xl:w-56 2xl:justify-start 2xl:px-3">
            <Search className="h-3.5 w-3.5 shrink-0" /><span className="flex-1 truncate xl:hidden 2xl:inline">Search…</span>
            <Kbd className="xl:hidden 2xl:inline-flex">{isMac ? "Cmd K" : "Ctrl K"}</Kbd>
          </button>
          {user.permissions.includes("create_project") && user.kind !== "external" && <a href="/projects/new" className={buttonVariants({ size: "sm" })}>New project</a>}
          {user.role === "Viewer" && <Tag kind="role">Read-only</Tag>}
          {user.kind === "external" && <Tag kind="role">{user.external_role === "Customer" ? "Customer access" : user.external_role ? "Partner access" : "External access"}</Tag>}
          <button type="button" onClick={signOut} className="text-left text-[13px] font-medium text-nav-fg hover:text-foreground xl:hidden">Log out</button>
        </nav>
        <div className="ml-auto flex items-center gap-2 xl:ml-0 xl:gap-3">
          <NotificationBell initialUnread={user.nav.unread_notifications ?? 0} />
          <button type="button" onClick={cycleTheme} aria-label={`Theme: ${theme}. Switch`} title={`Theme: ${theme}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-nav-fg hover:bg-muted hover:text-foreground">
            {theme === "dark" ? <Moon className="h-4 w-4" /> : theme === "light" ? <Sun className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
          </button>
          <Popover open={account} onOpenChange={setAccount}>
            <PopoverTrigger render={<button type="button" />} aria-label="Your account" className="flex items-center rounded-full outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
              <UserAvatar name={user.name} url={user.avatar_url} className="h-8 w-8" textClass="text-[11px] bg-accent text-accent-foreground" />
            </PopoverTrigger>
            <PopoverContent align="end" className="w-56 gap-1 p-2 text-[13px]">
              <div className="px-2 pb-2 pt-1">
                <p className="truncate font-medium" title={user.name}>{user.name}</p>
                <p className="text-[12px] text-muted-foreground">{user.kind === "external" ? "Partner or customer" : user.role}</p>
              </div>
              <Link to="/account" onClick={() => setAccount(false)} className="rounded-md px-2 py-2 hover:bg-muted">Account settings</Link>
              <button type="button" onClick={() => { setAccount(false); setSheet(true) }} className="flex items-center justify-between rounded-md px-2 py-2 text-left hover:bg-muted">Keyboard shortcuts <Kbd>?</Kbd></button>
              <button type="button" onClick={() => { setAccount(false); void signOut() }} className="rounded-md px-2 py-2 text-left hover:bg-muted">Log out</button>
            </PopoverContent>
          </Popover>
          <button ref={menuButton} type="button" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="inline-flex h-9 w-9 items-center justify-center rounded-md text-nav-fg hover:bg-muted xl:hidden"><Menu className="h-5 w-5" /></button>
        </div>
      </header>
      {/* the live region is always there, so words put in it are announced (review P3-46) */}
      <div role="status">
        {messages.length > 0 && (
          <div className="mx-5 mt-3 flex items-center justify-between gap-3 rounded-full bg-card px-4 py-2 text-[13px] shadow-card print:hidden">
            <span>{messages.join(" ")}</span>
            <button type="button" className="font-medium" onClick={onDismiss} aria-label="Dismiss">×</button>
          </div>
        )}
      </div>
      {/* a page's error stays under the nav and clears on any change of address (?view= too) */}
      <main id="main" tabIndex={-1} className="flex min-h-0 flex-1 flex-col outline-none"><ErrorBoundary inShell resetKey={pathname + search}>{children}</ErrorBoundary></main>
      <Toaster />
      <ConfirmHost />
      <TitleTips />
      <CommandPalette user={user} open={palette} onClose={() => setPalette(false)} onShortcuts={() => setSheet(true)}
        pages={[...items.map((i) => ({ label: i.label, href: i.href })), { label: "Account", href: "/account" }]} />
      <ShortcutSheet open={sheet} onOpenChange={setSheet} />
    </div>
  )
}
