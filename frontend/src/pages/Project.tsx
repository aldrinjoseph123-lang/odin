import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import { Copy, Trash2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Detail } from "@/pages/Flow"
import { StageListEditor } from "@/components/StageListEditor"
import { ApiError, flowDetail, postForm, projectExtras, type FlowDetail, type FormReply, type ProjectExtras, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()
const fmtDateTime = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
const fmtDate = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })
const selectClass = "h-8 rounded-md border border-input bg-background px-2 text-[13px]"
const LABELS: Record<string, string> = {
  client: "Client", via: "Via", partner_name: "Partner", partner_account_manager_name: "Account manager (partner)", account_manager_name: "Account manager",
  po_number: "PO number", po_date: "PO date", start_date: "Start date", target_end_date: "Target end date", delivery_mode: "Delivery mode",
  outsourcer_name: "Outsourcer", vendor_name: "Vendor", product_name: "Product",
}

function Panel({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="rounded-lg border border-border p-4">
      <h3 className="mb-3 text-[12px] font-semibold text-nav-fg">{title}{hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}</h3>
      {children}
    </section>
  )
}

export default function Project(_props: { user: User }) {
  const id = Number(useParams().id)
  const [d, setD] = useState<FlowDetail | null>(null)
  const [x, setX] = useState<ProjectExtras | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ text: string; undo?: string | null } | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [fd, ex] = await Promise.all([flowDetail(id), projectExtras(id)])
      setD(fd); setX(ex); setError(null)
    } catch (e) { setError(e instanceof ApiError && e.status === 404 ? "This project does not exist, or you are not on it." : e instanceof ApiError ? e.message : "Could not load the project") }
  }, [id])
  useEffect(() => { void reload() }, [reload])
  useEffect(() => { if (x) document.title = `${x.name} · Odin` }, [x])

  // one door for every form post: show what Flask said, then refetch
  async function send(path: string, fields: Record<string, string> | FormData = {}, confirmText?: string): Promise<FormReply | null> {
    if (confirmText && !window.confirm(confirmText)) return null
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      if (r.location === "/board") { window.location.assign("/board"); return r }
      setNotice(r.messages.length ? { text: r.messages.join(" "), undo: r.undo } : null)
      await reload()
      return r
    } catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That did not save" }); return null } finally { setBusy(false) }
  }
  async function undo() {
    if (!notice?.undo) return
    await send(notice.undo)
  }

  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d || !x) return <div className="p-5 text-[13px] text-muted-foreground">Loading project…</div>
  const can = x.can

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-wrap items-center gap-2 px-5 pt-4">
        <a href="/projects" className="text-[12.5px] text-muted-foreground hover:text-foreground">Projects</a>
        <span className="text-[12.5px] text-muted-foreground">/</span>
        <span className="text-[12.5px] font-medium">{x.name}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <a href={`/board?rollout=${id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>On the flow</a>
          <a href={`/projects/${id}/report`} className={buttonVariants({ variant: "ghost", size: "sm" })}>Report</a>
          {can.create && <a href={`/projects/new?from=${id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Duplicate</a>}
          {can.manage && <a href={`/projects/${id}/edit`} className={buttonVariants({ variant: "outline", size: "sm" })}>Edit</a>}
        </div>
      </div>
      {notice && (
        <div className="mx-5 mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status">
          <span>{notice.text}{notice.undo && <button type="button" onClick={undo} className="ml-2 font-medium text-primary-text hover:underline">Undo</button>}</span>
          <button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* the same detail as the flow screen: flowchart, tasks per stage, rail */}
      <Detail d={d} reload={reload} onMoved={(m) => setNotice({ text: m })} standalone />

      <div className="grid gap-4 px-5 pb-6 lg:grid-cols-2">
        <Panel title="Details">
          <dl className="grid grid-cols-[minmax(120px,auto)_1fr] gap-x-4 gap-y-1.5 text-[13px]">
            {Object.entries(LABELS).filter(([k]) => {
              const via = x.details.via
              if (k === "partner_name" || k === "partner_account_manager_name") return via === "Partner"
              if (k === "account_manager_name") return via !== "Partner"
              if (k === "outsourcer_name") return x.details.delivery_mode === "Outsourced"
              if (k === "vendor_name" || k === "product_name") return x.details.delivery_mode !== "Outsourced"
              return true
            }).map(([k, label]) => {
              const email = k === "account_manager_name" ? x.details.account_manager_email : k === "partner_account_manager_name" ? x.details.partner_account_manager_email : k === "outsourcer_name" ? x.details.outsourcer_email : null
              return <div key={k} className="contents"><dt className="text-muted-foreground">{label}</dt><dd>{x.details[k] ?? "—"}{email ? <span className="text-muted-foreground"> · {email}</span> : null}</dd></div>
            })}
            <dt className="text-muted-foreground">Customer approval</dt><dd>{x.customer_approval ? "Asked on every stage change" : "Off"}</dd>
          </dl>
        </Panel>

        <Panel title="Notes" hint={`${x.notes.length}`}>
          {can.note && <NoteForm busy={busy} onSubmit={(note) => send(`/projects/${id}/note`, { note })} />}
          <ul className="mt-3 grid gap-2">
            {x.notes.map((n) => (
              <li key={n.id} className="border-t border-border pt-2 text-[13px] first:border-0 first:pt-0">
                <div className="text-[12px] text-muted-foreground"><span className="font-medium text-foreground">{n.author}</span> · {n.stage} · {fmtDateTime(n.created_at)}</div>
                <div className="whitespace-pre-wrap">{n.note}</div>
              </li>
            ))}
            {x.notes.length === 0 && <li className="text-[13px] text-muted-foreground">No notes yet.</li>}
          </ul>
        </Panel>

        <Panel title="Team" hint="who is on this project, and as what" id="team">
          <ul className="grid gap-1.5">
            {x.participants.map((m) => (
              <li key={m.id} className="flex items-center gap-2 text-[13px]">
                <Avatar className="h-6 w-6"><AvatarFallback className="bg-secondary text-[10px] font-semibold text-nav-fg">{initials(m.name)}</AvatarFallback></Avatar>
                <span className="min-w-0 flex-1 truncate font-medium">{m.name}{!m.active && <span className="ml-1 font-normal text-muted-foreground">(deactivated)</span>}</span>
                <span className="text-muted-foreground">{m.role}</span>
                {m.email && <span className="hidden text-[12px] text-muted-foreground sm:inline">{m.email}</span>}
                {can.manage && m.user_id !== x.owner_id && (
                  <button type="button" disabled={busy} onClick={() => send(`/projects/${id}/participants/${m.id}/remove`)} aria-label={`Remove ${m.name}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>
                )}
              </li>
            ))}
          </ul>
          {can.manage && (
            <div className="mt-3 grid gap-2 border-t border-border pt-3">
              <TeamAddForm x={x} busy={busy} onSubmit={(f) => send(`/projects/${id}/participants/add`, f)} />
              <InviteForm x={x} busy={busy} onSubmit={(f) => send(`/projects/${id}/participants/invite`, f)} />
              <p className="text-[11.5px] text-muted-foreground">The owner is the project manager; change it on Edit. Invited people get a one-time sign-in link and see only their projects.</p>
            </div>
          )}
        </Panel>

        {can.manage && (
          <Panel title="This project's stages" hint="add, rename, reorder, delete, SLAs — only this project changes" id="stages">
            <StageListEditor rows={x.stage_rows} current={d.stage} busy={busy} send={send}
              paths={{ add: `/projects/${id}/stages/add`, rename: (s) => `/projects/${id}/stages/${s}/rename`, move: (s) => `/projects/${id}/stages/${s}/move`, remove: (s) => `/projects/${id}/stages/${s}/delete`, sla: `/projects/${id}/stages/sla` }} />
          </Panel>
        )}

        <Panel title="Documents" hint={`${x.documents.length}`}>
          {can.docs && <UploadForm x={x} busy={busy} onSubmit={(fd) => send(`/projects/${id}/documents`, fd)} />}
          <ul className="mt-3 grid gap-1.5">
            {x.documents.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 text-[13px]">
                <span className="w-28 shrink-0 truncate text-[12px] text-muted-foreground">{doc.category}</span>
                {can.download ? <a href={`/projects/${id}/documents/${doc.id}/download`} className="min-w-0 flex-1 truncate font-medium hover:underline">{doc.filename}</a> : <span className="min-w-0 flex-1 truncate font-medium">{doc.filename}</span>}
                <span className="hidden text-[12px] text-muted-foreground sm:inline">{doc.uploaded_by} · {fmtDate(doc.uploaded_at)}</span>
                {can.docs && <button type="button" disabled={busy} onClick={() => send(`/projects/${id}/documents/${doc.id}/delete`, {}, `Delete ${doc.filename}?`)} aria-label={`Delete ${doc.filename}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>}
              </li>
            ))}
            {x.documents.length === 0 && <li className="text-[13px] text-muted-foreground">No documents uploaded yet.</li>}
          </ul>
        </Panel>

        {(x.guest_links.customer || can.manage) && (
          <Panel title="Sharing">
            {x.guest_links.customer && <LinkRow label="Customer link (view and comment, no sign-in)" url={x.guest_links.customer} />}
            {x.guest_links.vendor && <LinkRow label="Vendor link (may advance the stage)" url={x.guest_links.vendor} />}
            {can.manage && (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => send(`/projects/${id}/rotate-token`, {}, "Rotate both guest links? The current links stop working immediately.")}>Rotate guest links</Button>
                <Button size="sm" variant="outline" disabled={busy} className="text-bad hover:text-bad" onClick={() => send(`/projects/${id}/delete`, {}, "Delete this project? You have five minutes to undo.")}>Delete project</Button>
              </div>
            )}
          </Panel>
        )}
      </div>
    </div>
  )
}

function LinkRow({ label, url }: { label: string; url: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="mb-2 text-[13px]">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className="flex items-center gap-2">
        <a href={url} className="min-w-0 truncate text-primary-text hover:underline">{url}</a>
        <button type="button" className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="Copy link"
          onClick={() => navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })}>
          {copied ? <span className="text-[12px]">Copied</span> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
  )
}

