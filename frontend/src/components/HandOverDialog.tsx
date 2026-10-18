import { useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Field } from "@/components/ui/field"
import { Notice } from "@/components/Notice"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { fieldAuto } from "@/lib/ui"
import type { AdminUser } from "@/lib/api"
import { plural } from "@/lib/format"

// Deactivating someone who holds open work: offer to move it to a colleague in
// the same step (their open tasks, the rollouts they manage, the RAID items they
// own). The server does it in one transaction, audits it and tells the new owner.
export function HandOverDialog({ u, colleagues, busy, send, onClose }: {
  u: AdminUser; colleagues: AdminUser[]; busy: boolean
  send: (path: string, fields: Record<string, string>, confirmText?: string, onError?: (m: string) => void) => Promise<boolean>; onClose: (done: boolean) => void
}) {
  const [to, setTo] = useState("")
  const [problem, setProblem] = useState<string | null>(null)
  const { tasks, rollouts, raid } = u.holds
  async function submit(e: FormEvent) {
    e.preventDefault()
    setProblem(null)
    if (await send(`/users/${u.id}/active`, { active: "0", ...(to ? { handover_to: to } : {}) }, undefined, setProblem)) onClose(true)
  }
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(false) }}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid grid-cols-1 gap-4">
          <DialogHeader>
            <DialogTitle>Deactivate {u.name}?</DialogTitle>
            <DialogDescription>Their open sessions end now. They hold {[plural(tasks, "open task"), plural(rollouts, "rollout they manage", "rollouts they manage"), plural(raid, "RAID item")].join(", ")}.</DialogDescription>
          </DialogHeader>
          <Field label="Hand it over to" hint="The new owner is told. Finished work stays under their name. Leave it unset to move nothing.">
            <select value={to} onChange={(e) => setTo(e.target.value)} aria-label="Hand over to" className={fieldAuto}>
              <option value="">Nobody: leave it where it is</option>
              {colleagues.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.role}</option>)}
            </select>
          </Field>
          {problem && <Notice bad>{problem}</Notice>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onClose(false)}>Cancel</Button>
            <Button type="submit" variant="destructive" loading={busy}>{to ? "Hand over and deactivate" : "Deactivate"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
