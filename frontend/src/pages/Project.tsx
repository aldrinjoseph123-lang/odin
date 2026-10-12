import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { PanelTitle } from "@/components/PanelTitle"
import { fieldAuto } from "@/lib/ui"
import { Link, useParams } from "react-router-dom"
import { Copy, MoreHorizontal, Trash2 } from "lucide-react"
import { askConfirm } from "@/lib/confirm"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { RagPill } from "@/components/PlanGantt"
import { UserAvatar } from "@/components/UserAvatar"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Detail } from "@/pages/Flow"
import { StageListEditor, stageRowsKey } from "@/components/StageListEditor"
import { PlanPanel } from "@/components/PlanPanel"
import { RaidPanel } from "@/components/RaidPanel"
import { ScopePanel } from "@/components/ScopePanel"
import { AIChase } from "@/components/AIChase"
import { AICatchUp } from "@/components/AICatchUp"
import { AIAsk } from "@/components/AIAsk"
import { AINotesTasks } from "@/components/AINotesTasks"
import { LessonsPanel } from "@/components/LessonsPanel"
import { ApiError, flowDetail, plan, postForm, projectActivity, projectExtras, type ActivityRow, type FlowDetail, type FormReply, type PlanData, type ProjectExtras, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb"
import { dayBucket, fmtDate, fmtWhen } from "@/lib/format"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

// a 14 px bin with a 24 px target (the pseudo-element), kept clear of its neighbours
const hit = "relative ml-1 shrink-0 text-muted-foreground before:absolute before:-inset-[5px] before:content-[''] hover:text-destructive"
const LABELS: Record<string, string> = {
  client: "Client", via: "Via", partner_name: "Partner", partner_account_manager_name: "Account manager (partner)", account_manager_name: "Account manager",
  po_number: "PO number", po_date: "PO date", start_date: "Start date", target_end_date: "Target end date", delivery_mode: "Delivery mode",
  outsourcer_name: "Outsourcer", vendor_name: "Vendor", product_name: "Product",
}

function Panel({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="panel scroll-mt-16 p-4">
      <PanelTitle hint={hint}>{title}</PanelTitle>
      {children}
    </section>
  )
}

export default function Project({ user }: { user: User }) {
  const id = Number(useParams().id)
  const [d, setD] = useState<FlowDetail | null>(null)
  const [x, setX] = useState<ProjectExtras | null>(null)
  const [activity, setActivity] = useState<ActivityRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ text: string; undo?: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [planRefresh, setPlanRefresh] = useState(0)   // a RAID change or a stage move moves the plan and the health
  const stageSeen = useRef<string | null>(null)
  const [health, setHealth] = useState<PlanData["health"] | null>(null)
  useEffect(() => { plan(id).then((p) => setHealth(p.health)).catch(() => setHealth(null)) }, [id, planRefresh])
  const [adding, setAdding] = useState(false)
  const [editStages, setEditStages] = useState(false)
  const [allNotes, setAllNotes] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [fd, ex, act] = await Promise.all([flowDetail(id), projectExtras(id), projectActivity(id)])
      // a stage move (or its undo) redraws the panels that read the stage, not only the header (sim PM-3)
      if (stageSeen.current !== null && stageSeen.current !== fd.stage) setPlanRefresh((n) => n + 1)
      stageSeen.current = fd.stage
      setD(fd); setX(ex); setActivity(act.rows); setError(null)
    } catch (e) { setError(e instanceof ApiError && e.status === 404 ? "This rollout does not exist, or you are not on it." : e instanceof ApiError ? e.message : "Could not load the rollout") }
  }, [id])
  useEffect(() => { void reload() }, [reload])
  useEffect(() => { document.title = x ? `${x.name} · Odin` : error ? "Rollout not found · Odin" : "Rollout · Odin" }, [x, error])

  // one door for every form post: show what Flask said, then refetch
  async function send(path: string, fields: Record<string, string> | FormData = {}, confirmText?: string): Promise<FormReply | null> {
    if (confirmText && !(await askConfirm(confirmText))) return null
    setBusy(true)
    let leaving = false
    try {
      const r = await postForm(path, fields)
      if (r.location === "/board") { leaving = true; window.location.assign("/board"); return r }
      setNotice(r.messages.length ? { text: r.messages.join(" "), undo: r.undo } : null)
      await reload()
      return r
    } catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That did not save" }); return null } finally { if (!leaving) setBusy(false) }
  }
  async function undo() {
    if (!notice?.undo) return
    await send(notice.undo)
  }

  if (error) return <LoadError message={error} back={error === "This rollout does not exist, or you are not on it." ? { href: "/projects", label: "All rollouts" } : undefined} />
  if (!d || !x) return <PageSkeleton />
  const can = x.can
  const staff = user.kind !== "external"
  const closed = !d.next_stage && d.stage_index === d.stages.length - 1

  return (
    <div>
      {/* the window scrolls (not this box), so the section index and the reply bar can stick */}
      <div className="flex flex-wrap items-center gap-2 px-5 pt-4">
        <Breadcrumb className="min-w-0 text-[13px]">
          <BreadcrumbList>
            <BreadcrumbItem><BreadcrumbLink render={<Link to="/projects" />}>Rollouts</BreadcrumbLink></BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem className="min-w-0"><BreadcrumbPage className="truncate" title={x.name}>{x.name}</BreadcrumbPage></BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        {/* health first: the plan's verdict and its main reason, in the title row (critique 10 Oct) */}
        {/* the plan already counts overdue and over-SLA; "due soon" is the schedule's alone, so show the worse of the two */}
        {health && (() => {
          const due = d.state === "due_soon" && health.rag === "green"
          const reasons = due ? [`Due ${fmtDate(d.target_end_date)}.`] : health.reasons
          return <span className="flex min-w-0 items-center gap-2"><RagPill rag={due ? "amber" : health.rag} />{reasons[0] && <span className="truncate text-[13px] text-muted-foreground" title={reasons.join(" · ")}>{reasons[0]}</span>}</span>
        })()}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <a href={`/board?rollout=${id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}>On the flow</a>
          <a href={`/projects/${id}/report`} className={buttonVariants({ variant: "ghost", size: "sm" })}>Report</a>
          {can.create && <a href={`/projects/new?from=${id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>Duplicate</a>}
          {can.manage && <a href={`/projects/${id}/edit`} className={buttonVariants({ variant: "outline", size: "sm" })}>Edit</a>}
          {/* the rare and the destructive live behind ⋯, not at the end of the page */}
          {can.manage && (x.guest_links_enabled || can.delete_project) && (
            <DropdownMenu>
              <DropdownMenuTrigger render={<button type="button" />} disabled={busy} aria-label="More actions" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "px-2")}><MoreHorizontal className="h-4 w-4" /></DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                {x.guest_links_enabled && <DropdownMenuItem onClick={() => send(`/projects/${id}/rotate-token`, {}, "Rotate both guest links? The current links stop working at once; anyone using them needs the new ones.")}>Rotate guest links</DropdownMenuItem>}
                {can.delete_project && <DropdownMenuItem variant="destructive" onClick={() => send(`/projects/${id}/delete`, {}, "Delete this project? It leaves every list at once; you have five minutes to undo.")}>Delete project</DropdownMenuItem>}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
      {/* the page is long: one row of anchors to every section, always in reach */}
      <nav aria-label="Sections of this rollout" className="sticky top-0 z-20 mt-2 flex gap-1 overflow-x-auto bg-background/95 px-5 py-2 text-[13px] backdrop-blur">
        {[["notes", "Notes"], ["plan", "Plan"], ["raid", "Risks & issues"], ["scope", "Scope & sign-off"], ["details", "Details"], ["team", "Team"],
          ...(can.manage ? [["stages", "Stages"]] : []), ["documents", "Documents"], ...(activity.length ? [["activity", "Activity"]] : []),
          ...((x.guest_links.customer || can.manage) ? [["sharing", "Sharing"]] : [])].map(([k, label]) => (
          <a key={k} href={`#${k}`} className="shrink-0 rounded-full px-3 py-1 text-nav-fg outline-none hover:bg-muted hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50">{label}</a>
        ))}
      </nav>
      {/* sticky: a reply to the Team or Notes panel far down the page (an invite link) shows where the person is */}
      {notice && (
        <div className="sticky top-14 z-20 mx-5 mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-2 text-[13px] shadow-card" role="status">
          <span>{notice.text}{notice.undo && <button type="button" onClick={undo} className="ml-2 font-medium text-primary-text hover:underline">Undo</button>}</span>
          <button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* the same detail as the flow screen: flowchart, tasks per stage, rail */}
      <Detail d={d} reload={reload} onMoved={(m, undo) => { setNotice({ text: m, undo }); void reload() }} standalone />

      <div className="grid grid-cols-1 gap-4 px-5 pb-4 [&>*]:min-w-0">
        <div className="empty:hidden"><AICatchUp projectId={id} /></div>
        <div className="empty:hidden"><AIAsk projectId={id} /></div>
        <div className="empty:hidden"><AINotesTasks projectId={id} /></div>
        {!closed && <div className="empty:hidden"><AIChase key={planRefresh} projectId={id} /></div>}
        {/* the project manager's daily write sits high, right under the flow (critique 10 Oct) */}
        <div><Panel title="Notes" hint={`${x.notes.length}`} id="notes">
          {can.note && <NoteForm busy={busy} staff={staff} people={x.participants.filter((m) => m.active).map((m) => m.name)}
            onSubmit={(note, share) => send(`/projects/${id}/note`, share ? { note, share: "1" } : { note })} />}
          <ul className="mt-3 grid grid-cols-1 gap-2">
            {(allNotes ? x.notes : x.notes.slice(0, 5)).map((n) => <NoteRow key={`${n.id}:${n.note}`} n={n} busy={busy}
              onEdit={(text) => send(`/projects/${id}/notes/${n.id}/edit`, { note: text })}
              onDelete={() => send(`/projects/${id}/notes/${n.id}/delete`, {}, "Delete this note? It leaves the rollout's history.")} />)}
            {x.notes.length === 0 && <li className="text-[13px] text-muted-foreground">No notes yet.</li>}
            {x.notes.length > 5 && <li><button type="button" onClick={() => setAllNotes(!allNotes)} className="text-[12px] text-muted-foreground hover:text-foreground">{allNotes ? "Show the latest 5" : `Show all ${x.notes.length}`}</button></li>}
          </ul>
        </Panel></div>
        <div><Panel title="Plan" hint="dates per stage, the baseline, and the forecast" id="plan"><PlanPanel projectId={id} refresh={planRefresh} /></Panel></div>
        <div><Panel title="Risks, issues, decisions, blockers" id="raid"><RaidPanel projectId={id} onChanged={() => setPlanRefresh((n) => n + 1)} /></Panel></div>
        {staff && <div className="empty:hidden"><LessonsPanel projectId={id} /></div>}
        <div><Panel title="Scope and sign-off" hint="what was agreed, what was delivered, and the customer's signature" id="scope"><ScopePanel projectId={id} signoff={d.signoff} /></Panel></div>
      </div>
      {/* the half-width panels as a masonry: two columns from lg, each panel
          under the one above it, so a short panel never leaves a gap */}
      <div className="gap-4 px-5 pb-6 lg:columns-2 [&>*]:mb-4 [&>*]:min-w-0 [&>*]:break-inside-avoid">
        <Panel title="Details" id="details">
          <dl className="grid grid-cols-[minmax(96px,auto)_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px] [&_dd]:min-w-0 [&_dd]:break-words">
            {Object.entries(LABELS).filter(([k]) => !!x.details[k]).filter(([k]) => {
              const via = x.details.via
              if (k === "partner_name" || k === "partner_account_manager_name") return via === "Partner"
              if (k === "account_manager_name") return via !== "Partner"
              if (k === "outsourcer_name") return x.details.delivery_mode === "Outsourced"
              if (k === "vendor_name" || k === "product_name") return x.details.delivery_mode !== "Outsourced"
              return true   // empty fields are already out: they say nothing, and Edit shows them all
            }).map(([k, label]) => {
              const email = k === "account_manager_name" ? x.details.account_manager_email : k === "partner_account_manager_name" ? x.details.partner_account_manager_email : k === "outsourcer_name" ? x.details.outsourcer_email : null
              return <div key={k} className="contents"><dt className="text-muted-foreground">{label}</dt><dd>{k.endsWith("_date") && x.details[k] ? fmtWhen(x.details[k]) : (x.details[k] ?? "—")}{email ? <span className="text-muted-foreground"> · {email}</span> : null}</dd></div>
            })}
            <dt className="text-muted-foreground">Customer approval</dt><dd>{x.customer_approval ? "Asked on every stage change" : "Off"}</dd>
          </dl>
        </Panel>

        <Panel title="Team" hint="who is on this rollout, and as what" id="team">
          <ul className="grid grid-cols-1 gap-2">
            {x.participants.map((m) => (
              <li key={m.id} className="group flex items-center gap-2 text-[13px]">
                <UserAvatar name={m.name} url={m.avatar_url} />
                <span className="min-w-0 flex-1 truncate font-medium" title={m.name}>{m.name}{!m.active && <span className="ml-1 font-normal text-muted-foreground">(deactivated)</span>}</span>
                <span className="text-muted-foreground">{m.role}</span>
                {m.email && <span className="hidden text-[12px] text-muted-foreground sm:inline">{m.email}</span>}
                {can.manage && m.user_id !== x.owner_id && (
                  <button type="button" disabled={busy} onClick={() => send(`/projects/${id}/participants/${m.id}/remove`, {}, `Remove ${m.name} from this rollout? They lose access to it and stop hearing about it; their notes and tasks stay.`)} aria-label={`Remove ${m.name}`} className={cn(hit, "opacity-0 focus:opacity-100 group-hover:opacity-100")}><Trash2 className="h-3.5 w-3.5" /></button>
                )}
              </li>
            ))}
          </ul>
          {can.manage && (adding ? (
            <div className="mt-3 grid grid-cols-1 gap-2 border-t border-border pt-3">
              <TeamAddForm x={x} busy={busy} onSubmit={(f) => send(`/projects/${id}/participants/add`, f)} />
              <InviteForm x={x} busy={busy} onSubmit={(f) => send(`/projects/${id}/participants/invite`, f)} />
              <p className="max-w-prose text-[12px] text-muted-foreground">The owner is the project manager; change it on Edit. Invited people get a one-time sign-in link and see only their rollouts.</p>
              <button type="button" onClick={() => setAdding(false)} className="justify-self-start text-[12px] text-muted-foreground hover:text-foreground">Done</button>
            </div>
          ) : <Button size="sm" variant="outline" className="mt-3" onClick={() => setAdding(true)}>Add people</Button>)}
        </Panel>

        {can.manage && (
          <Panel title="This rollout's stages" hint="only this rollout changes" id="stages">
            {/* configuration is rare: a summary until someone asks to edit */}
            {!editStages ? (
              <div className="flex flex-wrap items-center gap-3 text-[13px]">
                <span className="min-w-0 flex-1 text-muted-foreground">{x.stage_rows.length} stages: {x.stage_rows.map((r) => r.name).join(" › ")}</span>
                <Button size="sm" variant="outline" onClick={() => setEditStages(true)}>Edit stages</Button>
              </div>
            ) : <><button type="button" onClick={() => setEditStages(false)} className="mb-2 text-[12px] text-muted-foreground hover:text-foreground">Done editing</button><StageListEditor key={stageRowsKey(x.stage_rows)} rows={x.stage_rows} current={d.stage} busy={busy} send={send}
              paths={{ add: `/projects/${id}/stages/add`, rename: (s) => `/projects/${id}/stages/${s}/rename`, move: (s) => `/projects/${id}/stages/${s}/move`, remove: (s) => `/projects/${id}/stages/${s}/delete`, sla: `/projects/${id}/stages/sla` }} /></>}
          </Panel>
        )}

        <Panel title="Documents" hint={`${x.documents.length}`} id="documents">
          {can.docs && <UploadForm x={x} busy={busy} onSubmit={(fd) => send(`/projects/${id}/documents`, fd)} />}
          <ul className="mt-3 grid grid-cols-1 gap-2">
            {x.documents.map((doc) => (
              <li key={doc.id} className="flex items-center gap-3 text-[13px]">
                <span className="w-28 shrink-0 truncate text-[12px] text-muted-foreground">{doc.category}</span>
                {can.download ? <a href={`/projects/${id}/documents/${doc.id}/download`} className="min-w-0 flex-1 truncate font-medium hover:underline">{doc.filename}</a> : <span className="min-w-0 flex-1 truncate font-medium">{doc.filename}</span>}
                <span className="hidden text-[12px] text-muted-foreground sm:inline">{doc.uploaded_by} · {fmtWhen(doc.uploaded_at)}</span>
                {can.delete_doc && <button type="button" disabled={busy} onClick={() => send(`/projects/${id}/documents/${doc.id}/delete`, {}, `Delete ${doc.filename}? The file is removed for everyone on the rollout.`)} aria-label={`Delete ${doc.filename}`} className={hit}><Trash2 className="h-3.5 w-3.5" /></button>}
              </li>
            ))}
            {x.documents.length === 0 && <li className="text-[13px] text-muted-foreground">No documents uploaded yet.</li>}
          </ul>
        </Panel>

        {activity.length > 0 && (
          <Panel title="Activity" hint="newest first" id="activity">
            <a href={`/projects/${id}/activity.csv`} className="mb-2 inline-block text-[12px] text-primary-text hover:underline">Export CSV</a>
            <ul className="grid grid-cols-1 gap-2 text-[13px]">
              {activity.map((a, i) => {
                const day = dayBucket(a.when)
                return (
                  <li key={i} className="grid grid-cols-1 gap-2">
                    {/* chunked by day, so a run of "1 min ago" reads as one group */}
                    {(i === 0 || dayBucket(activity[i - 1].when) !== day) && <span className="rounded-md bg-muted/60 px-2 py-1 text-[12px] font-semibold text-nav-fg">{day}</span>}
                    <span className="flex gap-2">
                      <Ago iso={a.when} className="w-24 shrink-0 whitespace-nowrap text-muted-foreground" />
                      <span className="min-w-0 break-words"><span className="font-medium">{a.who}</span> {a.label}{a.details && <span className="text-muted-foreground"> · {a.details.replace(/\b([a-z_]+)=/g, (_, k: string) => `${k.replace(/_/g, " ")} `)}</span>}</span>
                    </span>
                  </li>
                )
              })}
            </ul>
          </Panel>
        )}
        {(x.guest_links.customer || can.manage) && (
          <Panel title="Sharing" id="sharing">
            {x.guest_links.customer && <LinkRow label="Customer link (view and comment, no sign-in)" url={x.guest_links.customer} />}
            {x.guest_links.vendor && <LinkRow label="Vendor link (may advance the stage)" url={x.guest_links.vendor} />}
            {!x.guest_links_enabled && <p className="text-[13px] text-muted-foreground">Anonymous guest links are switched off in Settings. Partners and customers are invited from the Team panel instead.</p>}
            {can.manage && x.guest_links_enabled && <p className="mt-2 text-[12px] text-muted-foreground">Rotate the links from More actions at the top of the page.</p>}
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
        <button type="button" className="shrink-0 text-muted-foreground hover:text-foreground" aria-label={`Copy the ${label.split(" (")[0].toLowerCase()}`}
          onClick={() => navigator.clipboard?.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })}>
          {copied ? <span className="text-[12px]">Copied</span> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
  )
}

function NoteRow({ n, busy, onEdit, onDelete }: { n: ProjectExtras["notes"][number]; busy: boolean; onEdit: (text: string) => Promise<FormReply | null>; onDelete: () => Promise<unknown> }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(n.note)
  return (
    <li className="group border-t border-border pt-2 text-[13px] first:border-0 first:pt-0">
      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <span><span className="font-medium text-foreground">{n.author}</span> · {n.stage} · <Ago iso={n.created_at} />{n.edited && " · edited"}</span>
        {n.mine && !editing && (
          <span className="ml-auto flex gap-2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <button type="button" onClick={() => setEditing(true)} className="hover:text-foreground">Edit</button>
            {!n.stage_entry && <button type="button" disabled={busy} onClick={() => void onDelete()} className="hover:text-destructive">Delete</button>}
          </span>
        )}
      </div>
      {editing ? (
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) void onEdit(text.trim()).then((r) => { if (r) setEditing(false) }) }} className="mt-1 grid grid-cols-1 gap-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={5000} aria-label="Edit note" autoFocus
            className="w-full rounded-md border border-input bg-background p-2 text-[13px]" onKeyDown={(e) => { if (e.key === "Escape") { setEditing(false); setText(n.note) } }} />
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={busy} disabled={!text.trim() || text.trim() === n.note}>Save</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => { setEditing(false); setText(n.note) }}>Cancel</Button>
            {n.stage_entry && <span className="self-center text-[12px] text-muted-foreground">Records a stage change: it can be corrected, not deleted.</span>}
          </div>
        </form>
      ) : <div className="whitespace-pre-wrap">{n.note}</div>}
    </li>
  )
}

