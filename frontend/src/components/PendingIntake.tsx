import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { Inbox } from "lucide-react"
import { Ago } from "@/components/Ago"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/EmptyState"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Tag } from "@/components/ui/tag"
import { ApiError, confirmIntake, pendingIntake, postForm, type FormReply, type PendingIntake as Meta, type PendingIntakeRow } from "@/lib/api"
import { askConfirm } from "@/lib/confirm"
import { fmtDate } from "@/lib/format"
import { danger, field as fieldLook } from "@/lib/ui"
import { useLoad } from "@/lib/useLoad"

// Deals the CRM sent (services/intake.py), waiting for a project manager. They sit
// here, in the Flow's List and the rollouts list's "Pending intake" view, and in no
// lane, count, alert or report until confirmed: attach the client's PO and take
// ownership, and the rollout starts as any new one does. `onChanged` runs after a
// discard; a confirm goes straight to the new rollout.
export function PendingIntake({ rows, onChanged }: { rows: PendingIntakeRow[]; onChanged?: () => unknown }) {
  if (rows.length === 0) return null
  return <WithMeta rows={rows} onChanged={onChanged} />
}

function WithMeta({ rows, onChanged }: { rows: PendingIntakeRow[]; onChanged?: () => unknown }) {
  const { data: meta } = useLoad("intake-meta", pendingIntake)   // who may confirm, and who could manage
  return <Lane rows={rows} meta={meta} onChanged={onChanged} />
}

// The rollouts list's "Pending intake" view: the same lane, fed by its own request.
export function PendingView() {
  const { data, reload } = useLoad("intake-pending", pendingIntake)
  return (
    <div className="mt-3 min-h-0 flex-1 overflow-auto panel p-4">
      {!data ? <p className="text-[13px] text-muted-foreground">Loading…</p>
        : data.rows.length === 0 ? <EmptyState>No intake is waiting. Deals the CRM sends appear here until a project manager confirms them.</EmptyState>
          : <Lane rows={data.rows} meta={data} onChanged={reload} bare />}
    </div>
  )
}

// The rollout's own page while it is a pending intake: one line saying so, with Confirm
// (for those who may create a rollout) and Discard (for those who may delete it).
export function IntakeBanner({ projectId, canDiscard, onConfirmed }: { projectId: number; canDiscard: boolean; onConfirmed: (messages: string[]) => unknown }) {
  const navigate = useNavigate()
  const { data } = useLoad(`intake-pending:${projectId}`, pendingIntake)
  const [open, setOpen] = useState(false)
  const row = data?.rows.find((r) => r.id === projectId)
  if (!row) return null
  return (
    <div className="px-5 pt-3">
      <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-muted/40 px-3 py-2 text-[13px]">
          <span className="min-w-0 flex-1"><Inbox className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden />
            A deal from {row.source ?? "the CRM"}{row.deal_id ? ` (${row.deal_id})` : ""}, waiting for a project manager. It counts in no flow, alert or report until it is confirmed.</span>
          {(data?.can_confirm || canDiscard) && <Button size="sm" variant="outline" onClick={() => setOpen(true)}>{data?.can_confirm ? "Confirm…" : "Discard…"}</Button>}
      </div>
      {open && <ConfirmDialog row={row} meta={data} canDiscard={canDiscard} onClose={() => setOpen(false)}
        onDiscarded={() => navigate("/projects?view=pending")} onConfirmed={(r) => { setOpen(false); void onConfirmed(r.messages) }} />}
    </div>
  )
}

