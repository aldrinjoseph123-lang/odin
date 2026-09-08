import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react"
import { ArrowRight, CalendarDays, Check, ChevronRight, Clock, ExternalLink, UserRound } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ApiError, changeStage, flow, flowDetail, type FlowData, type FlowDetail, type FlowState, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

// ---- state vocabulary: colour is a state and nothing else -------------------
const STATE: Record<FlowState, { label: string; ring: string; chip: string; dot: string }> = {
  overdue:  { label: "Overdue",   ring: "border-bad-line ring-bad-soft",   chip: "bg-bad-soft text-bad",   dot: "bg-bad-line" },
  over_sla: { label: "Over SLA",  ring: "border-warn-line ring-warn-soft", chip: "bg-warn-soft text-warn", dot: "bg-warn-line" },
  due_soon: { label: "Due soon",  ring: "border-warn-line ring-warn-soft", chip: "bg-warn-soft text-warn", dot: "bg-warn-line" },
  on_track: { label: "On track",  ring: "border-foreground ring-muted",    chip: "bg-muted text-muted-foreground", dot: "bg-ok-line" },
}

const initials = (name: string | null | undefined) => (name ?? "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()
const fmtDate = (iso: string | null | undefined) => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString([], { day: "numeric", month: "short" }) : "—")
const days = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n)} d`)

const daysLate = (target: string | null) => (target ? Math.round((Date.now() - new Date(`${target}T00:00:00`).getTime()) / 864e5) : 0)
function stateText(r: { state: FlowState; days_in_stage: number | null; over_by: number | null; target_end_date: string | null }) {
  if (r.state === "overdue") return `Overdue ${daysLate(r.target_end_date)} d`
  if (r.state === "over_sla") return `${days(r.days_in_stage)} · ${Math.round(r.over_by ?? 0)} over SLA`
  if (r.state === "due_soon") return `Due ${fmtDate(r.target_end_date)}`
  return days(r.days_in_stage)
}

// ---- the 7-dot stepper: one row's whole flow at a glance ----------------------
function Stepper({ stages, index, state, selected }: { stages: string[]; index: number; state: FlowState; selected: boolean }) {
  return (
    <div className="flex items-center" aria-label={`Stage ${index + 1} of ${stages.length}: ${stages[index]}`}>
      {stages.map((s, i) => (
        <div key={s} className="flex flex-1 items-center last:flex-none">
          <Tooltip>
            <TooltipTrigger
              render={<span />}
              className={cn(
                "block h-3 w-3 shrink-0 rounded-full border-[1.5px] bg-background",
                i < index && "border-ok-line bg-ok-line",
                i === index && cn("ring-[3px]", STATE[state].ring, selected && "scale-110"),
                i > index && "border-input",
              )}
            />
            <TooltipContent>{s}{i === index ? " · current" : i < index ? " · done" : ""}</TooltipContent>
          </Tooltip>
          {i < stages.length - 1 && <span className={cn("h-[1.5px] flex-1", i < index ? "bg-ok-line" : "bg-input")} />}
        </div>
      ))}
    </div>
  )
}

// ---- top pane: every active rollout, stuck first -------------------------------
function RolloutList({ data, selectedId, onSelect, filter, setFilter, user }: {
  data: FlowData; selectedId: number | null; onSelect: (id: number) => void
  filter: "all" | "attention" | "mine"; setFilter: (f: "all" | "attention" | "mine") => void; user: User
}) {
  const rows = useMemo(() => data.rows.filter((r) =>
    filter === "attention" ? r.state !== "on_track" : filter === "mine" ? r.owner_name === user.name : true), [data.rows, filter, user.name])
  const stuck = data.counts.overdue + data.counts.over_sla + data.counts.due_soon
  const chips: { key: typeof filter; label: string; n: number }[] = [
    { key: "all", label: "All", n: data.rows.length }, { key: "attention", label: "Needs attention", n: stuck }, { key: "mine", label: "Mine", n: data.rows.filter((r) => r.owner_name === user.name).length },
  ]
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 pb-2 pt-4">
        <h1 className="text-[17px] font-semibold tracking-tight">Active rollouts</h1>
        <p className="text-[13px] text-muted-foreground">
          {data.rows.length} active
          {data.counts.overdue ? <> · <span className="font-medium text-bad">{data.counts.overdue} overdue</span></> : null}
          {data.counts.over_sla ? <> · <span className="font-medium text-warn">{data.counts.over_sla} over SLA</span></> : null}
          {data.counts.due_soon ? <> · {data.counts.due_soon} due soon</> : null}
        </p>
        <div className="ml-auto flex gap-1.5">
          {chips.map((c) => (
            <button key={c.key} type="button" onClick={() => setFilter(c.key)} aria-pressed={filter === c.key}
              className={cn("h-7 rounded-full border px-3 text-[12.5px] font-medium transition-colors", filter === c.key ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")}>
              {c.label}{c.n ? <span className={cn("ml-1", filter === c.key ? "text-background/70" : "text-muted-foreground")}>{c.n}</span> : null}
            </button>
          ))}
        </div>
      </div>
      <div className="hidden grid-cols-[minmax(200px,1.2fr)_2fr_170px_36px] gap-4 px-5 pb-1.5 text-[11.5px] text-muted-foreground md:grid">
        <span>Rollout</span>
        <span className="flex justify-between">{data.stages.map((s) => <span key={s} className="truncate">{s}</span>)}</span>
        <span>In stage</span><span />
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <ul className="grid gap-0.5 px-3 pb-3">
          {rows.map((r) => {
            const selected = r.id === selectedId
            return (
              <li key={r.id}>
                <button type="button" onClick={() => onSelect(r.id)} aria-current={selected || undefined}
                  className={cn("grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors md:grid-cols-[minmax(200px,1.2fr)_2fr_170px_36px] md:gap-4",
                    selected ? "border-primary bg-accent" : "border-transparent hover:bg-muted focus-visible:bg-muted")}>
                  <span className="flex min-w-0 items-center gap-2">
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", r.state === "on_track" ? "bg-transparent" : STATE[r.state].dot)} aria-hidden />
                    <span className="truncate text-[13.5px] font-medium">{r.name}</span>
                    <span className="hidden truncate text-[12px] text-muted-foreground sm:inline">{r.client}</span>
                  </span>
                  <span className="col-span-2 md:col-span-1"><Stepper stages={data.stages} index={r.stage_index} state={r.state} selected={selected} /></span>
                  <span className={cn("justify-self-end whitespace-nowrap rounded-md px-2 py-0.5 text-[12px] font-medium md:justify-self-start", STATE[r.state].chip, r.state === "on_track" && "bg-transparent px-0 font-normal")}>
                    <span className="sr-only">{STATE[r.state].label}: </span>{stateText(r)}</span>
                  <Avatar className="hidden h-6 w-6 md:flex" title={r.owner_name}><AvatarFallback className="bg-secondary text-[10px] font-semibold text-nav-fg">{initials(r.owner_name)}</AvatarFallback></Avatar>
                </button>
              </li>
            )
          })}
          {rows.length === 0 && (
            <li className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-[13px] text-muted-foreground">
              {data.rows.length === 0 ? "No active rollouts yet. Create one from a client PO and it appears here." : "Nothing needs attention — every rollout is inside its stage SLA and on schedule."}
            </li>
          )}
        </ul>
      </ScrollArea>
    </div>
  )
}

// ---- bottom pane: the selected rollout as a flowchart ------------------------
function TimeStrip({ d }: { d: FlowDetail }) {
  const start = new Date(`${d.start_date}T00:00:00`).getTime()
  const today = new Date(`${d.today}T00:00:00`).getTime()
  const end = d.target_end_date ? new Date(`${d.target_end_date}T00:00:00`).getTime() : Math.max(today, start + 14 * 864e5)
  // The domain covers everything worth seeing — a target already in the past
  // sits to the left of today, which is exactly the shape of "overdue".
  const t0 = Math.min(start, end)
  const t1 = Math.max(today, end, start + 864e5)
  const span = t1 - t0 || 1
  const frac = (t: number) => Math.min(1, Math.max(0, (t - t0) / span))
  const pct = (t: number) => `${frac(t) * 100}%`
  const ticks = [{ t: start, l: fmtDate(d.start_date) }, { t: today, l: "today" }, ...(d.target_end_date ? [{ t: end, l: `target ${fmtDate(d.target_end_date)}` }] : [])]
    .sort((a, b) => a.t - b.t)
    .map((tk, i, all) => ({ ...tk, row: i > 0 && frac(tk.t) - frac(all[i - 1].t) < 0.12 ? 1 : 0 }))
  const visited = d.stages.filter((s) => s.entered_at)
  return (
    <div className="relative mt-4 h-[68px] border-t border-border">
      {ticks.map((tk) => (
        <span key={tk.l} className={cn("absolute whitespace-nowrap text-[11px]", tk.row ? "top-5" : "top-1", tk.l === "today" ? "font-semibold text-primary-text" : "text-muted-foreground")}
          style={{ left: pct(tk.t), transform: frac(tk.t) > 0.85 ? "translateX(-100%)" : frac(tk.t) < 0.1 ? "none" : "translateX(-50%)" }}>{tk.l}</span>
      ))}
      <span className="absolute top-10 h-1.5 rounded-full bg-muted" style={{ left: pct(Math.min(start, end)), width: `calc(${pct(Math.max(start, end))} - ${pct(Math.min(start, end))})` }} aria-hidden />
      {visited.map((s, i) => {
        const from = new Date(s.entered_at!).getTime()
        const to = i + 1 < visited.length ? new Date(visited[i + 1].entered_at!).getTime() : today
        const late = s.status === "current" && (d.state === "over_sla" || d.state === "overdue")
        return (
          <Tooltip key={s.name}>
            <TooltipTrigger render={<span />} className={cn("absolute top-10 h-1.5 rounded-full", late ? "bg-warn-line" : "bg-foreground")} style={{ left: pct(from), width: `calc(${pct(to)} - ${pct(from)})` }} />
            <TooltipContent>{s.name} · {days(s.days)}</TooltipContent>
          </Tooltip>
        )
      })}
      <span className="absolute top-8 h-6 w-[1.5px] bg-primary" style={{ left: pct(today) }} aria-hidden />
    </div>
  )
}

function Detail({ d, reload, onMoved }: { d: FlowDetail; reload: () => Promise<void>; onMoved: (msg: string) => void }) {
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const open = d.tasks.filter((t) => !t.done)
  const next = open[0]
  async function advance() {
    if (!d.next_stage) return
    setBusy(true); setErr(null)
    try {
      await changeStage(d.id, d.next_stage, note)
      setNote("")
      onMoved(`${d.name} moved to ${d.next_stage}`)
      await reload()
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not move the stage") } finally { setBusy(false) }
  }
  return (
    <div className="grid gap-5 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-[17px] font-semibold tracking-tight">{d.name}</h2>
            <p className="text-[12.5px] text-muted-foreground">
              {d.client}{d.vendor_name ? ` · ${d.vendor_name}` : ""}{d.product_name ? ` · ${d.product_name}` : ""}{d.outsourcer_name ? ` · via ${d.outsourcer_name}` : ""} · owner {d.owner_name}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {d.state !== "on_track" && <span className={cn("rounded-md px-2 py-1 text-[12px] font-medium", STATE[d.state].chip)}>{stateText({ state: d.state, days_in_stage: d.stages[d.stage_index]?.days ?? null, over_by: d.over_by, target_end_date: d.target_end_date })}</span>}
            <a href={`/projects/${d.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Open project <ExternalLink className="h-3.5 w-3.5" /></a>
          </div>
        </div>

        {/* the flowchart */}
        <ol className="mt-4 grid grid-cols-1 items-start gap-2 md:gap-0 md:[grid-template-columns:var(--cols)]" style={{ "--cols": `repeat(${d.stages.length}, minmax(0, 1fr))` } as CSSProperties} aria-label="Stages">
          {d.stages.map((s, i) => (
            <li key={s.name} className="relative min-w-0 md:px-1.5 md:first:pl-0 md:last:pr-0">
              {i > 0 && (
                <span className="absolute -left-2 top-[26px] hidden w-4 items-center md:flex" aria-hidden>
                  <span className={cn("h-[1.5px] flex-1", d.stages[i - 1].status === "done" ? "bg-ok-line" : "bg-input")} />
                  <ArrowRight className={cn("-ml-1.5 h-3 w-3", d.stages[i - 1].status === "done" ? "text-ok-line" : "text-input")} />
                </span>
              )}
              <div className={cn("min-h-[58px] rounded-lg border-[1.5px] bg-card px-2.5 py-2",
                s.status === "done" && "border-ok-line bg-ok-soft",
                s.status === "current" && cn("ring-[3px]", STATE[d.state].ring),
                s.status === "next" && "border-dashed border-input")}>
                <div className={cn("flex items-start gap-1 text-[12.5px] font-semibold leading-tight", s.status === "next" && "text-nav-fg")}>
                  {s.status === "done" && <Check className="mt-px h-3.5 w-3.5 shrink-0 text-ok" />}<span className="break-words line-clamp-2">{s.name}</span>
                </div>
                <div className="mt-0.5 truncate text-[11.5px] text-muted-foreground">
                  {s.status === "next" ? (s.sla_days ? `SLA ${s.sla_days} d` : "—") : s.status === "done" ? days(s.days) : `${days(s.days)}${s.sla_days ? ` · SLA ${s.sla_days}` : ""}`}
                </div>
              </div>
              {s.status === "current" && (
                <div className={cn("mt-2 text-[12.5px]", i < d.stages.length - 1 && "md:w-[calc(200%+0.75rem)]")}>
                  {open.length === 0 ? (
                    <p className="text-muted-foreground">No open tasks</p>
                  ) : (
                    <ul className="divide-y divide-border border-t border-border">
                      {open.slice(0, 4).map((t) => (
                        <li key={t.id} className="flex items-center gap-2 py-1.5">
                          <span className="h-3.5 w-3.5 shrink-0 rounded-[3px] border border-input" aria-hidden />
                          <span className="min-w-0 flex-1 break-words line-clamp-2">{t.title}</span>
                          {t.assignee && <Avatar className="h-5 w-5"><AvatarFallback className="bg-secondary text-[9px] font-semibold text-nav-fg">{initials(t.assignee)}</AvatarFallback></Avatar>}
                        </li>
                      ))}
                      {open.length > 4 && <li className="py-1.5 text-muted-foreground">+{open.length - 4} more</li>}
                    </ul>
                  )}
                  {open.length > 0 && <p className="mt-1.5 text-[11.5px] text-muted-foreground">{open.length} open before moving on</p>}
                </div>
              )}
            </li>
          ))}
        </ol>

        <TimeStrip d={d} />
      </div>

      {/* right rail: what to do next, when it's due, how we got here */}
      <aside className="grid content-start gap-4 text-[13px]">
        <section className="rounded-lg border border-border p-3">
          <h3 className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><ChevronRight className="h-3.5 w-3.5" /> Next up</h3>
          {next ? (
            <>
              <p className="font-medium">{next.title}</p>
              <p className="mt-1 flex items-center gap-3 text-muted-foreground">
                <span className="flex items-center gap-1"><UserRound className="h-3.5 w-3.5" />{next.assignee ?? "Unassigned"}</span>
                {next.due_date && <span className="flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" />{fmtDate(next.due_date)}</span>}
              </p>
            </>
          ) : <p className="text-muted-foreground">Nothing queued — add a task on the project page.</p>}
        </section>
        <section className="rounded-lg border border-border p-3">
          <h3 className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><Clock className="h-3.5 w-3.5" /> ETA</h3>
          {d.target_end_date ? (
            <p><span className="font-medium">{fmtDate(d.target_end_date)}</span>
              <span className={cn("ml-2", d.days_left != null && d.days_left < 0 ? "text-bad" : "text-muted-foreground")}>{d.days_left == null ? "" : d.days_left < 0 ? `${-d.days_left} d late` : `${d.days_left} d left`}</span></p>
          ) : <p className="text-muted-foreground">No target date set.</p>}
          <p className="mt-1 text-muted-foreground">{d.documents} document{d.documents === 1 ? "" : "s"} · {d.tasks.filter((t) => t.done).length}/{d.tasks.length} tasks done</p>
        </section>
        {d.can_move && d.next_stage && (
          <section className="rounded-lg border border-border p-3">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note for the history (optional)" aria-label="Stage change note" maxLength={5000} className="h-8 text-[13px]" />
            <Button className="mt-2 w-full" size="sm" onClick={advance} disabled={busy}>{busy ? "Moving…" : `Advance to ${d.next_stage}`} <ArrowRight className="h-3.5 w-3.5" /></Button>
            {err && <p className="mt-2 text-[12px] text-bad" role="alert">{err}</p>}
          </section>
        )}
        {d.recent_notes.length > 0 && (
          <section>
            <h3 className="mb-1.5 text-[12px] font-semibold text-nav-fg">Recent</h3>
            <ul className="grid gap-1.5">
              {d.recent_notes.map((n, i) => (
                <li key={i} className="text-[12.5px]"><span className="font-medium">{n.author}</span> <span className="text-muted-foreground">· {n.stage} · {fmtDate(n.created_at)}</span><div className="truncate text-nav-fg">{n.note}</div></li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
  )
}

export default function Flow({ user }: { user: User }) {
  const [data, setData] = useState<FlowData | null>(null)
  // ?rollout=<id> deep-links a rollout: shareable, and the URL follows selection.
  const [selectedId, setSelectedIdState] = useState<number | null>(() => {
    const q = Number(new URLSearchParams(window.location.search).get("rollout"))
    return Number.isInteger(q) && q > 0 ? q : null
  })
  const setSelectedId = useCallback((id: number | null) => {
    setSelectedIdState(id)
    const url = new URL(window.location.href)
    if (id == null) url.searchParams.delete("rollout"); else url.searchParams.set("rollout", String(id))
    window.history.replaceState(null, "", url)
  }, [])
  const [detail, setDetail] = useState<FlowDetail | null>(null)
  const [filter, setFilter] = useState<"all" | "attention" | "mine">("all")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try { setData(await flow()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load rollouts") }
  }, [])
  const loadDetail = useCallback(async (id: number) => {
    try { setDetail(await flowDetail(id)) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load the rollout") }
  }, [])
  useEffect(() => { void load() }, [load])
  useEffect(() => { if (selectedId != null) void loadDetail(selectedId) }, [selectedId, loadDetail])
  // Only after a click. On load the list must open at the top, where the
  // stuck rows are — scrolling to a deep-linked row would hide them.
  useEffect(() => { document.querySelector('main [aria-current="true"]')?.scrollIntoView({ block: "nearest" }) }, [selectedId])

  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!data) return <div className="p-5 text-[13px] text-muted-foreground">Loading rollouts…</div>

  return (
    <ResizablePanelGroup orientation="vertical" className="min-h-0 flex-1">
      <ResizablePanel defaultSize={selectedId == null ? 100 : 48} minSize={20}>
        <RolloutList data={data} selectedId={selectedId} onSelect={setSelectedId} filter={filter} setFilter={setFilter} user={user} />
      </ResizablePanel>
      {selectedId != null && (
        <>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize={52} minSize={25}>
            <ScrollArea className="h-full">
              {notice && (
                <div className="mx-5 mt-3 flex items-center justify-between rounded-md bg-ok-soft px-3 py-1.5 text-[12.5px] text-ok" role="status">
                  {notice}<button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
                </div>
              )}
              {detail && detail.id === selectedId ? (
                <Detail d={detail} reload={async () => { await Promise.all([load(), loadDetail(selectedId)]) }} onMoved={setNotice} />
              ) : <div className="p-5 text-[13px] text-muted-foreground">Loading…</div>}
            </ScrollArea>
          </ResizablePanel>
        </>
      )}
    </ResizablePanelGroup>
  )
}
