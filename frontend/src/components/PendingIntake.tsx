import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { Inbox } from "lucide-react"
import { Ago } from "@/components/Ago"
import { Notice } from "@/components/Notice"
import { PanelLoading } from "@/components/PanelLoading"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/EmptyState"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Tag } from "@/components/ui/tag"
import { DatePicker } from "@/components/DatePicker"
import { FieldInput } from "@/components/FieldValues"
import { confirmIntake, editIntake, pendingIntake, postForm, projectFields, projectForm, type FormReply, type PendingIntake as Meta, type PendingIntakeRow } from "@/lib/api"
import { askConfirm } from "@/lib/confirm"
import { toast } from "@/lib/toast"
import { fieldInput, fmtDate } from "@/lib/format"
import { danger, field as fieldLook } from "@/lib/ui"
import { useAction } from "@/lib/useAction"
import { useLoad } from "@/lib/useLoad"

// One request feeds every use: the lane, the rollouts list's view and the banner
// share a key (the list says who may confirm and who could manage, too).
const INTAKE_KEY = "intake-pending"

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
  const { data: meta } = useLoad(INTAKE_KEY, pendingIntake)   // who may confirm, and who could manage
  return <Lane rows={rows} meta={meta} onChanged={onChanged} />
}

// The rollouts list's "Pending intake" view: the same lane, fed by its own request.
export function PendingView() {
  const { data, reload } = useLoad(INTAKE_KEY, pendingIntake)
  return (
    <div className="mt-3 min-h-0 flex-1 overflow-auto panel p-4">
      {!data ? <PanelLoading />
        : data.rows.length === 0 ? <EmptyState>No intake is waiting. Deals the CRM sends appear here until a project manager confirms them.</EmptyState>
          : <Lane rows={data.rows} meta={data} onChanged={reload} bare />}
    </div>
  )
}

// The rollout's own page while it is a pending intake: one line saying so, with Confirm
// (for those who may create a rollout) and Discard (for those who may delete it).
export function IntakeBanner({ projectId, canDiscard, onConfirmed, onEdited }: {
  projectId: number; canDiscard: boolean; onConfirmed: (messages: string[]) => unknown; onEdited?: () => unknown
}) {
  const navigate = useNavigate()
  const { data, reload } = useLoad(INTAKE_KEY, pendingIntake)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const row = data?.rows.find((r) => r.id === projectId)
  if (!row) return null
  return (
    <div className="px-5 pt-3">
      <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-muted/40 px-3 py-2 text-[13px]">
          <span className="min-w-0 flex-1"><Inbox className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden />
            A deal from {row.source ?? "the CRM"}{row.deal_id ? ` (${row.deal_id})` : ""}, waiting for a project manager. It counts in no flow, alert or report until it is confirmed.</span>
          {data?.can_confirm && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Edit details…</Button>}
          {(data?.can_confirm || canDiscard) && <Button size="sm" variant="outline" onClick={() => setOpen(true)}>{data?.can_confirm ? "Confirm…" : "Discard…"}</Button>}
      </div>
      {editing && <EditDialog row={row} onClose={() => setEditing(false)} onSaved={async () => { setEditing(false); await reload(); await onEdited?.() }} />}
      {open && <ConfirmDialog row={row} meta={data} canDiscard={canDiscard} onClose={() => setOpen(false)}
        onDiscarded={() => navigate("/projects?view=pending")} onConfirmed={(r) => { setOpen(false); void onConfirmed(r.messages) }} />}
    </div>
  )
}

function Lane({ rows, meta, onChanged, bare }: { rows: PendingIntakeRow[]; meta: Meta | null; onChanged?: () => unknown; bare?: boolean }) {
  const [open, setOpen] = useState<PendingIntakeRow | null>(null)
  const [editing, setEditing] = useState<PendingIntakeRow | null>(null)
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
            <span className="text-[12px] text-muted-foreground">arrived <Ago iso={r.created_at} /></span>
            {meta?.can_confirm && <Button size="sm" variant="ghost" aria-label={`Edit details of ${r.name}`} onClick={() => setEditing(r)}>Edit details…</Button>}
            <Button size="sm" variant="outline" aria-label={`Confirm ${r.name}`} onClick={() => setOpen(r)}>Confirm…</Button>
          </li>
        ))}
      </ul>
      {open && <ConfirmDialog row={open} meta={meta} onClose={() => setOpen(null)} onDiscarded={() => { setOpen(null); void onChanged?.() }} />}
      {editing && <EditDialog row={editing} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await onChanged?.() }} />}
    </section>
  )
}

