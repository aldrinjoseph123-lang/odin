import { useCallback, useEffect, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { Printer } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { PrintBrand } from "@/components/Brand"
import { Button, buttonVariants } from "@/components/ui/button"
import { ApiError, postForm, report, type ReportData, type User } from "@/lib/api"
import { groupBlocks } from "@/lib/format"
import { useUnsavedGuard } from "@/lib/useUnsavedGuard"
import { PageSkeleton } from "@/components/PageSkeleton"

const fmt = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString([], { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })

// The saved body is plain text with two conventions: "# " heads a section,
// "- " is a list item. Rendered here exactly as the Jinja page did.
function Blocks({ blocks }: { blocks: ReportData["blocks"] }) {
  return (
    <div className="text-[13px] leading-relaxed">
      {groupBlocks(blocks).map((b, i) =>
        b.kind === "ul" ? <ul key={i} className="my-1.5 list-disc pl-5">{b.items.map((t, j) => <li key={j} className="my-0.5 whitespace-pre-wrap">{t}</li>)}</ul>
        : b.kind === "h" ? <h2 key={i} className="mt-5 border-b border-border pb-1 text-[13px] font-semibold first:mt-0">{b.text}</h2>
        : <p key={i} className="my-1.5 whitespace-pre-wrap">{b.text}</p>)}
    </div>
  )
}

export default function Report(_props: { user: User }) {
  const id = Number(useParams().id)
  const [params, setParams] = useSearchParams()
  const [d, setD] = useState<ReportData | null>(null)
  const [text, setText] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const query = params.toString()
  useUnsavedGuard(editing && !!d && text !== d.editor_text)
  const load = useCallback(async () => {
    try {
      const r = await report(id, query)
      setD(r); setText(r.editor_text); setEditing(r.is_draft && r.can_edit); setError(null)
      document.title = `Report · ${r.project.name} · Odin`
    } catch (e) { setError(e instanceof ApiError && e.status === 404 ? "No such report version." : e instanceof ApiError ? e.message : "Could not load the report") }
  }, [id, query])
  useEffect(() => { void load() }, [load])
  async function save() {
    setBusy(true)
    try {
      const r = await postForm(`/projects/${id}/report/save`, { body: text })
      setNotice(r.messages.join(" ") || null)
      setParams({})            // the newest version is the default view
      await load()
    } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <PageSkeleton />
  const next = (d.versions[0]?.version ?? 0) + 1
  return (
    <div className="mx-auto max-w-3xl px-5 pb-8 pt-4">
      <PrintBrand />
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <a href={`/projects/${id}`} className="text-[12.5px] text-muted-foreground hover:text-foreground">{d.project.name}</a>
        <span className="text-[12.5px] text-muted-foreground">/ Report</span>
        {d.versions.length > 0 && (
          <select value={d.current?.version ?? ""} onChange={(e) => setParams({ v: e.target.value })} aria-label="Report version" className="ml-2 h-7 rounded-md border border-border bg-background px-2 text-[12.5px]">
            {d.versions.map((v) => <option key={v.version} value={v.version}>v{v.version} · {v.created_by} · {fmt(v.created_at)}</option>)}
          </select>
        )}
        {d.can_edit && d.versions.length > 0 && !d.is_draft && <button type="button" onClick={() => setParams({ draft: "1" })} className={buttonVariants({ variant: "ghost", size: "sm" })}>Regenerate draft</button>}
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => window.print()}><Printer className="h-3.5 w-3.5" /> Print / save as PDF</Button>
      </div>
      {notice && <div className="mt-3 flex items-center justify-between rounded-md bg-muted px-3 py-1.5 text-[12.5px] print:hidden" role="status"><span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}
      {d.is_draft && d.can_edit && (
        <p className="mt-3 text-[12.5px] text-muted-foreground print:hidden">{d.versions.length ? "Fresh draft from today's data — nothing is saved until you click Save." : "No report saved yet. This draft comes from the timeline, tasks, notes and documents; edit it and save the first version. Partners and customers see saved versions only."}</p>
      )}
      <div className="mt-4">
        {d.blocks.length ? <Blocks blocks={d.blocks} /> : <p className="text-[13px] text-muted-foreground">No report has been published for this project yet.</p>}
      </div>
      {d.can_edit && (
        <div className="mt-6 border-t border-border pt-4 print:hidden">
          {editing ? (
            <>
              <p className="mb-2 text-[12px] text-muted-foreground">Plain text. A line starting with <code className="font-mono">#&nbsp;</code> is a heading, <code className="font-mono">-&nbsp;</code> a list item. Saving creates version {next}; earlier versions stay.</p>
              <textarea value={text} onChange={(e) => setText(e.target.value)} aria-label="Report text" maxLength={50000} className="min-h-[28rem] w-full rounded-lg border border-input bg-background p-3 font-mono text-[12.5px] leading-relaxed" />
              <div className="mt-2 flex gap-2">
                <Button size="sm" onClick={save} disabled={busy || !text.trim()}>Save as version {next}</Button>
                {!d.is_draft && <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setText(d.editor_text) }}>Cancel</Button>}
              </div>
            </>
          ) : <Button size="sm" variant="outline" onClick={() => setEditing(true)}>Edit report</Button>}
        </div>
      )}
      {d.current && <p className="mt-6 text-[11.5px] text-muted-foreground">Version {d.current.version} · {d.current.created_by} · {fmt(d.current.created_at)}</p>}
    </div>
  )
}
