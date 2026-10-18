import { useState, type FormEvent } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { DatePicker } from "@/components/DatePicker"
import { addTask, type WorkProject } from "@/lib/api"
import { fieldAuto } from "@/lib/ui"
import { toast } from "@/lib/toast"
import { useAction } from "@/lib/useAction"

// My work: a task on one of my rollouts without opening it. The task lands on
// the rollout's current stage, assigned to me, through the project page's own
// add route (so its permission, audit row and notification apply).
export function QuickAddTask({ projects, me, preferred, onAdded }: {
  projects: (WorkProject & { can_add_task: boolean })[]; me: number; preferred?: number | null; onAdded: () => void
}) {
  const open = projects.filter((p) => p.can_add_task)
  const [pick, setPick] = useState<number | null>(null)
  const [title, setTitle] = useState("")
  const [due, setDue] = useState("")
  const { busy, act } = useAction(undefined, { quiet: true })
  if (open.length === 0) return null
  const rollout = open.find((p) => p.id === (pick ?? preferred)) ?? open[0]
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy || !title.trim()) return
    const ok = await act(() => addTask(rollout.id, { title: title.trim(), stage: rollout.stage, assignee_id: me, due_date: due || null }))
    if (!ok) return
    toast(`Added to ${rollout.name}: ${title.trim()}`)
    setTitle(""); setDue("")
    onAdded()
  }
  return (
    <form onSubmit={submit} aria-label="Add a task" className="mb-3 flex flex-wrap items-center gap-2">
      <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="Add a task to a rollout" aria-label="New task title" className="h-8 min-w-48 flex-1 text-[13px]" />
      {open.length > 1 && (
        <select value={rollout.id} onChange={(e) => setPick(Number(e.target.value))} aria-label="Rollout for the new task" className={fieldAuto}>
          {open.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      )}
      <DatePicker value={due} onChange={setDue} label="Due date for the new task" placeholder="No date" className="h-8 w-36 px-2" />
      <Button type="submit" size="sm" loading={busy} disabled={!title.trim()}><Plus className="h-3.5 w-3.5" aria-hidden /> Add</Button>
    </form>
  )
}
