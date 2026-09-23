import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, postForm, projectForm, type ProjectFormData, type User } from "@/lib/api"

// Field names are Flask's: the form posts to the same route the Jinja page
// did, as multipart (the PO document rides along on create).
const selectClass = "h-8 w-full rounded-md border border-input bg-background px-2 text-[13px]"

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="grid gap-1 text-[12px] text-muted-foreground">{label}{hint && <span className="ml-1 text-[11.5px]">({hint})</span>}{children}</label>
}

export default function ProjectForm(_props: { user: User }) {
  const editId = Number(useParams().id) || null
  const [params] = useSearchParams()
  const query = editId ? `edit=${editId}` : params.get("from") ? `from=${params.get("from")}` : ""
  const [d, setD] = useState<ProjectFormData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState<Record<string, string>>({})
  const [team, setTeam] = useState<string[]>([])
  const [approval, setApproval] = useState(false)

  useEffect(() => {
    projectForm(query).then((data) => {
      setD(data)
      const p = data.project
      setF({
        name: p.name ?? "", client: p.client ?? "", via: p.via ?? data.via_options[0], account_manager_name: p.account_manager_name ?? "",
        account_manager_email: p.account_manager_email ?? "", partner_name: p.partner_name ?? "", partner_account_manager_name: p.partner_account_manager_name ?? "",
        partner_account_manager_email: p.partner_account_manager_email ?? "", po_number: p.po_number ?? "", po_date: p.po_date ?? "", start_date: p.start_date ?? "",
        target_end_date: p.target_end_date ?? "", delivery_mode: p.delivery_mode ?? data.delivery_modes[0], vendor_name: p.vendor_name ?? "", product_name: p.product_name ?? "",
        outsourcer_name: p.outsourcer_name ?? "", outsourcer_email: p.outsourcer_email ?? "",
        stage_template_id: String(p.stage_template_id ?? data.templates[0]?.id ?? ""), owner_id: String(p.owner_id ?? data.me),
      })
      setApproval(!!p.customer_approval)
      document.title = `${data.mode === "edit" ? "Edit" : data.mode === "duplicate" ? "Duplicate" : "New"} project · Odin`
    }).catch((e) => setError(e instanceof ApiError && e.status === 403 ? "You cannot edit this project." : e instanceof ApiError ? e.message : "Could not load the form"))
  }, [query])

  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const partner = d?.partners.find((p) => p.name === f.partner_name)

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!d) return
    const fd = new FormData(e.currentTarget)          // picks up the file input
    for (const [k, v] of Object.entries(f)) fd.set(k, v)
    fd.delete("team_user_ids"); for (const id of team) fd.append("team_user_ids", id)
    if (approval) fd.set("customer_approval", "1"); else fd.delete("customer_approval")
    setBusy(true)
    try {
      const r = await postForm(d.mode === "edit" ? `/projects/${d.id}/edit` : "/projects/new", fd)
      const failed = r.location && (r.location.endsWith("/projects/new") || r.location.endsWith("/edit"))
      if (r.location && !failed) { window.location.assign(r.location); return }
      setNotice(r.messages.join(" ") || "Not saved")
    } catch (err) { setNotice(err instanceof ApiError ? err.message : "That did not save") } finally { setBusy(false) }
  }

  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <div className="p-5 text-[13px] text-muted-foreground">Loading…</div>
  const editing = d.mode === "edit"
  const title = editing ? "Edit project" : d.mode === "duplicate" ? "Duplicate project" : "New project"

  return (
    <div className="px-5 pb-8 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <a href="/projects" className="text-[12.5px] text-muted-foreground hover:text-foreground">Projects</a><span className="text-[12.5px] text-muted-foreground">/</span>
        <h1 className="text-[17px] font-semibold tracking-tight">{title}</h1>
        {editing && <a href={`/projects/${d.id}`} className={`ml-auto ${buttonVariants({ variant: "ghost", size: "sm" })}`}>Cancel</a>}
      </div>
      {notice && <div className="mt-3 flex items-center justify-between rounded-md bg-warn-soft px-3 py-1.5 text-[12.5px] text-warn" role="alert"><span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}

      <form onSubmit={submit} className="mt-4 grid max-w-3xl gap-4 lg:grid-cols-2">
        <section className="grid content-start gap-3 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Project</h3>
          <Field label="Project name *"><Input value={f.name} onChange={set("name")} required maxLength={200} aria-label="Project name" className="h-8 text-[13px]" /></Field>
          <Field label="Client *"><Input value={f.client} onChange={set("client")} required maxLength={200} aria-label="Client" className="h-8 text-[13px]" /></Field>
          {editing ? (
            <Field label="Owner" hint="the project manager">
              <select value={f.owner_id} onChange={set("owner_id")} aria-label="Owner" className={selectClass}>{d.users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
            </Field>
          ) : (
            <Field label="Team" hint="optional — added as coordinators; you are the project manager">
              <select multiple size={4} value={team} onChange={(e) => setTeam([...e.target.selectedOptions].map((o) => o.value))} aria-label="Team members" className="rounded-md border border-input bg-background px-2 py-1 text-[13px]">
                {d.users.filter((u) => u.id !== d.me).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </Field>
          )}
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={approval} onChange={(e) => setApproval(e.target.checked)} className="h-3.5 w-3.5 accent-primary" /> Ask the customer contact to approve each stage change</label>
          <Field label="PO number"><Input value={f.po_number} onChange={set("po_number")} maxLength={100} aria-label="PO number" className="h-8 text-[13px]" /></Field>
          <div className="grid grid-cols-3 gap-2">
            <Field label="PO date"><Input type="date" value={f.po_date} onChange={(e) => setF({ ...f, po_date: e.target.value, start_date: f.start_date || e.target.value })} aria-label="PO date" className="h-8 text-[12.5px]" /></Field>
            <Field label="Start date"><Input type="date" value={f.start_date} onChange={set("start_date")} aria-label="Start date" className="h-8 text-[12.5px]" /></Field>
            <Field label="Target end"><Input type="date" value={f.target_end_date} onChange={set("target_end_date")} aria-label="Target end date" className="h-8 text-[12.5px]" /></Field>
          </div>
          {!editing && (
            <>
              <Field label="Stage template" hint="the project gets its own copy; edit it on the project afterwards">
                <select name="stage_template_id" value={f.stage_template_id} onChange={set("stage_template_id")} aria-label="Stage template" className={selectClass}>{d.templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
              </Field>
              <Field label="Client PO document *" hint="required — no project without the PO on file">
                <input type="file" name="po_document" required aria-label="Client PO document" className="text-[12.5px] file:mr-2 file:rounded-md file:border file:border-border file:bg-background file:px-2 file:py-1 file:text-[12.5px] file:font-medium" />
              </Field>
            </>
          )}
        </section>

        <section className="grid content-start gap-3 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Commercial route and delivery</h3>
          <Field label="Via *"><select value={f.via} onChange={set("via")} aria-label="Via" className={selectClass}>{d.via_options.map((v) => <option key={v}>{v}</option>)}</select></Field>
          {f.via === "Partner" ? (
            <>
              <Field label="Partner">
                <select value={f.partner_name} onChange={(e) => setF({ ...f, partner_name: e.target.value, partner_account_manager_name: "", partner_account_manager_email: "" })} aria-label="Partner name" className={selectClass}>
                  <option value="">Select…</option>{d.partners.map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Account manager (partner)">
                <select value={f.partner_account_manager_name} onChange={(e) => setF({ ...f, partner_account_manager_name: e.target.value, partner_account_manager_email: partner?.managers.find((m) => m.name === e.target.value)?.email ?? "" })} aria-label="Account manager (partner)" className={selectClass} disabled={!partner}>
                  <option value="">{partner ? "Select…" : "Select a partner first…"}</option>{partner?.managers.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
                </select>
              </Field>
              <Field label="Account manager email"><Input value={f.partner_account_manager_email} readOnly aria-label="Partner account manager email" className="h-8 text-[13px] text-muted-foreground" /></Field>
            </>
          ) : (
            <>
              <Field label="Account manager (internal)">
                <select value={f.account_manager_name} onChange={(e) => setF({ ...f, account_manager_name: e.target.value, account_manager_email: d.account_managers.find((a) => a.name === e.target.value)?.email ?? "" })} aria-label="Account manager (internal)" className={selectClass}>
                  <option value="">Select…</option>{d.account_managers.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
                </select>
              </Field>
              <Field label="Account manager email"><Input value={f.account_manager_email} readOnly aria-label="Account manager email" className="h-8 text-[13px] text-muted-foreground" /></Field>
            </>
          )}
          <Field label="Delivery mode *"><select value={f.delivery_mode} onChange={set("delivery_mode")} aria-label="Delivery mode" className={selectClass}>{d.delivery_modes.map((m) => <option key={m}>{m}</option>)}</select></Field>
          {f.delivery_mode === "Outsourced" ? (
            <>
              <Field label="Outsourcer">
                <select value={f.outsourcer_name} onChange={(e) => setF({ ...f, outsourcer_name: e.target.value, outsourcer_email: d.outsourcers.find((o) => o.name === e.target.value)?.email ?? "" })} aria-label="Outsourcer" className={selectClass}>
                  <option value="">Select…</option>{d.outsourcers.map((o) => <option key={o.name} value={o.name}>{o.name}</option>)}
                </select>
              </Field>
              <Field label="Outsourcer email"><Input value={f.outsourcer_email} readOnly aria-label="Outsourcer email" className="h-8 text-[13px] text-muted-foreground" /></Field>
            </>
          ) : (
            <>
              <Field label="Vendor"><select value={f.vendor_name} onChange={set("vendor_name")} aria-label="Vendor" className={selectClass}><option value="">Select…</option>{d.vendors.map((v) => <option key={v}>{v}</option>)}</select></Field>
              <Field label="Product"><select value={f.product_name} onChange={set("product_name")} aria-label="Product" className={selectClass}><option value="">Select…</option>{d.products.map((p) => <option key={p}>{p}</option>)}</select></Field>
            </>
          )}
        </section>

        <div className="flex items-center gap-3 lg:col-span-2">
          <Button type="submit" size="sm" disabled={busy || !f.name?.trim() || !f.client?.trim()}>{busy ? "Saving…" : editing ? "Save changes" : "Create project"}</Button>
          {!editing && <span className="text-[11.5px] text-muted-foreground">Pick-lists are managed under Settings → Contacts & partners.</span>}
        </div>
      </form>
    </div>
  )
}
