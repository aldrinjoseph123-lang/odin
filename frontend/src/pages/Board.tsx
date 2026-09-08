import { useCallback, useEffect, useState } from "react"
import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ApiError, board, changeStage, dismissAlert, type BoardData, type Card as CardData } from "@/lib/api"
import { localDateTime } from "@/lib/format"
import { cn } from "@/lib/utils"

// Alert banner order and tone. Mirrors the Jinja board: names are capped at
// banner_names per type with a "+N more" into the alert log.
const ALERT_ROWS: { key: string; tone: string; label: string }[] = [
  { key: "project_overdue", tone: "bg-danger-bg text-danger border-danger-border", label: "project(s) overdue" },
  { key: "project_due_soon", tone: "bg-warn-bg text-warn border-warn-border", label: "project(s) due soon" },
  { key: "stage_sla_breach", tone: "bg-warn-bg text-warn border-warn-border", label: "project(s) over their stage SLA" },
  { key: "stale", tone: "bg-muted text-foreground border-border", label: "project(s) untouched for a while" },
]

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <h2 className="label-caps mb-2 mt-4 text-muted-foreground">
      {children}
      {hint && <span className="ml-1 font-normal normal-case tracking-normal">({hint})</span>}
    </h2>
  )
}

function StatTile({ href, label, value, tone }: { href: string; label: string; value: number; tone?: string }) {
  return (
    <a href={href} className="block border border-border bg-card p-4 transition-colors hover:border-foreground">
      <div className="label-caps text-[11px] text-muted-foreground">{label}</div>
      <div className={cn("font-heading mt-1 text-3xl font-bold tabular-nums", tone)}>{value}</div>
    </a>
  )
}

function DraggableCard({ card, canMove }: { card: CardData; canMove: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: card.id, data: { stage: card.stage }, disabled: !canMove })
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={cn("relative border border-border bg-card p-2 text-sm transition-shadow", canMove && "cursor-grab", isDragging && "z-10 shadow-md")}
    >
      {/* The title is a real link stretched over the card: mouse users click
          anywhere, keyboard users get one proper anchor. */}
      <div className="font-semibold">
        <a href={`/projects/${card.id}`} className="after:absolute after:inset-0 hover:underline">{card.name}</a>
      </div>
      <div className="text-xs text-muted-foreground">{card.client}</div>
      <div className="text-xs text-muted-foreground">
        {card.owner_name}{card.delivery_mode === "Outsourced" ? " · Outsourced" : ""}
      </div>
      {card.task_total > 0 && (
        <div className="text-xs text-muted-foreground">
          {card.task_done === card.task_total ? "☑" : "☐"} {card.task_done}/{card.task_total} tasks
        </div>
      )}
    </div>
  )
}

function Column({ stage, cards, cap, canMove }: { stage: string; cards: CardData[]; cap: number; canMove: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage, disabled: !canMove })
  return (
    <div ref={setNodeRef} className={cn("flex min-w-[220px] flex-1 flex-col bg-muted p-2 transition-colors", isOver && "bg-warn-bg")}>
      <h2 className="label-caps mb-2 flex justify-between text-muted-foreground">
        {stage} <span className="tabular-nums">{cards.length}</span>
      </h2>
      <div className="flex flex-col gap-2">
        {cards.slice(0, cap).map((card) => <DraggableCard key={card.id} card={card} canMove={canMove} />)}
        {cards.length > cap && (
          <a href={`/projects?stage=${encodeURIComponent(stage)}`} className="label-caps block border border-dashed border-border bg-card p-2 text-center text-primary-text hover:border-primary">
            +{cards.length - cap} more in {stage} →
          </a>
        )}
      </div>
    </div>
  )
}