function NoteForm({ busy, onSubmit }: { busy: boolean; onSubmit: (note: string) => Promise<unknown> }) {
  const [note, setNote] = useState("")
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (note.trim()) void onSubmit(note.trim()).then(() => setNote("")) }} className="flex gap-2">
      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note" aria-label="Add a note" maxLength={5000} className="h-8 text-[13px]" />
      <Button type="submit" size="sm" disabled={busy || !note.trim()}>Add</Button>
    </form>
  )
}

function TeamAddForm({ x, busy, onSubmit }: { x: ProjectExtras; busy: boolean; onSubmit: (f: Record<string, string>) => Promise<unknown> }) {
  const [userId, setUserId] = useState("")
  const [role, setRole] = useState(x.roles[0] ?? "")
  const candidates = x.users.filter((u) => u.id !== x.owner_id)
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (userId) void onSubmit({ user_id: userId, role }).then(() => setUserId("")) }} className="flex flex-wrap items-center gap-2">
      <select value={userId} onChange={(e) => setUserId(e.target.value)} aria-label="Add a person" className={cn(selectClass, "min-w-40")}>
        <option value="">Add a person…</option>
        {candidates.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
      </select>
      <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" className={selectClass}>
        {x.roles.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <Button type="submit" size="sm" variant="outline" disabled={busy || !userId}>Add</Button>
    </form>
  )
}

