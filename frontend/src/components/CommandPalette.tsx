import { Fragment, useEffect, useMemo, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Clock, CornerDownLeft, FileText, FolderKanban, Plus, Search, Settings2, SquareCheck, TextSearch, User as UserIcon } from "lucide-react"
import { people, search, type PersonCard, type SearchResults, type User } from "@/lib/api"
import { policyIndex } from "@/lib/policyIndex"
import { pushRecent, rolloutName, type RecentRollout } from "@/lib/recentRollouts"
import { hasWords, searchSettings, type PolicyRef } from "@/lib/settingsMenu"
import { readPref, usePref } from "@/lib/usePref"
import { cn } from "@/lib/utils"
import { Kbd } from "@/components/ui/kbd"

export type PaletteItem = { kind: "recent" | "page" | "project" | "task" | "mention" | "person" | "setting" | "action" | "all"; label: string; hint?: string; href?: string; run?: () => void }
const GROUP: Record<PaletteItem["kind"], string> = { recent: "Recent rollouts", project: "Rollouts", task: "Tasks", mention: "In notes and documents", person: "People", setting: "Settings", action: "Actions", page: "Go to", all: "" }

// Ctrl/⌘ K anywhere, or the header search button. A native <dialog> gives
// focus trapping, Escape and the backdrop for free. With the box empty it offers
// the rollouts opened last, actions and the pages; typing adds rollouts, tasks,
// words in notes, colleagues (staff) and settings (their managers), each only as
// far as this session may open it (advice B7).
export function CommandPalette({ user, pages, open, onClose, onShortcuts }: { user: User; pages: { label: string; href: string }[]; open: boolean; onClose: () => void; onShortcuts?: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [recent, setRecent] = usePref<RecentRollout[]>("recent.rollouts", [])
  const [colleagues, setColleagues] = useState<PersonCard[]>([])
  const [names, setNames] = useState<PolicyRef[]>([])
  const staff = user.kind !== "external"
  const [q, setQ] = useState("")
  const [results, setResults] = useState<SearchResults>({ projects: [], tasks: [], mentions: [] })
  const [active, setActive] = useState(0)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) { d.showModal(); setQ(""); setActive(0) }
    if (!open && d.open) d.close()
  }, [open])

  // remember a rollout once its page has named itself
  useEffect(() => {
    const m = pathname.match(/^\/projects\/(\d+)$/)
    if (!m) return
    const t = setTimeout(() => {
      const name = rolloutName(document.title)
      if (name) setRecent(pushRecent(readPref<RecentRollout[]>("recent.rollouts", []), { id: Number(m[1]), name }))
    }, 800)
    return () => clearTimeout(t)
  }, [pathname, setRecent])
  // people and setting names are fetched the first time the palette opens, then kept
  useEffect(() => {
    if (!open) return
    if (staff && user.permissions.includes("view_board")) void people().then((d) => setColleagues(d.people)).catch(() => {})
    if (user.permissions.includes("manage_settings")) void policyIndex().then(setNames)
  }, [open, staff, user.permissions])

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setResults({ projects: [], tasks: [], mentions: [] }); return }
    let live = true   // a slow answer for "ab" must not replace the one for "abc"
    const timer = setTimeout(() => { search(term).then((r) => { if (live) setResults(r) }).catch(() => {}) }, 150)
    return () => { live = false; clearTimeout(timer) }
  }, [q])

  const items: PaletteItem[] = useMemo(() => {
    const term = q.trim().toLowerCase()
    const pageItems = pages.filter((p) => !term || p.label.toLowerCase().includes(term)).map((p) => ({ kind: "page" as const, label: p.label, href: p.href }))
    const actions: PaletteItem[] = [
      ...(user.permissions.includes("create_project") && staff ? [{ kind: "action" as const, label: "New rollout", href: "/projects/new" }] : []),
      ...(staff && user.permissions.includes("view_board") ? [{ kind: "action" as const, label: "Notify someone", hint: "pick a colleague", href: "/people" }] : []),
      ...(onShortcuts ? [{ kind: "action" as const, label: "Keyboard shortcuts", hint: "?", run: onShortcuts }] : []),
    ].filter((a) => !term || hasWords(a.label, term))
    if (!term) return [...recent.map((r) => ({ kind: "recent" as const, label: r.name, href: `/projects/${r.id}` })), ...actions, ...pageItems]
    const projectItems = results.projects.map((p) => ({ kind: "project" as const, label: p.name, hint: `${p.client} · ${p.stage}`, href: `/projects/${p.id}` }))
    const taskItems = results.tasks.map((t) => ({ kind: "task" as const, label: t.title, hint: `${t.project_name}${t.done ? " · done" : ""}`, href: `/board?rollout=${t.project_id}` }))
    const where = { note: "note", risk: "RAID", scope: "scope", document: "document" } as const
    const mentionItems = (results.mentions ?? []).map((m) => ({ kind: "mention" as const, label: m.snippet, hint: `${where[m.kind]} · ${m.project_name}`, href: m.href }))
    const personItems = term.length >= 2 ? colleagues.filter((c) => hasWords(c.name, term)).slice(0, 5).map((c) => ({ kind: "person" as const, label: c.name, hint: c.role, href: `/people/${c.id}` })) : []
    const found = searchSettings(user, names, term)
    const settingItems = [...found.areas.map((a) => ({ kind: "setting" as const, label: a.label, hint: "Settings", href: a.href })),
      ...found.policies.map((p) => ({ kind: "setting" as const, label: p.label, hint: `Settings · ${p.areaLabel}`, href: p.href }))]
    const all = term.length >= 2 ? [{ kind: "all" as const, label: `Search all rollouts for “${q.trim()}”`, href: `/projects?q=${encodeURIComponent(q.trim())}` }] : []
    return [...projectItems, ...taskItems, ...mentionItems, ...personItems, ...settingItems, ...actions, ...pageItems, ...all]
  }, [q, pages, results, recent, colleagues, names, user, staff, onShortcuts])

  function go(item: PaletteItem | undefined) {
    if (!item) return
    onClose()
    if (item.run) item.run(); else if (item.href) navigate(item.href)
  }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === "Enter") { e.preventDefault(); go(items[active]) }
  }
  const icon = { recent: Clock, page: FileText, project: FolderKanban, task: SquareCheck, mention: TextSearch, person: UserIcon, setting: Settings2, action: Plus, all: Search }

  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose() }} aria-label="Search and jump"
      className="m-auto mt-[12vh] w-[min(560px,calc(100vw-32px))] rounded-xl border border-border bg-popover p-0 text-popover-foreground backdrop:bg-black/40">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="h-4 w-4 text-muted-foreground" />
        <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={onKey}
          placeholder="Search rollouts, people, settings and more, or jump to a page" aria-label="Search" role="combobox" aria-expanded={items.length > 0} aria-controls="palette-list"
          aria-activedescendant={items[active] ? `palette-${active}` : undefined}
          className="h-11 w-full bg-transparent text-[14px] outline-none placeholder:text-muted-foreground" />
        <Kbd>Esc</Kbd>
      </div>
      <ul id="palette-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
        {items.map((it, i) => {
          const Icon = icon[it.kind]
          const head = GROUP[it.kind] && (i === 0 || items[i - 1].kind !== it.kind)
          return (
            <Fragment key={`${it.kind}-${it.href ?? it.label}-${i}`}>
              {head && <li role="presentation" className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{GROUP[it.kind]}</li>}
              <li id={`palette-${i}`} role="option" aria-selected={i === active}
                onMouseEnter={() => setActive(i)} onClick={() => go(it)}
                className={cn("flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-[13px]", i === active && "bg-accent text-accent-foreground")}>
                <Icon className="h-4 w-4 shrink-0 opacity-70" />
                <span className="min-w-0 flex-1 truncate" title={it.label}>{it.label}</span>
                {/* the hint gives way to the label: at most 40% of the row */}
                {it.hint && <span className="min-w-0 max-w-[40%] truncate text-[12px] text-muted-foreground" title={it.hint}>{it.hint}</span>}
                {i === active && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 opacity-60" />}
              </li>
            </Fragment>
          )
        })}
      </ul>
      {/* outside the listbox: a listbox holds only options (review P3-48) */}
      <p role="status" className={items.length ? "sr-only" : "px-3 pb-6 pt-4 text-center text-[13px] text-muted-foreground"}>{items.length ? "" : `Nothing matches “${q}”.`}</p>
    </dialog>
  )
}