export default function Board() {
  const [data, setData] = useState<BoardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  const load = useCallback(async () => {
    try {
      setData(await board())
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the board")
    }
  }, [])
  useEffect(() => { void load() }, [load])

  async function onDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (!data || !over || !data.can_move) return
    const from = active.data.current?.stage as string
    const to = String(over.id)
    if (from === to) return
    try {
      await changeStage(Number(active.id), to)
      setNotice(`Moved to ${to}`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Stage change failed")
    }
  }

  async function dismiss(projectId: number, type: string) {
    await dismissAlert(projectId, type)
    await load()
  }

  if (error) return <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>
  if (!data) return <p className="text-muted-foreground">Loading…</p>

  const { dashboard, stages, terminal, delivery_modes: modes } = data
  const active = stages.filter((s) => s !== terminal)
  const dmTotal = modes.reduce((n, m) => n + (dashboard.delivery_counts[m] ?? 0), 0)
  const hasAlerts = ALERT_ROWS.some((r) => data.alerts[r.key]?.length)

  return (
    <>
      <h1 className="font-heading mb-4 text-2xl font-bold tracking-tight">Board</h1>
      {notice && (
        <Alert className="mb-4" role="status">
          <AlertDescription className="flex items-center justify-between">
            {notice}
            <Button variant="ghost" size="sm" onClick={() => setNotice(null)} aria-label="Dismiss">×</Button>
          </AlertDescription>
        </Alert>
      )}

      {hasAlerts && (
        <div className="mb-4 flex flex-col gap-2" id="alerts">
          {ALERT_ROWS.map(({ key, tone, label }) => {
            const items = data.alerts[key] ?? []
            if (!items.length) return null
            return (
              <div key={key} className={cn("border px-4 py-2 text-sm", tone)}>
                <strong>{items.length} {label}:</strong>{" "}
                {items.slice(0, data.banner_names).map((p, i) => (
                  <span key={p.id} className="whitespace-nowrap">
                    <a href={`/projects/${p.id}`} className="font-semibold underline">{p.name}</a>
                    <button type="button" onClick={() => dismiss(p.id, key)} className="px-2 font-bold opacity-60 hover:opacity-100" title="Dismiss" aria-label={`Dismiss ${p.name}`}>×</button>
                    {i < Math.min(items.length, data.banner_names) - 1 ? ", " : ""}
                  </span>
                ))}
                {items.length > data.banner_names && (
                  <a href={`/alerts?type=${key}`} className="ml-2 whitespace-nowrap font-semibold underline">+{items.length - data.banner_names} more →</a>
                )}
              </div>
            )
          })}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile href="/projects" label="Active Projects" value={dashboard.total_active} />
        <StatTile href="/projects?view=overdue" label="Overdue" value={data.real_alerts.project_overdue ?? 0} tone="text-primary-text" />
        <StatTile href="/projects?view=at_risk" label="Due Soon" value={data.real_alerts.project_due_soon ?? 0} tone="text-warn" />
        <StatTile href="/projects?view=stale" label="Stale Projects" value={data.real_alerts.stale ?? 0} tone="text-warn" />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card><CardContent className="pt-4">
          <SectionTitle hint="active pipeline">Projects by Stage</SectionTitle>
          <div className="flex flex-col gap-1.5">
            {active.map((stage) => {
              const n = dashboard.stage_counts[stage] ?? 0
              const w = dashboard.max_stage_count ? (n / dashboard.max_stage_count) * 100 : 0
              return (
                <a key={stage} href={`/projects?stage=${encodeURIComponent(stage)}`} className="grid grid-cols-[110px_1fr_28px] items-center gap-2 text-xs hover:underline" title={`View ${stage} projects`}>
                  <span className="text-right text-muted-foreground">{stage}</span>
                  <span className="h-3 bg-muted"><span className="block h-full bg-foreground" style={{ width: `${w}%` }} /></span>
                  <span className="text-right font-semibold tabular-nums">{n}</span>
                </a>
              )
            })}
          </div>
        </CardContent></Card>

        <Card><CardContent className="pt-4">
          <SectionTitle>Delivery Mode</SectionTitle>
          <div className="flex h-7 overflow-hidden">
            {modes.map((m, i) => {
              const n = dashboard.delivery_counts[m] ?? 0
              return (
                <a key={m} href={`/projects?delivery_mode=${encodeURIComponent(m)}`} title={`View ${m} projects`}
                  className={cn("flex items-center justify-center text-xs font-bold text-white", i === 0 ? "bg-chart-1" : "bg-chart-2")}
                  style={{ width: `${dmTotal ? (n / dmTotal) * 100 : 0}%` }}>{n || ""}</a>
              )
            })}
          </div>
          <div className="mt-2 flex gap-4 text-xs">
            {modes.map((m, i) => (
              <a key={m} href={`/projects?delivery_mode=${encodeURIComponent(m)}`} className="inline-flex items-center gap-1.5 hover:underline">
                <span className={cn("inline-block h-2.5 w-2.5", i === 0 ? "bg-chart-1" : "bg-chart-2")} />{m} ({dashboard.delivery_counts[m] ?? 0})
              </a>
            ))}
          </div>
        </CardContent></Card>
      </div>

      <Card className="mt-4"><CardContent className="pt-4">
        <SectionTitle>Recent Activity</SectionTitle>
        {data.recent_notes.length === 0 ? <p className="text-sm text-muted-foreground">No activity yet.</p> : (
          <div className="flex flex-col gap-2">
            {data.recent_notes.map((n) => (
              <div key={n.id} className="border border-border bg-muted/40 p-2 text-sm">
                <div className="label-caps text-[11px] text-muted-foreground">
                  <strong className="text-foreground">{n.author}</strong> · <a href={`/projects/${n.project_id}`} className="hover:underline">{n.project_name}</a> · {n.stage} · <time dateTime={`${n.created_at}Z`}>{localDateTime(n.created_at)}</time>
                </div>
                <div className="mt-0.5 break-words">{n.note}</div>
              </div>
            ))}
          </div>
        )}
      </CardContent></Card>

      <h1 className="font-heading mb-3 mt-6 text-2xl font-bold tracking-tight">Pipeline</h1>
      {dashboard.total_active === 0 ? (
        <Card><CardContent className="py-8 text-center">
          <p className="mb-4 text-muted-foreground">No active projects yet. The pipeline fills up as projects move through the stages.</p>
          {data.can_move && <a href="/projects/new" className={buttonVariants()}>Create your first project</a>}
        </CardContent></Card>
      ) : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {stages.map((stage) => (
              <Column key={stage} stage={stage} cards={data.columns[stage] ?? []} cap={data.column_cards} canMove={data.can_move} />
            ))}
          </div>
        </DndContext>
      )}
      {!data.can_move && <p className="mt-2 text-xs text-muted-foreground"><Badge variant="secondary">Read-only</Badge> Drag-and-drop is disabled for your role.</p>}
    </>
  )
}