function Lane({ rows, meta, onChanged, bare }: { rows: PendingIntakeRow[]; meta: Meta | null; onChanged?: () => unknown; bare?: boolean }) {
  const [open, setOpen] = useState<PendingIntakeRow | null>(null)
  return (
    <section aria-label="Pending intake" className={bare ? undefined : "rounded-lg bg-muted/40 px-3 py-3"}>
      <h2 className="flex items-baseline gap-2 text-[13px] font-semibold">
        <Inbox className="size-3.5 self-center text-muted-foreground" aria-hidden />Pending intake
        <span className="font-normal text-muted-foreground">{rows.length}</span>
      </h2>
      <p className="mt-1 text-[12px] text-muted-foreground">Deals from the CRM. Each waits for a project manager to attach the PO and take ownership; none counts in the flow, alerts or reports until then.</p>
      <ul className="mt-2 grid grid-cols-1 divide-y divide-border text-[13px]" aria-label="Pending intakes">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium" title={r.name}>{r.name}</p>
              <p className="truncate text-[12px] text-muted-foreground">
                {[r.client, r.vendor_name && `${r.vendor_name}${r.product_name ? ` ${r.product_name}` : ""}`, r.target_end_date && `target ${fmtDate(r.target_end_date)}`].filter(Boolean).join(" · ")}
              </p>
            </div>
            {r.source && <Tag kind="source" title={r.deal_id ? `Deal ${r.deal_id}` : undefined}>{r.source}</Tag>}
            <span className="text-[12px] text-muted-foreground">in <Ago iso={r.created_at} /></span>
            <Button size="sm" variant="outline" aria-label={`Confirm ${r.name}`} onClick={() => setOpen(r)}>Confirm…</Button>
          </li>
        ))}
      </ul>
      {open && <ConfirmDialog row={open} meta={meta} onClose={() => setOpen(null)} onDiscarded={() => { setOpen(null); void onChanged?.() }} />}
    </section>
  )
}

function ConfirmDialog({ row, meta, onClose, onDiscarded, canDiscard = true, onConfirmed }: {
  row: PendingIntakeRow; meta: Meta | null; onClose: () => void; onDiscarded: () => void; canDiscard?: boolean; onConfirmed?: (r: FormReply) => void
}) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const canConfirm = meta?.can_confirm ?? true   // the server decides; until it answers the form is open
  const needLead = meta != null && !meta.can_lead
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const r = await confirmIntake(row.id, new FormData(e.currentTarget))
      if (onConfirmed) onConfirmed(r)   // already on the rollout's page: it reloads in place
      else navigate(r.location ?? `/projects/${row.id}`)
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Could not confirm that rollout"); setBusy(false) }
  }
  async function discard() {
    if (!(await askConfirm(`Discard ${row.name}? It leaves the pending list; the CRM can send the deal again.`, "Discard"))) return
    setBusy(true); setErr(null)
    try { await postForm(`/projects/${row.id}/delete`); onDiscarded() } catch (x) { setErr(x instanceof ApiError ? x.message : "Could not discard that intake"); setBusy(false) }
  }
  const facts: [string, string | null][] = [
    ["Client", row.client], ["Deal", row.deal_id], ["Sent by", row.source], ["Delivery", row.delivery_mode],
    ["Vendor and product", [row.vendor_name, row.product_name].filter(Boolean).join(" ") || null], ["Target", row.target_end_date ? fmtDate(row.target_end_date) : null],
    ["Customer contacts", row.contacts.join(", ") || null], ["Held by", row.owner_name],
  ]
  return (
    <Dialog open onOpenChange={(o) => { if (!o && !busy) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Confirm {row.name}</DialogTitle>
          <DialogDescription>Attach the client's PO and take ownership. The rollout then starts in its first stage with the template's tasks.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-1 gap-3">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[13px]">
            {facts.filter(([, v]) => v).map(([k, v]) => <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="min-w-0 wrap-anywhere">{v}</dd></div>)}
          </dl>
          <Field label={`${meta?.po_category ?? "Client PO"} document *`} hint="required: no rollout without the PO on file">
            <Input type="file" name="po_document" required aria-label="Client PO document" className="h-auto py-1" />
          </Field>
          <Field label="PO number"><Input name="po_number" defaultValue={row.po_number ?? ""} maxLength={60} className="h-8 text-[13px]" /></Field>
          {needLead && (
            <Field label="Project manager *" hint="You cannot move stages, so name someone who can">
              <select name="owner_id" required defaultValue="" className={fieldLook}>
                <option value="" disabled>Choose…</option>
                {meta.leads.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </Field>
          )}
          {!canConfirm && <Notice bad>Your role cannot confirm a rollout. Ask a project manager.</Notice>}
          {err && <Notice bad>{err}</Notice>}
          <DialogFooter>
            {canDiscard && <Button type="button" variant="ghost" className={danger} disabled={busy} onClick={() => void discard()}>Discard</Button>}
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={busy} disabled={!canConfirm}>{needLead ? "Confirm" : "Confirm and take ownership"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
