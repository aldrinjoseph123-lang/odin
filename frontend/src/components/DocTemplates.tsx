import { useCallback, useEffect, useState } from "react"
import { ArrowDown, ArrowUp, Copy, Eye, FileText, ImageUp, Plus, Star, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  ApiError, defaultDocTemplate, deleteDocTemplate, docTemplates, previewDocTemplate, saveDocTemplate, uploadDocLogo,
  type DocConfig, type DocKind, type DocTemplate, type DocTemplatesData,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import { fmtWhen } from "@/lib/format"

// Settings → Documents: templates for the rollout report, the portfolio report
// and the sign-off. Brand (our logo, an optional customer logo, accent,
// company line, footer), sections on/off and in order, and text blocks with
// {placeholders}; a preview renders the unsaved template on real data.
// The swatches show the PDF's own colours (document data, not UI chrome).
const SWATCH: Record<string, string> = { blue: "#3D5AFE", indigo: "#4F46E5", teal: "#0D9488", green: "#16A34A", orange: "#EA580C", red: "#E11D2E", slate: "#334155", black: "#101114" }
const field = "h-8 w-full rounded-md border border-input bg-background px-2 text-[13px]"
const KINDS: DocKind[] = ["rollout", "signoff", "portfolio"]
type Editing = { id?: number; kind: DocKind; name: string; config: DocConfig }

export function DocTemplates() {
  const [d, setD] = useState<DocTemplatesData | null>(null)
  const [edit, setEdit] = useState<Editing | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ text: string; bad?: boolean } | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const load = useCallback(() => docTemplates().then(setD).catch(() => setNotice({ text: "Could not load the templates", bad: true })), [])
  useEffect(() => { void load() }, [load])
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  if (!d) return null

  async function run(fn: () => Promise<unknown>, text: string) {
    setBusy(true); setNotice(null)
    try { await fn(); setNotice({ text }); await load() } catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That did not save", bad: true }) } finally { setBusy(false) }
  }
  async function showPreview() {
    if (!edit) return
    setBusy(true); setNotice(null)
    try { const blob = await previewDocTemplate(edit.kind, edit.config); if (preview) URL.revokeObjectURL(preview); setPreview(URL.createObjectURL(blob)) }
    catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "No preview", bad: true }) } finally { setBusy(false) }
  }
  const startNew = (kind: DocKind) => { setPreview(null); setEdit({ kind, name: "", config: structuredClone(d.kinds[kind].default) }) }

  if (edit) return (
    <Editor d={d} edit={edit} setEdit={setEdit} busy={busy} notice={notice} preview={preview} onPreview={showPreview}
      onCancel={() => { setEdit(null); setPreview(null) }}
      onSave={() => run(async () => { await saveDocTemplate(edit.kind, edit.name, edit.config, edit.id); setEdit(null); setPreview(null) }, "Template saved.")}
      onLogo={async (key, file) => {
        setBusy(true); setNotice(null)
        try { const name = await uploadDocLogo(file); setEdit({ ...edit, config: { ...edit.config, [key]: name } }) }
        catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That image could not be used", bad: true }) } finally { setBusy(false) }
      }} />
  )

  return (
    <div className="grid grid-cols-1 gap-4">
      {notice && <p className={cn("text-[13px]", notice.bad ? "text-bad" : "text-muted-foreground")} role="status">{notice.text}</p>}
      {KINDS.map((kind) => {
        const list = d.templates.filter((t) => t.kind === kind)
        return (
          <section key={kind} className="panel p-4" aria-label={d.kinds[kind].label}>
            <div className="mb-2 flex items-center gap-2">
              <h2 data-n className="text-[12px] font-semibold text-nav-fg">{d.kinds[kind].label}</h2>
              <Button size="sm" variant="outline" className="ml-auto h-7 rounded-full" onClick={() => startNew(kind)}><Plus className="h-3.5 w-3.5" /> New template</Button>
            </div>
            {list.length === 0 && <p className="text-[13px] text-muted-foreground">No templates yet: documents use the built-in layout.</p>}
            <ul className="divide-y divide-border text-[13px]">
              {list.map((t) => <Row key={t.id} t={t} busy={busy}
                onEdit={() => { setPreview(null); setEdit({ id: t.id, kind: t.kind, name: t.name, config: structuredClone(t.config) }) }}
                onCopy={() => { setPreview(null); setEdit({ kind: t.kind, name: `${t.name} (copy)`, config: structuredClone(t.config) }) }}
                onDefault={() => run(() => defaultDocTemplate(t.id), `${t.name} is now the default.`)}
                onDelete={() => { if (confirm(`Delete the template ${t.name}? Documents already issued keep their look.`)) void run(() => deleteDocTemplate(t.id), "Template deleted.") }} />)}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

function Row({ t, busy, onEdit, onCopy, onDefault, onDelete }: { t: DocTemplate; busy: boolean; onEdit: () => void; onCopy: () => void; onDefault: () => void; onDelete: () => void }) {
  return (
    <li className="flex flex-wrap items-center gap-2 py-2">
      <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: SWATCH[t.config.accent] }} aria-hidden />
      <button type="button" onClick={onEdit} className="min-w-0 flex-1 text-left"><span className="font-medium hover:underline">{t.name}</span>
        {t.is_default && <span className="ml-2 rounded-full bg-accent px-2 py-1 text-[11px] font-medium text-primary-text">Default</span>}
        <span className="block text-[12px] text-muted-foreground">{t.config.title} · edited by {t.updated_by}, {fmtWhen(t.updated_at)}</span></button>
      {!t.is_default && <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={onDefault}><Star className="h-3.5 w-3.5" /> Make default</Button>}
      <Button size="sm" variant="ghost" className="h-7" onClick={onCopy} aria-label={`Duplicate ${t.name}`}><Copy className="h-3.5 w-3.5" /></Button>
      <Button size="sm" variant="ghost" className="h-7 text-bad" disabled={busy} onClick={onDelete} aria-label={`Delete ${t.name}`}><Trash2 className="h-3.5 w-3.5" /></Button>
    </li>
  )
}

function Editor({ d, edit, setEdit, busy, notice, preview, onPreview, onCancel, onSave, onLogo }: {
  d: DocTemplatesData; edit: Editing; setEdit: (e: Editing) => void; busy: boolean; notice: { text: string; bad?: boolean } | null; preview: string | null
  onPreview: () => void; onCancel: () => void; onSave: () => void; onLogo: (key: "logo" | "co_logo", f: File) => void
}) {
  const k = d.kinds[edit.kind]
  const c = edit.config
  const set = (patch: Partial<DocConfig>) => setEdit({ ...edit, config: { ...c, ...patch } })
  const label = (key: string) => k.sections.find((s) => s.key === key)?.label ?? key
  const move = (i: number, by: -1 | 1) => { const s = [...c.sections]; const j = i + by; if (j < 0 || j >= s.length) return; [s[i], s[j]] = [s[j], s[i]]; set({ sections: s }) }
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="grid grid-cols-1 content-start gap-4">
        <section className="panel grid grid-cols-1 gap-3 p-4" aria-label="Template">
          <div className="flex items-center gap-2"><FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
            <h2 className="text-[14px] font-semibold">{edit.id ? "Edit template" : "New template"} · {k.label}</h2></div>
          <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Template name<input className={field} required maxLength={80} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="e.g. Globex customer copy" autoFocus /></label>
          <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Document title<input className={field} maxLength={80} value={c.title} onChange={(e) => set({ title: e.target.value })} /></label>
        </section>

        <section className="panel grid grid-cols-1 gap-3 p-4" aria-label="Brand">
          <h2 data-n className="text-[12px] font-semibold text-nav-fg">Brand</h2>
          <fieldset><legend className="mb-2 text-[13px] font-medium">Accent</legend>
            <div className="flex flex-wrap gap-2">
              {d.accents.map((a) => <button key={a} type="button" onClick={() => set({ accent: a })} aria-label={a} aria-pressed={c.accent === a}
                className={cn("h-7 w-7 rounded-full ring-offset-2 ring-offset-card", c.accent === a && "ring-2 ring-foreground")} style={{ background: SWATCH[a] }} />)}
            </div>
          </fieldset>
          {(["logo", "co_logo"] as const).map((key) => (
            <div key={key} className="grid grid-cols-1 gap-1 text-[13px]">
              <span className="font-medium">{key === "logo" ? "Our logo" : "Customer's logo (co-brand)"} <span className="font-normal text-muted-foreground">{key === "logo" ? "replaces the Odin wordmark in the header" : "beside ours, on the right"}</span></span>
              <div className="flex items-center gap-2">
                {c[key] ? <img src={`/api/doc-templates/logo/${c[key]}`} alt="" className="h-9 max-w-40 rounded border border-border bg-white object-contain p-1" /> : <span className="text-muted-foreground">none</span>}
                <label className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-full border border-border px-3 hover:bg-muted"><ImageUp className="h-3.5 w-3.5" /> Upload
                  <input type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) onLogo(key, f); e.target.value = "" }} /></label>
                {c[key] && <button type="button" onClick={() => set({ [key]: null })} className="text-muted-foreground hover:text-foreground" aria-label={`Remove ${key === "logo" ? "our logo" : "the customer's logo"}`}><X className="h-4 w-4" /></button>}
              </div>
            </div>
          ))}
          <p className="-mt-1 text-[12px] text-muted-foreground">PNG or JPEG, up to 1 MB. A wide logo on a transparent or dark background reads best on the black header.</p>
          <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Company line <span className="font-normal text-muted-foreground">under the title, e.g. address and registration</span>
            <input className={field} maxLength={160} value={c.company_line} onChange={(e) => set({ company_line: e.target.value })} /></label>
          <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Footer <span className="font-normal text-muted-foreground">on every page, e.g. "Confidential"</span>
            <input className={field} maxLength={200} value={c.footer} onChange={(e) => set({ footer: e.target.value })} /></label>
        </section>

        <section className="panel p-4" aria-label="Sections">
          <h2 data-n className="mb-2 text-[12px] font-semibold text-nav-fg">Sections <span className="font-normal text-muted-foreground">which appear, in this order</span></h2>
          <ol className="grid grid-cols-1 gap-1 text-[13px]">
            {c.sections.map((s, i) => (
              <li key={s.key} className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-muted/50">
                <input type="checkbox" className="accent-primary" checked={s.on} aria-label={`Show ${label(s.key)}`} onChange={(e) => set({ sections: c.sections.map((x) => (x.key === s.key ? { ...x, on: e.target.checked } : x)) })} />
                <span className={cn("flex-1", !s.on && "text-muted-foreground line-through")}>{label(s.key)}</span>
                <button type="button" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${label(s.key)} up`} className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp className="h-3.5 w-3.5" /></button>
                <button type="button" disabled={i === c.sections.length - 1} onClick={() => move(i, 1)} aria-label={`Move ${label(s.key)} down`} className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown className="h-3.5 w-3.5" /></button>
              </li>
            ))}
          </ol>
          {edit.kind === "signoff" && <p className="mt-2 text-[12px] text-muted-foreground">The acceptance statement, the signatures and the signing record always appear.</p>}
        </section>

        <section className="panel grid grid-cols-1 gap-3 p-4" aria-label="Wording">
          <h2 data-n className="text-[12px] font-semibold text-nav-fg">Wording</h2>
          <p className="-mt-1 text-[12px] text-muted-foreground">Placeholders: {Object.entries(d.placeholders).map(([p, what]) => <code key={p} title={what} className="mr-2 rounded bg-muted px-1">{`{${p}}`}</code>)}</p>
          {k.texts.map((t) => (
            <label key={t.key} className="grid grid-cols-1 gap-1 text-[13px] font-medium">{t.label} <span className="font-normal text-muted-foreground">{t.help}</span>
              <textarea rows={t.key === "terms" ? 3 : 2} maxLength={3000} value={c.texts[t.key] ?? ""} onChange={(e) => set({ texts: { ...c.texts, [t.key]: e.target.value } })}
                className="w-full rounded-md border border-input bg-background p-2 text-[13px] leading-relaxed" /></label>
          ))}
        </section>

        {notice && <p className={cn("text-[13px]", notice.bad ? "text-bad" : "text-muted-foreground")} role="status">{notice.text}</p>}
        <div className="flex flex-wrap gap-2">
          <Button className="rounded-full" loading={busy} disabled={!edit.name.trim()} onClick={onSave}>Save template</Button>
          <Button variant="outline" className="rounded-full" disabled={busy} onClick={onPreview}><Eye className="h-4 w-4" /> Preview</Button>
          <Button variant="ghost" className="rounded-full" disabled={busy} onClick={onCancel}>Cancel</Button>
        </div>
      </div>
      <section className="panel sticky top-4 flex min-h-[70vh] flex-col p-2" aria-label="Preview">
        {preview ? <iframe src={preview} title="Template preview" className="h-full min-h-[70vh] w-full flex-1 rounded-lg border-0 bg-white" />
          : <div className="grid grid-cols-1 flex-1 place-items-center p-6 text-center text-[13px] text-muted-foreground">Preview renders this template on your newest project{edit.kind === "portfolio" ? "s" : ""}, before you save it.</div>}
      </section>
    </div>
  )
}