function InviteForm({ x, busy, onSubmit }: { x: ProjectExtras; busy: boolean; onSubmit: (f: Record<string, string>) => Promise<unknown> }) {
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [role, setRole] = useState(x.external_roles[0] ?? "")
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (email) void onSubmit({ email, name, role }).then(() => { setEmail(""); setName("") }) }} className="flex flex-wrap items-center gap-2">
      <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Invite by email" aria-label="Invite by email" required className="h-8 w-56 text-[13px]" />
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" aria-label="Name" maxLength={80} className="h-8 w-36 text-[13px]" />
      <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Their role" className={selectClass}>
        {x.external_roles.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <Button type="submit" size="sm" variant="outline" disabled={busy || !email}>Invite</Button>
    </form>
  )
}

function UploadForm({ x, busy, onSubmit }: { x: ProjectExtras; busy: boolean; onSubmit: (fd: FormData) => Promise<unknown> }) {
  const [category, setCategory] = useState("")
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    if (!category || !(fd.get("file") as File | null)?.name) return
    void onSubmit(fd).then(() => { e.currentTarget?.reset?.(); setCategory("") })
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <select name="category" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Document category" required className={selectClass}>
        <option value="">Category…</option>
        {x.doc_categories.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <input type="file" name="file" required aria-label="Document to upload" className="text-[12.5px] file:mr-2 file:rounded-md file:border file:border-border file:bg-background file:px-2 file:py-1 file:text-[12.5px] file:font-medium" />
      <Button type="submit" size="sm" variant="outline" disabled={busy}>Upload</Button>
    </form>
  )
}