// The note box. "@" + letters before the caret offers the team: ↑/↓ choose,
// Enter or a click writes "@Full Name " at the caret, Esc closes the list.
// Staff notes are internal unless shared with the customer and partners.
function NoteForm({ busy, staff, people, onSubmit }: { busy: boolean; staff: boolean; people: string[]; onSubmit: (note: string, share: boolean) => Promise<FormReply | null> }) {
  const [note, setNote] = useState("")
  const [share, setShare] = useState(false)
  const [caret, setCaret] = useState(0)
  const [active, setActive] = useState(0)
  const [closedAt, setClosedAt] = useState<string | null>(null)   // Esc hides the list until the text changes
  const ref = useRef<HTMLInputElement>(null)
  const before = note.slice(0, caret)
  const token = /(^|\s)@([^\s@]*)$/.exec(before)
  const matches = token && closedAt !== note ? people.filter((n) => n.toLowerCase().includes(token[2].toLowerCase())).slice(0, 6) : []
  const at = Math.min(active, Math.max(0, matches.length - 1))
  function pick(name: string) {
    const head = before.slice(0, before.length - (token?.[2].length ?? 0) - 1) + `@${name} `
    setNote(head + note.slice(caret)); setCaret(head.length); setActive(0)
    requestAnimationFrame(() => { ref.current?.focus(); ref.current?.setSelectionRange(head.length, head.length) })
  }
  const track = (e: { currentTarget: HTMLInputElement }) => setCaret(e.currentTarget.selectionStart ?? e.currentTarget.value.length)
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (note.trim()) void onSubmit(note.trim(), staff && share).then((r) => { if (r) { setNote(""); setCaret(0); setShare(false) } }) }} className="relative">
      <div className="flex gap-2">
        <Input ref={ref} value={note} onChange={(e) => { setNote(e.target.value); track(e); setActive(0) }} onSelect={track} placeholder="Add a note — type @ to notify someone on the team" aria-label="Add a note" maxLength={5000} className="h-8 text-[13px]"
          role="combobox" aria-autocomplete="list" aria-expanded={matches.length > 0} aria-controls="mention-list" aria-activedescendant={matches.length ? `mention-${at}` : undefined}
          onKeyDown={(e) => {
            if (!matches.length) return
            if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setActive((at + (e.key === "ArrowDown" ? 1 : matches.length - 1)) % matches.length) }
            else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pick(matches[at]) }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setClosedAt(note) }
          }} />
        <Button type="submit" size="sm" loading={busy} disabled={!note.trim()}>Add</Button>
      </div>
      {staff && (
        <label className="mt-2 flex items-center gap-2 text-[12px] text-muted-foreground">
          <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} className="h-3.5 w-3.5 accent-primary" /> Share with the customer
          {share ? <span className="font-medium text-foreground">· Visible to the customer and partners</span> : <span>· internal to the team</span>}
        </label>
      )}
      {matches.length > 0 && (
        <ul id="mention-list" role="listbox" aria-label="Mention someone" className="absolute left-0 top-9 z-20 w-64 overflow-hidden panel bg-popover py-1 text-[13px] shadow-pop">
          {matches.map((n, i) => (
            // mousedown is cancelled so the text box keeps its focus and caret
            <li key={n} id={`mention-${i}`} role="option" aria-selected={i === at} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(n)}
              className={cn("cursor-pointer px-3 py-2", i === at ? "bg-muted" : "hover:bg-muted")}>@{n}</li>
          ))}
        </ul>
      )}
    </form>
  )
}

