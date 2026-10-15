import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react"
import { PanelTitle } from "@/components/PanelTitle"
import { field } from "@/lib/ui"
import { DatePicker } from "@/components/DatePicker"
import { useParams, useSearchParams } from "react-router-dom"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, postForm, projectForm, type ProjectFormData, type User } from "@/lib/api"
import { useUnsavedGuard } from "@/lib/useUnsavedGuard"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { productsFor } from "@/lib/format"
import { toastAfterLoad } from "@/lib/toast"

// Field names are Flask's: the form posts to the same route the Jinja page
// did, as multipart (the PO document rides along on create).
const MISSING = "This rollout does not exist, or you cannot edit it."

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">{label}{hint && <span className="ml-1 text-[12px]">({hint})</span>}{children}</label>
}

export default function ProjectForm(_props: { user: User }) {
  const editId = Number(useParams().id) || null
  const [params] = useSearchParams()
  const query = editId ? `edit=${editId}` : params.get("from") ? `from=${params.get("from")}` : ""
  const [d, setD] = useState<ProjectFormData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)   // a double click sends once: state updates too late to stop the second
  const [f, setF] = useState<Record<string, string>>({})
  const [team, setTeam] = useState<string[]>([])
  const [approval, setApproval] = useState(false)
  const [initial, setInitial] = useState("")
  const [saved, setSaved] = useState(false)
  const snap = JSON.stringify({ f, approval, team })   // everything the user can change, not just the text fields
  useUnsavedGuard(!saved && initial !== "" && initial !== snap)

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
        // a new project starts from Settings → Projects & workflow; a copy or an edit keeps its own
        stage_template_id: String(p.stage_template_id ?? data.defaults.stage_template_id ?? data.templates[0]?.id ?? ""), owner_id: String(p.owner_id ?? (data.mode !== "edit" && !data.can_lead ? "" : data.me)),
      })
      setApproval(data.mode === "new" ? data.defaults.customer_approval : !!p.customer_approval)
      setInitial("pending")   // the snapshot is taken on the next render, once f is set
      document.title = `${data.mode === "edit" ? "Edit" : data.mode === "duplicate" ? "Duplicate" : "New"} project · Odin`
    }).catch((e) => setError(editId && e instanceof ApiError && (e.status === 403 || e.status === 404) ? MISSING : e instanceof ApiError && e.status === 403 ? "You cannot create projects." : e instanceof ApiError ? e.message : "Could not load the form"))
  }, [query])

  useEffect(() => { if (initial === "pending") setInitial(snap) }, [initial, snap])
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const partner = d?.partners.find((p) => p.name === f.partner_name)

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!d) return
    const fd = new FormData(e.currentTarget)          // picks up the file input
    for (const [k, v] of Object.entries(f)) fd.set(k, v)
    fd.delete("team_user_ids"); for (const id of team) fd.append("team_user_ids", id)
    if (approval) fd.set("customer_approval", "1"); else fd.delete("customer_approval")
    if (sending.current) return
    sending.current = true
    setBusy(true)
    try {
      const r = await postForm(d.mode === "edit" ? `/projects/${d.id}/edit` : "/projects/new", fd)
      const failed = r.location && (r.location.endsWith("/projects/new") || r.location.endsWith("/edit"))
      // saved: stay busy until the next page (the new project's own page once the server names it)
      if (r.location && !failed) { setSaved(true); toastAfterLoad(r.messages.join(" ") || "Saved"); window.setTimeout(() => window.location.assign(r.location!), 0); return }
      setNotice(r.messages.join(" ") || "Not saved")
    } catch (err) { setNotice(err instanceof ApiError ? err.message : "That did not save") }
    sending.current = false
    setBusy(false)
  }

  if (error) return <LoadError message={error} back={error === MISSING ? { href: "/projects", label: "All rollouts" } : undefined} />
  if (!d) return <PageSkeleton />
  const editing = d.mode === "edit"
  const title = editing ? "Edit project" : d.mode === "duplicate" ? "Duplicate project" : "New project"

  return (
    <div className="px-5 pb-8 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <a href="/projects" className="text-[13px] text-muted-foreground hover:text-foreground">Rollouts</a><span className="text-[13px] text-muted-foreground">/</span>
        <h1 className="text-[17px] font-semibold tracking-tight">{title}</h1>
        {/* back to where it came from: the rollout being edited or copied, else the list */}
        <a href={editing ? `/projects/${d.id}` : params.get("from") ? `/projects/${params.get("from")}` : "/projects"} className={`ml-auto ${buttonVariants({ variant: "ghost", size: "sm" })}`}>Cancel</a>
      </div>
      {notice && <div className="mt-3 flex items-center justify-between rounded-md bg-destructive/10 px-3 py-2 text-[13px] text-destructive" role="alert"><span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}

      <p className="mt-3 text-[12px] text-muted-foreground">Fields marked * are required.</p>   {/* test report UX-26 */}
      <form onSubmit={submit} className="mt-2 grid max-w-5xl grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="grid grid-cols-1 content-start gap-3 panel p-4">
          <PanelTitle className="mb-0">Project</PanelTitle>
          <Field label="Project name *"><Input value={f.name} onChange={set("name")} required maxLength={200} aria-label="Project name" className="h-8 text-[13px]" /></Field>
          <Field label="Client *"><Input value={f.client} onChange={set("client")} required maxLength={200} aria-label="Client" className="h-8 text-[13px]" /></Field>
          {editing ? (
            <Field label="Owner" hint="the project manager">
              <select value={f.owner_id} onChange={set("owner_id")} aria-label="Owner" className={field}>{d.leads.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
            </Field>
          ) : (<>
            {!d.can_lead && (
              <Field label="Project manager *" hint="someone who can move stages; you join as a coordinator">
                <select value={f.owner_id} onChange={set("owner_id")} required aria-label="Project manager" className={field}>
                  <option value="">Choose…</option>{d.leads.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                </select>
              </Field>
            )}
            <Field label="Team" hint={d.can_lead ? "optional — added as coordinators; you are the project manager" : "optional — added as coordinators"}>
              {/* ticks, not a native multi-select: no Ctrl-click to learn, nothing lost by a plain click */}
              <div role="group" aria-label="Team members" className="grid max-h-40 grid-cols-2 gap-x-4 overflow-auto rounded-lg border border-input bg-background px-3 py-2 text-[13px]">
                {d.users.filter((u) => u.id !== d.me).map((u) => (
                  <label key={u.id} className="flex min-w-0 items-center gap-2 py-1"><input type="checkbox" checked={team.includes(String(u.id))} className="h-3.5 w-3.5 accent-primary"
                    onChange={(e) => setTeam(e.target.checked ? [...team, String(u.id)] : team.filter((x) => x !== String(u.id)))} /><span className="truncate">{u.name}</span></label>
                ))}
              </div>
            </Field>
          </>)}
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={approval} onChange={(e) => setApproval(e.target.checked)} className="h-3.5 w-3.5 accent-primary" /> Ask the customer contact to approve each stage change</label>
          <div className="grid grid-cols-3 gap-2">
            <Field label="PO date"><DatePicker value={f.po_date} onChange={(v) => setF({ ...f, po_date: v, start_date: f.start_date || v })} label="PO date" className="w-full" /></Field>
            <Field label="Start date"><DatePicker value={f.start_date} onChange={(v) => setF({ ...f, start_date: v })} label="Start date" className="w-full" /></Field>
            <Field label="Target end"><DatePicker value={f.target_end_date} onChange={(v) => setF({ ...f, target_end_date: v })} label="Target end date" min={f.start_date || undefined} className="w-full" /></Field>
          </div>
          {!editing && (
            <>
              <Field label="Stage template" hint="the rollout gets its own copy; edit it on the rollout afterwards">
                <select name="stage_template_id" value={f.stage_template_id} onChange={set("stage_template_id")} aria-label="Stage template" className={field}>{d.templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
              </Field>
            </>
          )}
        </section>

        <section className="grid grid-cols-1 content-start gap-3 panel p-4">
          <PanelTitle className="mb-0">Commercial route and delivery</PanelTitle>
          <Field label="Via *"><select value={f.via} onChange={set("via")} aria-label="Via" className={field}>{d.via_options.map((v) => <option key={v}>{v}</option>)}</select></Field>
          {f.via === "Partner" ? (
            <>
              <Field label="Partner">
                <select value={f.partner_name} onChange={(e) => setF({ ...f, partner_name: e.target.value, partner_account_manager_name: "", partner_account_manager_email: "" })} aria-label="Partner name" className={field}>
                  <option value="">Select…</option>{d.partners.map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Account manager (partner)">
                <select value={f.partner_account_manager_name} onChange={(e) => setF({ ...f, partner_account_manager_name: e.target.value, partner_account_manager_email: partner?.managers.find((m) => m.name === e.target.value)?.email ?? "" })} aria-label="Account manager (partner)" className={field} disabled={!partner}>
                  <option value="">{partner ? "Select…" : "Select a partner first…"}</option>{partner?.managers.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
                </select>
              </Field>
              <Field label="Account manager email"><Input value={f.partner_account_manager_email} readOnly aria-label="Partner account manager email" className="h-8 text-[13px] text-muted-foreground" /></Field>
            </>
          ) : (
            <>
              <Field label="Account manager (internal)">
                <select value={f.account_manager_name} onChange={(e) => setF({ ...f, account_manager_name: e.target.value, account_manager_email: d.account_managers.find((a) => a.name === e.target.value)?.email ?? "" })} aria-label="Account manager (internal)" className={field}>
                  <option value="">{d.account_managers.length ? "Select…" : "None set up yet"}</option>{d.account_managers.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
                </select>
              </Field>
              {d.account_managers.length === 0 && <p className="-mt-2 text-[12px] text-muted-foreground">Nobody to pick yet. Add account managers under <a href="/settings/contacts" className="text-primary-text hover:underline">Settings › Contacts &amp; partners</a>.</p>}
              <Field label="Account manager email"><Input value={f.account_manager_email} readOnly aria-label="Account manager email" className="h-8 text-[13px] text-muted-foreground" /></Field>
            </>
          )}
          <Field label="Delivery mode *"><select value={f.delivery_mode} onChange={set("delivery_mode")} aria-label="Delivery mode" className={field}>{d.delivery_modes.map((m) => <option key={m}>{m}</option>)}</select></Field>
          {f.delivery_mode === "Outsourced" ? (
            <>
              <Field label="Outsourcer">
                <select value={f.outsourcer_name} onChange={(e) => setF({ ...f, outsourcer_name: e.target.value, outsourcer_email: d.outsourcers.find((o) => o.name === e.target.value)?.email ?? "" })} aria-label="Outsourcer" className={field}>
                  <option value="">Select…</option>{d.outsourcers.map((o) => <option key={o.name} value={o.name}>{o.name}</option>)}
                </select>
              </Field>
              <Field label="Outsourcer email"><Input value={f.outsourcer_email} readOnly aria-label="Outsourcer email" className="h-8 text-[13px] text-muted-foreground" /></Field>
            </>
          ) : (
            <>
              <Field label="Vendor">
                <select value={f.vendor_name} aria-label="Vendor" className={field}
                  onChange={(e) => { const v = e.target.value; const keep = d.products.some((p) => p.name === f.product_name && (!p.vendor || p.vendor === v)); setF({ ...f, vendor_name: v, product_name: keep ? f.product_name : "" }) }}>
                  <option value="">Select…</option>
                  {/* a vendor deleted since keeps showing on the projects that named it (sim roles-12) */}
                  {(f.vendor_name && !d.vendors.includes(f.vendor_name) ? [f.vendor_name, ...d.vendors] : d.vendors).map((v) => <option key={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="Product">
                <select value={f.product_name} onChange={set("product_name")} aria-label="Product" className={field}>
                  <option value="">Select…</option>
                  {productsFor(d.products, f.vendor_name, f.product_name).map((p) => <option key={p}>{p}</option>)}
                </select>
              </Field>
            </>
          )}
          {/* the purchase order belongs with the commercial route (balances the two cards) */}
          <Field label="PO number"><Input value={f.po_number} onChange={set("po_number")} maxLength={100} aria-label="PO number" className="h-8 text-[13px]" /></Field>
          {!editing && (
            <Field label="Client PO document *" hint="required — no rollout without the PO on file">
              <input type="file" name="po_document" required aria-label="Client PO document"
                className="text-[13px] text-muted-foreground file:mr-3 file:h-8 file:cursor-pointer file:rounded-lg file:border file:border-input file:bg-background file:px-3 file:text-[13px] file:font-medium file:text-foreground hover:file:bg-muted" />
            </Field>
          )}
        </section>

        <div className="flex items-center gap-3 lg:col-span-2">
          <Button type="submit" size="sm" loading={busy} disabled={editing && initial === snap}>{editing ? "Save changes" : "Create project"}</Button>
          {!editing && <span className="text-[12px] text-muted-foreground">Pick-lists are managed under Settings › Contacts & partners.</span>}
        </div>
      </form>
    </div>
  )
}
