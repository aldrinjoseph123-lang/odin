import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { CornerDownLeft, FileText, FolderKanban, Search, SquareCheck, TextSearch } from "lucide-react"
import { search, type SearchResults } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Kbd } from "@/components/ui/kbd"

export type PaletteItem = { kind: "page" | "project" | "task" | "mention" | "all"; label: string; hint?: string; href: string }

// Ctrl/⌘ K anywhere, or the header search button. A native <dialog> gives
// focus trapping, Escape and the backdrop for free.
export function CommandPalette({ pages, open, onClose }: { pages: { label: string; href: string }[]; open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const navigate = useNavigate()
  const [q, setQ] = useState("")
  const [results, setResults] = useState<SearchResults>({ projects: [], tasks: [], mentions: [] })
  const [active, setActive] = useState(0)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) { d.showModal(); setQ(""); setActive(0) }
    if (!open && d.open) d.close()
  }, [open])

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
    const projectItems = results.projects.map((p) => ({ kind: "project" as const, label: p.name, hint: `${p.client} · ${p.stage}`, href: `/projects/${p.id}` }))
    const taskItems = results.tasks.map((t) => ({ kind: "task" as const, label: t.title, hint: `${t.project_name}${t.done ? " · done" : ""}`, href: `/board?rollout=${t.project_id}` }))
    const where = { note: "note", risk: "RAID", scope: "scope", document: "document" } as const
    const mentionItems = (results.mentions ?? []).map((m) => ({ kind: "mention" as const, label: m.snippet, hint: `${where[m.kind]} · ${m.project_name}`, href: m.href }))
    const all = term.length >= 2 ? [{ kind: "all" as const, label: `Search all rollouts for “${q.trim()}”`, href: `/projects?q=${encodeURIComponent(q.trim())}` }] : []
    return [...projectItems, ...taskItems, ...mentionItems, ...pageItems, ...all]
  }, [q, pages, results])

  function go(item: PaletteItem | undefined) {
    if (!item) return
    onClose()
    navigate(item.href)
  }
  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === "Enter") { e.preventDefault(); go(items[active]) }
  }
  const icon = { page: FileText, project: FolderKanban, task: SquareCheck, mention: TextSearch, all: Search }

  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose() }} aria-label="Search and jump"
      className="m-auto mt-[12vh] w-[min(560px,calc(100vw-32px))] rounded-xl border border-border bg-popover p-0 text-popover-foreground backdrop:bg-black/40">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="h-4 w-4 text-muted-foreground" />
        <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={onKey}
          placeholder="Search rollouts, tasks, notes and documents, or jump to a page" aria-label="Search" role="combobox" aria-expanded={items.length > 0} aria-controls="palette-list"
          aria-activedescendant={items[active] ? `palette-${active}` : undefined}
          className="h-11 w-full bg-transparent text-[14px] outline-none placeholder:text-muted-foreground" />
        <Kbd>Esc</Kbd>
      </div>
      <ul id="palette-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
        {items.map((it, i) => {
          const Icon = icon[it.kind]
          return (
            <li key={`${it.kind}-${it.href}-${i}`} id={`palette-${i}`} role="option" aria-selected={i === active}
              onMouseEnter={() => setActive(i)} onClick={() => go(it)}
              className={cn("flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-[13px]", i === active && "bg-accent text-accent-foreground")}>
              <Icon className="h-4 w-4 shrink-0 opacity-70" />
              <span className="min-w-0 flex-1 truncate" title={it.label}>{it.label}</span>
              {/* the hint gives way to the label: at most 40% of the row */}
              {it.hint && <span className="min-w-0 max-w-[40%] truncate text-[12px] text-muted-foreground" title={it.hint}>{it.hint}</span>}
              {i === active && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 opacity-60" />}
            </li>
          )
        })}
      </ul>
      {/* outside the listbox: a listbox holds only options (review P3-48) */}
      <p role="status" className={items.length ? "sr-only" : "px-3 pb-6 pt-4 text-center text-[13px] text-muted-foreground"}>{items.length ? "" : `Nothing matches “${q}”.`}</p>
    </dialog>
  )
}