// People not on the team yet come first; someone already on it can only have
// their role changed (the route updates an existing member's role).
function TeamAddForm({ x, busy, onSubmit }: { x: ProjectExtras; busy: boolean; onSubmit: (f: Record<string, string>) => Promise<FormReply | null> }) {
  const [userId, setUserId] = useState("")
  const [role, setRole] = useState(x.roles[0] ?? "")
  const onTeam = new Map(x.participants.map((m) => [m.user_id, m.role]))
  const candidates = x.users.filter((u) => u.id !== x.owner_id)
  const fresh = candidates.filter((u) => !onTeam.has(u.id)), members = candidates.filter((u) => onTeam.has(u.id))
  const member = onTeam.get(Number(userId))
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (userId) void onSubmit({ user_id: userId, role }).then((r) => { if (r) setUserId("") }) }} className="grid grid-cols-1 gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <select value={userId} onChange={(e) => setUserId(e.target.value)} aria-label="Add a person" className={cn(fieldAuto, "min-w-40")}>
          <option value="">Add a person…</option>
          {fresh.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          {members.length > 0 && <optgroup label="On the team: change their role">{members.map((u) => <option key={u.id} value={u.id}>{u.name} ({onTeam.get(u.id)})</option>)}</optgroup>}
        </select>
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" className={fieldAuto}>
          {x.roles.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <Button type="submit" size="sm" variant="outline" loading={busy} disabled={!userId || member === role}>{member ? "Change role" : "Add"}</Button>
      </div>
      <p className="text-[12px] text-muted-foreground">A rollout role adds no powers beyond the person's account: a Viewer stays read-only in any role.</p>
    </form>
  )
}

