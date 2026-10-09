import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Bell } from "lucide-react"
import { Ago } from "@/components/Ago"
import { markRead, notifications, type Notification } from "@/lib/api"
import { cn } from "@/lib/utils"

// The bell: what happened that concerns you, whether or not mail is on.
// The count comes with the session; it refreshes every minute and on focus.
export function NotificationBell({ initialUnread }: { initialUnread: number }) {
  const [unread, setUnread] = useState(initialUnread)
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Notification[] | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const bell = useRef<HTMLButtonElement>(null)
  const navigate = useNavigate()

  const refresh = useCallback(async () => {
    try { const d = await notifications(); setUnread(d.unread); setRows(d.rows) } catch { /* offline: keep what we have */ }
  }, [])
  useEffect(() => {
    const timer = window.setInterval(refresh, 60_000)
    window.addEventListener("focus", refresh)
    return () => { window.clearInterval(timer); window.removeEventListener("focus", refresh) }
  }, [refresh])
  useEffect(() => {
    if (!open) return
    void refresh()
    function away(e: MouseEvent) { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    // Escape closes and returns to the bell; tabbing out of the popover closes it (test report UX-11)
    function esc(e: KeyboardEvent) { if (e.key === "Escape") { setOpen(false); bell.current?.focus() } }
    function left(e: FocusEvent) { if (box.current && e.target instanceof Node && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc); document.addEventListener("focusin", left)
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); document.removeEventListener("focusin", left) }
  }, [open, refresh])

  async function openOne(n: Notification) {
    if (!n.read) { try { const r = await markRead({ id: n.id }); setUnread(r.unread) } catch { /* the link still works */ } }
    setOpen(false)
    if (n.link) navigate(n.link)
  }
  async function readAll() {
    try { const r = await markRead({ all: true }); setUnread(r.unread); setRows((rs) => rs?.map((x) => ({ ...x, read: true })) ?? rs) } catch { /* retry later */ }
  }

  return (
    <div ref={box} className="relative">
      <button ref={bell} type="button" onClick={() => setOpen((v) => !v)} aria-haspopup="dialog" aria-expanded={open}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        className="relative inline-flex h-8 w-8 items-center justify-center rounded-md text-nav-fg hover:bg-muted hover:text-foreground">
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center text-[11px] font-semibold leading-4 text-primary-foreground">{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications" className="fixed inset-x-4 top-14 z-50 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-pop sm:absolute sm:inset-x-auto sm:right-0 sm:top-10 sm:w-[380px]">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-[12px] font-semibold text-nav-fg">Notifications</span>
            {unread > 0 && <button type="button" onClick={readAll} className="text-[12px] text-primary-text hover:underline">Mark all read</button>}
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {rows === null && <li className="px-3 py-6 text-center text-[13px] text-muted-foreground">Loading…</li>}
            {rows?.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-muted-foreground">Nothing yet. Stage changes, tasks for you and mentions land here.</li>}
            {rows?.map((n) => (
              <li key={n.id}>
                <button type="button" onClick={() => openOne(n)} className={cn("flex w-full gap-3 border-b border-border px-3 py-3 text-left last:border-0 hover:bg-muted", !n.read && "bg-accent/40")}>
                  <span className={cn("mt-2 h-2 w-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-primary")} aria-hidden />
                  {!n.read && <span className="sr-only">Unread: </span>}
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-[13px]", !n.read && "font-medium")}>{n.title}</span>
                    {n.body && <span className="mt-1 line-clamp-2 block text-[12px] text-muted-foreground">{n.body}</span>}
                    <span className="mt-1 block text-[12px] text-muted-foreground"><Ago iso={n.created_at} />{n.actor ? ` · ${n.actor}` : ""}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
