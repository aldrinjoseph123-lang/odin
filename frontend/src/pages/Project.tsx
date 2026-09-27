import { useCallback, useEffect, useState, type ReactNode } from "react"
import { useParams } from "react-router-dom"
import { Copy, Trash2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { UserAvatar } from "@/components/UserAvatar"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Detail } from "@/pages/Flow"
import { StageListEditor, stageRowsKey } from "@/components/StageListEditor"
import { ApiError, flowDetail, postForm, projectActivity, projectExtras, type ActivityRow, type FlowDetail, type FormReply, type ProjectExtras, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { PageSkeleton } from "@/components/PageSkeleton"

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
      <h3 data-n className="mb-3 text-[12px] font-semibold text-nav-fg">{title}{hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}</h3>
      {children}
    </section>
  )
}

export default function Project(_props: { user: User }) {
  const id = Number(useParams().id)
  const [d, setD] = useState<FlowDetail | null>(null)
  const [x, setX] = useState<ProjectExtras | null>(null)
  const [activity, setActivity] = useState<ActivityRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ text: string; undo?: string | null } | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [fd, ex, act] = await Promise.all([flowDetail(id), projectExtras(id), projectActivity(id)])
      setD(fd); setX(ex); setActivity(act.rows); setError(null)
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
  if (!d || !x) return <PageSkeleton />
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

      <div className="grid gap-4 px-5 pb-6 lg:grid-cols-2 [&>*]:min-w-0">
        <Panel title="Details">
          <dl className="grid grid-cols-[minmax(96px,auto)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[13px] [&_dd]:min-w-0 [&_dd]:break-words">
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
          {can.note && <NoteForm busy={busy} people={x.participants.filter((m) => m.active).map((m) => m.name)} onSubmit={(note) => send(`/projects/${id}/note`, { note })} />}
          <ul className="mt-3 grid gap-2">
            {x.notes.map((n) => <NoteRow key={`${n.id}:${n.note}`} n={n} busy={busy}
              onEdit={(text) => send(`/projects/${id}/notes/${n.id}/edit`, { note: text })}
              onDelete={() => send(`/projects/${id}/notes/${n.id}/delete`, {}, "Delete this note?")} />)}
            {x.notes.length === 0 && <li className="text-[13px] text-muted-foreground">No notes yet.</li>}
          </ul>
        </Panel>

        <Panel title="Team" hint="who is on this project, and as what" id="team">
          <ul className="grid gap-1.5">
            {x.participants.map((m) => (
              <li key={m.id} className="flex items-center gap-2 text-[13px]">
                <UserAvatar name={m.name} url={m.avatar_url} />
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
            <StageListEditor key={stageRowsKey(x.stage_rows)} rows={x.stage_rows} current={d.stage} busy={busy} send={send}
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

        {activity.length > 0 && (
          <Panel title="Activity" hint="everything recorded on this project, newest first">
            <a href={`/projects/${id}/activity.csv`} className="mb-2 inline-block text-[12px] text-primary-text hover:underline">Export CSV</a>
            <ul className="grid gap-1.5 text-[12.5px]">
              {activity.map((a, i) => (
                <li key={i} className="flex gap-2">
                  <Ago iso={a.when} className="w-24 shrink-0 whitespace-nowrap text-muted-foreground" />
                  <span className="min-w-0 break-words"><span className="font-medium">{a.who}</span> {a.label}{a.details && <span className="text-muted-foreground"> · {a.details}</span>}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
        {(x.guest_links.customer || can.manage) && (
          <Panel title="Sharing">
            {x.guest_links.customer && <LinkRow label="Customer link (view and comment, no sign-in)" url={x.guest_links.customer} />}
            {x.guest_links.vendor && <LinkRow label="Vendor link (may advance the stage)" url={x.guest_links.vendor} />}
            {!x.guest_links_enabled && <p className="text-[12.5px] text-muted-foreground">Anonymous guest links are switched off in Settings. Partners and customers are invited from the Team panel instead.</p>}
            {can.manage && (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
                {x.guest_links_enabled && <Button size="sm" variant="outline" disabled={busy} onClick={() => send(`/projects/${id}/rotate-token`, {}, "Rotate both guest links? The current links stop working immediately.")}>Rotate guest links</Button>}
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

function NoteRow({ n, busy, onEdit, onDelete }: { n: ProjectExtras["notes"][number]; busy: boolean; onEdit: (text: string) => Promise<unknown>; onDelete: () => Promise<unknown> }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(n.note)
  return (
    <li className="group border-t border-border pt-2 text-[13px] first:border-0 first:pt-0">
      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <span><span className="font-medium text-foreground">{n.author}</span> · {n.stage} · <Ago iso={n.created_at} />{n.edited && " · edited"}</span>
        {n.mine && !editing && (
          <span className="ml-auto flex gap-2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <button type="button" onClick={() => setEditing(true)} className="hover:text-foreground">Edit</button>
            {!n.stage_entry && <button type="button" disabled={busy} onClick={() => void onDelete()} className="hover:text-bad">Delete</button>}
          </span>
        )}
      </div>
      {editing ? (
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) void onEdit(text.trim()).then(() => setEditing(false)) }} className="mt-1 grid gap-1.5">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={5000} aria-label="Edit note" autoFocus
            className="w-full rounded-md border border-input bg-background p-2 text-[13px]" onKeyDown={(e) => { if (e.key === "Escape") { setEditing(false); setText(n.note) } }} />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy || !text.trim() || text.trim() === n.note}>Save</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => { setEditing(false); setText(n.note) }}>Cancel</Button>
            {n.stage_entry && <span className="self-center text-[11.5px] text-muted-foreground">Records a stage change: it can be corrected, not deleted.</span>}
          </div>
        </form>
      ) : <div className="whitespace-pre-wrap">{n.note}</div>}
    </li>
  )
}

function NoteForm({ busy, people, onSubmit }: { busy: boolean; people: string[]; onSubmit: (note: string) => Promise<unknown> }) {
  const [note, setNote] = useState("")
  // "@" + letters at the end of the text offers the team; picking one writes "@Full Name "
  const token = /(^|\s)@([^\s@]*)$/.exec(note)
  const matches = token ? people.filter((n) => n.toLowerCase().includes(token[2].toLowerCase())).slice(0, 6) : []
  function pick(name: string) { setNote(note.slice(0, note.length - (token?.[2].length ?? 0) - 1) + `@${name} `) }
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (note.trim()) void onSubmit(note.trim()).then(() => setNote("")) }} className="relative">
      <div className="flex gap-2">
        <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note — type @ to notify someone on the team" aria-label="Add a note" maxLength={5000} className="h-8 text-[13px]"
          onKeyDown={(e) => { if (e.key === "Enter" && matches.length) { e.preventDefault(); pick(matches[0]) } }} />
        <Button type="submit" size="sm" disabled={busy || !note.trim()}>Add</Button>
      </div>
      {matches.length > 0 && (
        <ul role="listbox" aria-label="Mention someone" className="absolute left-0 top-9 z-20 w-64 overflow-hidden rounded-lg border border-border bg-popover py-1 text-[13px] shadow-lg">
          {matches.map((n) => <li key={n} role="option" aria-selected={false}><button type="button" onClick={() => pick(n)} className="w-full px-3 py-1.5 text-left hover:bg-muted">@{n}</button></li>)}
        </ul>
      )}
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
  const [files, setFiles] = useState<File[]>([])
  const [over, setOver] = useState(false)
  // One POST per file through the same route, so each keeps its own checks and audit row.
  async function upload() {
    if (!category || !files.length) return
    for (const f of files) {
      const fd = new FormData(); fd.append("category", category); fd.append("file", f)
      await onSubmit(fd)
    }
    setFiles([])
  }
  return (
    <div onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); setFiles([...e.dataTransfer.files]) }}
      className={cn("grid gap-2 rounded-lg border border-dashed p-3 transition-colors", over ? "border-primary bg-accent/40" : "border-border")}>
      <div className="flex flex-wrap items-center gap-2">
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Document category" className={selectClass}>
          <option value="">Category…</option>
          {x.doc_categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="cursor-pointer text-[12.5px] font-medium text-primary-text hover:underline">
          Choose files<input type="file" multiple aria-label="Documents to upload" className="sr-only" onChange={(e) => setFiles([...(e.target.files ?? [])])} />
        </label>
        <span className="text-[12px] text-muted-foreground">or drop them here</span>
        <Button type="button" size="sm" variant="outline" className="ml-auto" disabled={busy || !category || !files.length} onClick={() => void upload()}>
          Upload{files.length > 1 ? ` ${files.length} files` : ""}
        </Button>
      </div>
      {files.length > 0 && <p className="truncate text-[12px] text-muted-foreground">{files.map((f) => f.name).join(", ")}{!category && " — pick a category first"}</p>}
    </div>
  )
}