function InviteForm({ x, busy, onSubmit }: { x: ProjectExtras; busy: boolean; onSubmit: (f: Record<string, string>) => Promise<FormReply | null> }) {
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [role, setRole] = useState(x.external_roles[0] ?? "")
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (email) void onSubmit({ email, name, role }).then((r) => { if (r) { setEmail(""); setName("") } }) }} className="flex flex-wrap items-center gap-2">
      <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Invite by email" aria-label="Invite by email" required className="h-8 w-56 text-[13px]" />
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" aria-label="Name" maxLength={80} className="h-8 w-36 text-[13px]" />
      <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Their role" className={fieldAuto}>
        {x.external_roles.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <Button type="submit" size="sm" variant="outline" loading={busy} disabled={!email}>Invite</Button>
    </form>
  )
}

function UploadForm({ x, busy, onSubmit }: { x: ProjectExtras; busy: boolean; onSubmit: (fd: FormData) => Promise<FormReply | null> }) {
  const [category, setCategory] = useState("")
  const [files, setFiles] = useState<File[]>([])
  const [over, setOver] = useState(false)
  // One POST per file through the same route, so each keeps its own checks and audit row.
  async function upload() {
    if (!category || !files.length) return
    const left = [...files]
    while (left.length) {
      const fd = new FormData(); fd.append("category", category); fd.append("file", left[0])
      if (!(await onSubmit(fd))) break   // the failed file and the rest stay picked
      left.shift()
    }
    setFiles(left)
  }
  return (
    <div onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); setFiles([...e.dataTransfer.files]) }}
      className={cn("grid gap-2 rounded-lg border border-dashed p-3 transition-colors", over ? "border-primary bg-accent/40" : "border-border")}>
      <div className="flex flex-wrap items-center gap-2">
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Document category" className={fieldAuto}>
          <option value="">Category…</option>
          {x.doc_categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="cursor-pointer rounded-sm text-[13px] font-medium text-primary-text hover:underline has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50">
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

