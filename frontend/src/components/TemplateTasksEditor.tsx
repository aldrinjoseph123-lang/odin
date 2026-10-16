import { useEffect, useMemo, useState } from "react"
import { Plus, Trash2 } from "lucide-react"
import { PanelTitle } from "@/components/PanelTitle"
import { Notice } from "@/components/Notice"
import { LoadFailed } from "@/components/LoadFailed"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, saveTemplateTasks, templateTasks, type TemplateTask, type TemplateTaskInput } from "@/lib/api"
import { fieldAuto } from "@/lib/ui"
import { toast } from "@/lib/toast"
import { useLoad } from "@/lib/useLoad"
import { cn } from "@/lib/utils"

// "Tasks that come with this stage": what a rollout created from this
// template arrives with, per stage — a title, the project role it lands on,
// its due offset from the stage's start and at most one other task it waits
// on (services/template_tasks.py). One Save sends the whole list; rollouts
// already created keep the tasks they got.
type Row = { key: string; stage_id: number; title: string; role: string; offset: string; waits: string; hours: string }
const ROLE_LABEL: Record<string, string> = { "Project manager": "PM", Coordinator: "Coordinator", Customer: "Customer" }
const toRow = (t: TemplateTask): Row => ({ key: String(t.id), stage_id: t.stage_id, title: t.title, role: t.role ?? "", offset: String(t.offset_days), waits: t.waits_on_id ? String(t.waits_on_id) : "", hours: t.estimate_hours ? String(t.estimate_hours) : "" })
const toInput = (r: Row): TemplateTaskInput => ({ key: r.key, stage_id: r.stage_id, title: r.title.trim(), role: r.role || null, offset_days: Number(r.offset) || 0, waits_on: r.waits || null, estimate_hours: r.hours ? Number(r.hours) : null })

export function TemplateTasksEditor({ templateId, stages, label }: { templateId: number; stages: { id: number; name: string }[]; label: string }) {
  const { data, error, reload } = useLoad(`template-tasks:${templateId}`, () => templateTasks(templateId))
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [fresh, setFresh] = useState(0)
  useEffect(() => { if (data) setRows(data.tasks.map(toRow)) }, [data])
  const dirty = useMemo(() => !!data && JSON.stringify(rows.map(toInput)) !== JSON.stringify(data.tasks.map(toRow).map(toInput)), [rows, data])
  if (!data) return error ? <LoadFailed what="the template's tasks" onRetry={() => void reload()} /> : null
  const work = stages.slice(0, -1)   // the last stage is the finish line: nothing to do in it
  const set = (key: string, patch: Partial<Row>) => setRows(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  function add(stage_id: number) {
    setFresh(fresh + 1)
    setRows([...rows, { key: `new-${fresh + 1}`, stage_id, title: "", role: "", offset: "0", waits: "", hours: "" }])
  }
  // a removed task frees whatever waited on it
  const remove = (key: string) => setRows(rows.filter((r) => r.key !== key).map((r) => (r.waits === key ? { ...r, waits: "" } : r)))
  async function save() {
    setBusy(true); setProblem(null)
    try {
      const r = await saveTemplateTasks(templateId, rows.map(toInput))
      setRows(r.tasks.map(toRow))
      await reload()
      toast(`Saved ${r.tasks.length} task${r.tasks.length === 1 ? "" : "s"} for ${label}`)
    } catch (e) { setProblem(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  return (
    <form className="mt-1 border-t border-border pt-3" onSubmit={(e) => { e.preventDefault(); void save() }}>
      <PanelTitle n={false} className="mb-1" hint="new rollouts only">Tasks that come with each stage</PanelTitle>
      <p className="mb-2 text-[12px] text-muted-foreground">Due the given days after the stage starts. PM is the project manager; Coordinator and Customer are the rollout's first in that role, else unassigned.</p>
      <div className="grid grid-cols-1 gap-3">
        {work.map((s) => {
          const mine = rows.filter((r) => r.stage_id === s.id)
          return (
            <div key={s.id}>
              <h3 className="mb-1 text-[12px] font-medium text-muted-foreground">Tasks that come with {s.name}</h3>
              <ul className="grid grid-cols-1 gap-1">
                {mine.map((r) => (
                  <li key={r.key} className="flex flex-wrap items-center gap-2">
                    <Input value={r.title} onChange={(e) => set(r.key, { title: e.target.value })} placeholder="Task" aria-label={`Task title in ${s.name}`} maxLength={200} className="h-7 min-w-40 flex-1 text-[13px]" />
                    <select value={r.role} onChange={(e) => set(r.key, { role: e.target.value })} aria-label={`Who takes ${r.title || "this task"}`} className={cn(fieldAuto, "h-7 text-[12px]")}>
                      <option value="">Unassigned</option>
                      {data.roles.map((role) => <option key={role} value={role}>{ROLE_LABEL[role] ?? role}</option>)}
                    </select>
                    <span className="flex items-center gap-1 text-[12px] text-muted-foreground">day
                      <Input type="number" min={0} max={365} value={r.offset} onChange={(e) => set(r.key, { offset: e.target.value })} aria-label={`Days after the stage starts for ${r.title || "this task"}`} className="h-7 w-16 text-[12px]" />
                    </span>
                    <Input type="number" min={0.5} max={999} step={0.5} value={r.hours} onChange={(e) => set(r.key, { hours: e.target.value })} placeholder="Hours" aria-label={`Estimate hours for ${r.title || "this task"}`} className="h-7 w-20 text-[12px]" />
                    <select value={r.waits} onChange={(e) => set(r.key, { waits: e.target.value })} aria-label={`What ${r.title || "this task"} waits on`} className={cn(fieldAuto, "h-7 max-w-48 text-[12px]")}>
                      <option value="">Waits on nothing</option>
                      {rows.filter((o) => o.key !== r.key && o.title.trim()).map((o) => <option key={o.key} value={o.key}>Waits on {o.title}</option>)}
                    </select>
                    <Button type="button" variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive" onClick={() => remove(r.key)} aria-label={`Remove ${r.title || "this task"} from ${s.name}`}><Trash2 className="size-3.5" /></Button>
                  </li>
                ))}
              </ul>
              <button type="button" onClick={() => add(s.id)} aria-label={`Add a task that comes with ${s.name}`} className="mt-1 flex items-center gap-1 text-[12px] text-muted-foreground hover:text-primary-text"><Plus className="h-3 w-3" /> Task</button>
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <Button type="submit" size="sm" loading={busy} disabled={!dirty || rows.some((r) => !r.title.trim())}>Save tasks</Button>
        {dirty && <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => setRows(data.tasks.map(toRow))}>Discard</Button>}
      </div>
      {problem && <Notice bad className="mt-2">{problem}</Notice>}
    </form>
  )
}
