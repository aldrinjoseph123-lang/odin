import { useEffect, useRef, useState } from "react"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Notice } from "@/components/Notice"
import { ApiError, changeStage, type FlowDetail } from "@/lib/api"

// The one way a rollout moves to its next stage, from the detail's rail or a
// Kanban drop: what the move will do next to the button that does it, a
// confirm that names the risk (Cancel first when there is one), and a guard
// against a double-click. The server still decides (permission, sign-off gate,
// a move that lost a race); its answer shows here. A 409 means the rollout
// moved on since this view was drawn: `onStale` reloads it, so a retry does
// not send the same old stage again.
export function MoveConfirm({ d, from = d.stage, onMoved, onStale, quiet, confirmNow, onCancel, heading: H = "h3", bare }: {
  d: FlowDetail
  from?: string              // the stage the person saw (a Kanban card's column); the server refuses a move from any other
  onMoved: (text: string, undo?: string) => void | Promise<void>
  onStale: (why: string) => void
  quiet?: boolean            // the rail's outline button while work is still open in the stage
  confirmNow?: boolean       // a Kanban drop is the first click: open straight on the confirm
  onCancel?: () => void      // a Kanban drop's dialog closes on Cancel
  heading?: "h2" | "h3"
  bare?: boolean             // inside a dialog: no card of its own, no heading (the dialog's title says it)
}) {
  const [note, setNote] = useState("")
  const [confirming, setConfirming] = useState(!!confirmNow)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const confirmAt = useRef(0)
  // a drop opens on the confirm: the guard counts from then, as from the rail's first click
  useEffect(() => { if (confirmNow) confirmAt.current = Date.now() }, [confirmNow])
  const advanceRef = useRef<HTMLButtonElement>(null)
  if (!d.next_stage) return null
  const next = d.next_stage
  const openHere = d.tasks.filter((t) => !t.done && t.stage === d.stage).length
  const approvalPending = d.approval?.stage === d.stage && d.approval.status === "pending"
  const declined = d.approval?.status === "declined" && d.approval.stage === d.stage
  const told = d.participants.filter((p) => p.user_id !== d.me).length
  const risky = openHere > 0 || approvalPending || declined
  const cancel = () => {
    if (onCancel) return onCancel()
    setConfirming(false); requestAnimationFrame(() => advanceRef.current?.focus())
  }
  async function advance() {
    setBusy(true); setErr(null)
    try {
      const r = await changeStage(d.id, next, note, from)
      setNote(""); setConfirming(false)
      await onMoved(`${d.name} moved to ${next}.`, r.undo)
    } catch (e) {
      const why = e instanceof ApiError ? e.message : "Could not move the stage"
      setErr(why)
      if (e instanceof ApiError && e.status === 409) { setConfirming(false); onStale(why) }
    } finally { setBusy(false) }
  }
  return (
    <section className={bare ? undefined : "panel p-3"} aria-label={bare ? `Move to ${next}` : undefined} aria-labelledby={bare ? undefined : `move-h-${d.id}`} onKeyDown={(e) => { if (e.key === "Escape" && confirming) { e.stopPropagation(); cancel() } }}>
      {!bare && <H id={`move-h-${d.id}`} className="mb-2 flex items-center gap-2 text-[12px] font-semibold text-nav-fg"><ArrowRight className="h-3.5 w-3.5" /> Move to {next}</H>}
      <ul className="mb-2 grid grid-cols-1 gap-1 text-[13px] text-muted-foreground">
        {openHere > 0 && <li className="font-medium text-warn">{openHere} open task{openHere === 1 ? "" : "s"} still in {d.stage}</li>}
        {approvalPending && <li className="font-medium text-warn">The customer has not approved {d.stage} yet</li>}
        {declined && <li className="font-medium text-bad">The customer declined {d.stage}{d.approval?.comment ? `: “${d.approval.comment}”` : ""}</li>}
        <li>Tells {told} {told === 1 ? "person" : "people"} on the team</li>
      </ul>
      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" aria-label="Stage change note, shared with the customer and partners" aria-describedby={`move-note-${d.id}`} maxLength={5000} className="h-8 text-[13px]" />
      <p id={`move-note-${d.id}`} className="mt-1 text-[12px] text-muted-foreground">Shared with the customer and partners.</p>
      {confirming ? (
        <div className={bare ? "mt-2 flex justify-end gap-2" : "mt-2 grid grid-cols-1 gap-2"} role="group" aria-label={`Confirm the move to ${next}`}>
          {/* Cancel first, the move after it, as in every other dialog */}
          <Button size="sm" variant={risky ? "outline" : "ghost"} onClick={cancel} disabled={busy} autoFocus={risky}>Cancel</Button>
          <Button size="sm" onClick={() => { if (Date.now() - confirmAt.current > 400) void advance() }} loading={busy} autoFocus={!risky}>
            {openHere > 0 ? `Move with ${openHere} open task${openHere === 1 ? "" : "s"}` : approvalPending ? "Move without the customer's approval" : `Move to ${next} now`}</Button>
        </div>
      ) : (
        <Button ref={advanceRef} className="mt-2 w-full" size="sm" variant={quiet ? "outline" : "default"} onClick={() => { confirmAt.current = Date.now(); setConfirming(true) }} disabled={busy}>Move to {next} <ArrowRight className="h-3.5 w-3.5" /></Button>
      )}
      {err && <Notice bad className="mt-2">{err}</Notice>}
    </section>
  )
}