function ConfirmDialog({ row, meta, onClose, onDiscarded, canDiscard = true, onConfirmed }: {
  row: PendingIntakeRow; meta: Meta | null; onClose: () => void; onDiscarded: () => void; canDiscard?: boolean; onConfirmed?: (r: FormReply) => void
}) {
  const navigate = useNavigate()
  const { busy, note, act } = useAction()
  const canConfirm = meta?.can_confirm ?? true   // the server decides; until it answers the form is open
  const needLead = meta != null && !meta.can_lead
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = new FormData(e.currentTarget)
    void act(async () => {
      const r = await confirmIntake(row.id, data)
      if (onConfirmed) onConfirmed(r)   // already on the rollout's page: it reloads in place
      else navigate(r.location ?? `/projects/${row.id}`)
    })
  }
  async function discard() {
    if (!(await askConfirm(`Discard ${row.name}? It leaves the pending list; the CRM can send the deal again.`, "Discard"))) return
    void act(async () => { await postForm(`/projects/${row.id}/delete`); onDiscarded() })
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
          {note?.bad && <Notice bad>{note.text}</Notice>}
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

// Correct what the CRM sent before confirming (routes/intake.intake_edit, audited old → new): the
// project form's pick-lists (vendor and product as suggestions, since a CRM may name one Odin has
// not listed) and the rollout's custom fields. Only what changed is worth a look in the audit row.
const EDIT_KEYS = ["name", "client", "vendor_name", "product_name", "delivery_mode", "target_end_date", "po_number"] as const

function EditDialog({ row, onClose, onSaved }: { row: PendingIntakeRow; onClose: () => void; onSaved: () => unknown }) {
  const { data } = useLoad(`intake-edit:${row.id}`, () => Promise.all([projectForm(""), projectFields(row.id)]))
  const { busy, note, act } = useAction()
  const [f, setF] = useState<Record<string, string>>(() => Object.fromEntries(EDIT_KEYS.map((k) => [k, row[k] ?? ""])))
  const [vals, setVals] = useState<Record<string, string> | null>(null)
  const [form, fields] = data ?? [null, null]
  const shown = vals ?? Object.fromEntries((fields?.fields ?? []).map((c) => [c.id, fieldInput(c.kind, c.value)]))
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  function submit(e: FormEvent) {
    e.preventDefault()
    const body = { ...f, ...Object.fromEntries(Object.entries(vals ?? {}).map(([id, v]) => [`field_${id}`, v])) }
    void act(async () => { await editIntake(row.id, body); toast("Intake details saved."); await onSaved() })
  }
  return (
    <Dialog open onOpenChange={(o) => { if (!o && !busy) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit {row.name}</DialogTitle>
          <DialogDescription>Correct what the CRM sent before you confirm it. The change is in the audit trail.</DialogDescription>
        </DialogHeader>
        {!form ? <PanelLoading /> : (
          <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name *"><Input value={f.name} onChange={set("name")} required maxLength={200} className="h-8 text-[13px]" /></Field>
            <Field label="Client *"><Input value={f.client} onChange={set("client")} required maxLength={200} className="h-8 text-[13px]" /></Field>
            <Field label="Vendor"><Input value={f.vendor_name} onChange={set("vendor_name")} maxLength={120} list="intake-vendors" className="h-8 text-[13px]" /></Field>
            <Field label="Product"><Input value={f.product_name} onChange={set("product_name")} maxLength={120} list="intake-products" className="h-8 text-[13px]" /></Field>
            <datalist id="intake-vendors">{form.vendors.map((v) => <option key={v}>{v}</option>)}</datalist>
            <datalist id="intake-products">{form.products.filter((p) => !p.vendor || !f.vendor_name || p.vendor === f.vendor_name).map((p) => <option key={p.name}>{p.name}</option>)}</datalist>
            <Field label="Delivery mode">
              <select value={f.delivery_mode} onChange={set("delivery_mode")} className={fieldLook}>{form.delivery_modes.map((m) => <option key={m}>{m}</option>)}</select>
            </Field>
            <Field label="Target date"><DatePicker value={f.target_end_date} onChange={(v) => setF({ ...f, target_end_date: v })} label="Target date" className="w-full" /></Field>
            <Field label="PO number"><Input value={f.po_number} onChange={set("po_number")} maxLength={60} className="h-8 text-[13px]" /></Field>
            {fields?.fields.map((c) => (
              <Field key={c.id} label={c.name}><FieldInput field={c} value={shown[c.id] ?? ""} onChange={(v) => setVals({ ...shown, [c.id]: v })} /></Field>
            ))}
            {note?.bad && <div className="sm:col-span-2"><Notice bad>{note.text}</Notice></div>}
            <DialogFooter className="sm:col-span-2">
              <Button type="button" variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
              <Button type="submit" loading={busy}>Save details</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
