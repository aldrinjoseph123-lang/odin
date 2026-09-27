import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { CornerDownLeft, FileText, FolderKanban, Search, SquareCheck } from "lucide-react"
import { search, type SearchResults } from "@/lib/api"
import { cn } from "@/lib/utils"

export type PaletteItem = { kind: "page" | "project" | "task" | "all"; label: string; hint?: string; href: string }

// Ctrl/⌘ K anywhere, or the header search button. A native <dialog> gives
// focus trapping, Escape and the backdrop for free.
export function CommandPalette({ pages, open, onClose }: { pages: { label: string; href: string }[]; open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const navigate = useNavigate()
  const [q, setQ] = useState("")
  const [results, setResults] = useState<SearchResults>({ projects: [], tasks: [] })
  const [active, setActive] = useState(0)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) { d.showModal(); setQ(""); setActive(0) }
    if (!open && d.open) d.close()
  }, [open])

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setResults({ projects: [], tasks: [] }); return }
    const timer = setTimeout(() => { search(term).then(setResults).catch(() => {}) }, 150)
    return () => clearTimeout(timer)
  }, [q])

  const items: PaletteItem[] = useMemo(() => {
    const term = q.trim().toLowerCase()
    const pageItems = pages.filter((p) => !term || p.label.toLowerCase().includes(term)).map((p) => ({ kind: "page" as const, label: p.label, href: p.href }))
    const projectItems = results.projects.map((p) => ({ kind: "project" as const, label: p.name, hint: `${p.client} · ${p.stage}`, href: `/projects/${p.id}` }))
    const taskItems = results.tasks.map((t) => ({ kind: "task" as const, label: t.title, hint: `${t.project_name}${t.done ? " · done" : ""}`, href: `/board?rollout=${t.project_id}` }))
    const all = term.length >= 2 ? [{ kind: "all" as const, label: `Search all projects for “${q.trim()}”`, href: `/projects?q=${encodeURIComponent(q.trim())}` }] : []
    return [...projectItems, ...taskItems, ...pageItems, ...all]
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
  const icon = { page: FileText, project: FolderKanban, task: SquareCheck, all: Search }

  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose() }} aria-label="Search and jump"
      className="m-auto mt-[12vh] w-[min(560px,calc(100vw-32px))] rounded-xl border border-border bg-popover p-0 text-popover-foreground shadow-2xl backdrop:bg-black/40">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="h-4 w-4 text-muted-foreground" />
        <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={onKey}
          placeholder="Search projects and tasks, or jump to a page" aria-label="Search" role="combobox" aria-expanded aria-controls="palette-list"
          aria-activedescendant={items[active] ? `palette-${active}` : undefined}
          className="h-11 w-full bg-transparent text-[14px] outline-none placeholder:text-muted-foreground" />
        <kbd className="rounded border border-border px-1.5 text-[11px] text-muted-foreground">Esc</kbd>
      </div>
      <ul id="palette-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-1.5">
        {items.map((it, i) => {
          const Icon = icon[it.kind]
          return (
            <li key={`${it.kind}-${it.href}-${i}`} id={`palette-${i}`} role="option" aria-selected={i === active}
              onMouseEnter={() => setActive(i)} onClick={() => go(it)}
              className={cn("flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px]", i === active && "bg-accent text-accent-foreground")}>
              <Icon className="h-4 w-4 shrink-0 opacity-70" />
              <span className="min-w-0 flex-1 truncate">{it.label}</span>
              {it.hint && <span className="shrink-0 truncate text-[12px] text-muted-foreground">{it.hint}</span>}
              {i === active && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 opacity-60" />}
            </li>
          )
        })}
        {items.length === 0 && <li className="px-3 py-6 text-center text-[13px] text-muted-foreground">Nothing matches “{q}”.</li>}
      </ul>
    </dialog>
  )
}
