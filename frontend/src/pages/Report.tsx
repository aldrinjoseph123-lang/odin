import { useCallback, useEffect, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { ChevronLeft, Download, Printer, Save, Sparkles } from "lucide-react"
import { Area, AreaChart, ResponsiveContainer, Tooltip as ChartTip, XAxis, YAxis } from "recharts"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { PrintBrand } from "@/components/Brand"
import { PageSkeleton } from "@/components/PageSkeleton"
import { PlanGantt, RagPill } from "@/components/PlanGantt"
import { RAID_KIND } from "@/components/RaidPanel"
import { Section, Table } from "@/components/ReportParts"
import { ApiError, rolloutReport, saveRolloutReport, type RolloutReport, type User } from "@/lib/api"
import { AIWordsDraft } from "@/components/AIWordsDraft"
import { AIDraftBar } from "@/components/AIDraftBar"
import { useUnsavedGuard } from "@/lib/useUnsavedGuard"
import { cn } from "@/lib/utils"
import { fillPlaceholders, fmtDate, fmtWhen, groupBlocks } from "@/lib/format"
import { TemplatePicker } from "@/components/TemplatePicker"

// The rollout report: where it stands, when it lands, what could stop it,
// who is doing what, and how it got here. Staff read it live and can switch
// to the customer's copy; the project manager's words are edited in place and
// "Save as version" freezes the lot. Partners and customers read saved
// versions only (the server enforces it). Every version exports to PDF.
const pill = cn(buttonVariants({ variant: "outline", size: "sm" }), "h-8 rounded-full px-3 text-[13px]")
const slip = (n: number | null | undefined) => (n == null ? "—" : n === 0 ? "on plan" : n > 0 ? `${n} d late` : `${-n} d early`)
const tip = { contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--elevation-pop)", fontSize: 12 }, labelStyle: { color: "var(--muted-foreground)" } }

export default function Report({ user }: { user: User }) {
  const id = Number(useParams().id)
  const [params, setParams] = useSearchParams()
  // partners only ever get the customer copy: asking for the internal one first logged a 404 (test report UX-28)
  const audience = params.get("audience") === "customer" || user.kind === "external" ? "customer" : "internal"
  const v = Number(params.get("v")) || null
  const template = Number(params.get("template")) || null
  const [r, setR] = useState<RolloutReport | null>(null)
  const [words, setWords] = useState({ summary: "", next_steps: "", asks: "" })
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [aiDraft, setAiDraft] = useState<number | null>(null)   // the AI draft the words came from, recorded with the save
  const load = useCallback(async () => {
    try {
      const x = await rolloutReport(id, audience, v, template)
      setR(x); setError(null)
      setWords({ summary: x.words.summary ?? "", next_steps: x.words.next_steps ?? "", asks: x.words.asks ?? "" })
      document.title = `Report · ${x.project.name} · Odin`
    } catch (e) { setError(e instanceof ApiError && e.status === 404 ? "No report has been published for this rollout yet." : e instanceof ApiError ? e.message : "Could not load the report") }
  }, [id, audience, v, template])
  useEffect(() => { void load() }, [load])
  const editable = !!r && r.is_live && r.can_edit
  const dirty = !!r && editable && (words.summary !== r.words.summary || words.next_steps !== r.words.next_steps || words.asks !== r.words.asks)
  useUnsavedGuard(dirty)
  if (error) return <div className="p-5"><Alert role="status"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!r) return <PageSkeleton />
  const set = (k: string, val: string | null) => setParams((p) => { const n = new URLSearchParams(p); if (val) n.set(k, val); else n.delete(k); return n }, { replace: true })
  async function save() {
    setBusy(true); setNotice(null)
    try { const x = await saveRolloutReport(id, words, template, aiDraft); setAiDraft(null); setNotice(`Version ${x.version} saved. Partners and customers now see it.`); await load() } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  const pdf = `/projects/${id}/report.pdf?audience=${r.audience}${r.version ? `&v=${r.version.version}` : template ? `&template=${template}` : ""}`
  const toolbar = (
    <div className="flex flex-wrap items-center gap-2 print:hidden">
      <Link to={`/projects/${id}`} className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"><ChevronLeft className="h-3.5 w-3.5" />{r.project.name}</Link>
      <span className="ml-auto flex flex-wrap items-center gap-2">
        {r.can_edit && (
          <span className="flex rounded-full bg-muted p-1" role="group" aria-label="Audience">
            {(["internal", "customer"] as const).map((a) => <button key={a} type="button" aria-pressed={r.audience === a} onClick={() => set("audience", a === "internal" ? null : a)}
              className={cn("h-7 rounded-full px-3 text-[13px] font-medium", r.audience === a ? "bg-card shadow-card" : "text-muted-foreground")}>{a === "internal" ? "Internal" : "Customer copy"}</button>)}
          </span>
        )}
        {r.versions.length > 0 && (
          <select value={r.version?.version ?? ""} onChange={(e) => set("v", e.target.value || null)} aria-label="Version" className="h-8 rounded-full border border-input bg-card px-3 text-[13px]">
            {r.can_edit && <option value="">Live — today's data</option>}
            {r.versions.map((x) => <option key={x.version} value={x.version}>v{x.version} · {x.created_by} · {fmtWhen(x.created_at)}{x.kind === "text" ? " (text)" : ""}</option>)}
          </select>
        )}
        {r.is_live && r.can_edit && <TemplatePicker kind="rollout" value={template} onChange={(t) => set("template", t ? String(t) : null)} />}
        {r.data && <a href={pdf} target="_blank" rel="noreferrer" className={pill}><Download className="h-3.5 w-3.5" /> PDF</a>}
        <button type="button" onClick={() => window.print()} className={pill}><Printer className="h-3.5 w-3.5" /> Print</button>
        {editable && <Button size="sm" className="h-8 rounded-full" loading={busy} disabled={!words.summary.trim()} onClick={save}><Save className="h-3.5 w-3.5" /> Save as version</Button>}
      </span>
    </div>
  )

  // an old plain-text version
  if (!r.data) {
    return (
      <div className="mx-auto w-full max-w-4xl px-5 pb-10 pt-2">
        <PrintBrand />{toolbar}
        <h1 className="mt-3 text-[17px] font-semibold tracking-tight">Report, version {r.version?.version}</h1>
        <Section title={`Written by ${r.version?.created_by}, ${fmtWhen(r.version?.created_at, true)}`} className="mt-3">
          <div className="text-[13px] leading-relaxed">
            {groupBlocks(r.words.blocks ?? []).map((b, i) => b.kind === "ul" ? <ul key={i} className="my-2 list-disc pl-5">{b.items.map((t, j) => <li key={j}>{t}</li>)}</ul>
              : b.kind === "h" ? <h3 key={i} className="mt-4 border-b border-border pb-1 text-[13px] font-semibold first:mt-0">{b.text}</h3> : <p key={i} className="my-2">{b.text}</p>)}
          </div>
        </Section>
      </div>
    )
  }

  const d = r.data
  const customer = d.audience === "customer"
  // the document template: which sections show, and its opening and closing words
  const on = (key: string) => !d.template || d.template.sections.some((s) => s.key === key && s.on)
  const hide = (key: string) => (on(key) ? undefined : "hidden")
  const tplValues = { project: d.project.name, client: d.project.client, company: d.company, pm: d.project.owner_name, po: d.project.po_number ?? "",
    stage: d.project.stage, target: fmtDate(d.finish.target), forecast: fmtDate(d.finish.forecast), date: fmtDate(d.today) }
  const intro = fillPlaceholders(d.template?.texts.intro ?? "", tplValues).trim()
  const closing = fillPlaceholders(d.template?.texts.closing ?? "", tplValues).trim()
  const f = d.finish
  const tiles: { label: string; value: string; sub: string; bad?: boolean }[] = [
    { label: "Forecast finish", value: f.forecast ? fmtDate(f.forecast) : "—", sub: f.vs_target_days == null ? "no target date" : f.vs_target_days > 0 ? `${f.vs_target_days} d after target` : `${-f.vs_target_days} d before target`, bad: (f.vs_target_days ?? 0) > 0 },
    { label: "Target", value: f.target ? fmtDate(f.target) : "—", sub: f.days_to_target == null ? "" : f.days_to_target < 0 ? `${-f.days_to_target} d ago` : `${f.days_to_target} d to go` },
    ...(customer ? [] : [{ label: "Against baseline", value: slip(f.vs_baseline_days), sub: d.baseline_at ? `baseline of ${fmtDate(d.baseline_at)}` : "no baseline yet", bad: (f.vs_baseline_days ?? 0) > 0 }]),
    { label: "Complete", value: `${d.pct_complete}%`, sub: `${d.elapsed_days} d since start` },
    { label: "Tasks", value: `${d.work.done}/${d.work.total}`, sub: d.work.late ? `${d.work.late} late` : "none late", bad: d.work.late > 0 },
  ]
  const textarea = "w-full rounded-lg border border-input bg-background p-3 text-[14px] leading-relaxed"
  const wordBlock = (key: "summary" | "next_steps" | "asks", label: string, rows: number, hint: string) => (
    <div>
      <div className="mb-1 flex items-center gap-2"><h3 className="text-[13px] font-semibold text-nav-fg">{label}</h3>
        {editable && r.words.suggested && r.words.suggested[key] && words[key] !== r.words.suggested[key] && (
          <button type="button" onClick={() => setWords({ ...words, [key]: r.words.suggested![key] })} className="inline-flex items-center gap-1 text-[12px] text-primary-text hover:underline print:hidden"><Sparkles className="h-3 w-3" /> Use the suggestion</button>
        )}
      </div>
      {editable && <textarea aria-label={label} rows={rows} value={words[key]} onChange={(e) => setWords({ ...words, [key]: e.target.value })} placeholder={hint} className={cn(textarea, "print:hidden")} />}
      <div className={cn("whitespace-pre-line text-[14px] leading-relaxed", editable && "hidden print:block")}>{words[key] || <span className="text-muted-foreground">—</span>}</div>
    </div>
  )

  return (
    <div className="mx-auto w-full max-w-6xl px-5 pb-10 pt-2 print:max-w-none print:px-0">
      <PrintBrand />
      {toolbar}
      {notice && <p className="mt-2 text-[13px] text-muted-foreground print:hidden" role="status">{notice}</p>}
      <p className="mt-2 text-[12px] text-muted-foreground print:hidden">
        {r.is_live ? (editable ? "Live: today's numbers. Edit the words, then Save as version — partners and customers see saved versions only." : "Live: today's numbers.")
          : `Saved version ${r.version!.version} by ${r.version!.created_by}, ${fmtWhen(r.version!.created_at, true)} — the numbers as they were then.`}
        {customer && r.can_edit ? " You are looking at the customer's copy." : ""}
      </p>

      <header className="mt-3">
        <h1 className="text-[24px] font-semibold tracking-tight">{d.project.name}</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">{[d.project.client, `PM ${d.project.owner_name}`, `stage ${d.project.stage_number} of ${d.project.stage_count}: ${d.project.stage}`, d.project.po_number, d.project.vendor_name && `${d.project.vendor_name}${d.project.product_name ? ` ${d.project.product_name}` : ""}`].filter(Boolean).join(" · ")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <RagPill rag={d.health.rag} />
          {!customer && <ul className="text-[13px] text-muted-foreground">{d.health.reasons.map((x) => <li key={x}>{x}</li>)}</ul>}
          {!customer && <span className="text-[12px] text-muted-foreground">Forecast confidence: <span className="font-medium text-foreground">{d.health.confidence}</span></span>}
        </div>
      </header>

      {intro && <p className="mt-3 whitespace-pre-line text-[14px] leading-relaxed">{intro}</p>}
      <div className={cn("mt-4 grid grid-cols-2 gap-3", customer ? "lg:grid-cols-4" : "lg:grid-cols-5", hide("numbers"))}>
        {tiles.map((t) => (
          <div key={t.label} className="panel p-4 print:shadow-none">
            <div className="text-[12px] text-muted-foreground">{t.label}</div>
            <div className={cn("mt-2 text-[24px] font-semibold leading-none tracking-tight", t.bad && "text-bad")}>{t.value}</div>
            <div className="mt-1 text-[12px] text-muted-foreground">{t.sub}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4">
        <Section n title="Summary" className={hide("summary")}>
          {editable && <AIWordsDraft projectId={id} onUse={(w, sid) => { setWords(w); setAiDraft(sid) }} />}
          {editable && words.summary.trim() && (
            <AIDraftBar<{ summary: string; next_steps: string[]; asks: string[] }> projectId={id} feature="customer_words" input={() => words}
              ask="Tidy for the customer" again="Tidy again"
              idle="Before you save: rewrite these words so the customer can read them. Names, blame and shorthand come out; every fact stays; nothing is added."
              working="Tidying the words as they are now… about a minute."
              note="A customer-ready version of your words. Use it, then read it once more before saving."
              onUse={(s) => { setWords({ summary: s.payload.summary, next_steps: s.payload.next_steps.join("\n"), asks: s.payload.asks.join("\n") }); setAiDraft(s.id) }} />
          )}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {wordBlock("summary", "Where it stands", 5, "Two or three lines: where the rollout stands, what changed, what happens next.")}
            <div className="grid grid-cols-1 content-start gap-4">
              {wordBlock("next_steps", "Next steps", 3, "One per line.")}
              {(customer || editable) && wordBlock("asks", "What we need from the customer", 3, "One per line: approvals, access, windows, decisions.")}
              {customer && (d.needs.approval || d.needs.tasks.length > 0) && (
                <ul className="list-disc pl-5 text-[13px]">
                  {d.needs.approval && <li>Approve the {d.needs.approval.stage} stage (asked {fmtDate(d.needs.approval.requested_at)}).</li>}
                  {d.needs.tasks.map((t, i) => <li key={i}>{t.title}{t.due_date && ` — due ${fmtDate(t.due_date)}`}</li>)}
                </ul>
              )}
            </div>
          </div>
        </Section>

        <Section n title="Timeline" sub="plan against actual, and the forecast for what is left" className={hide("timeline")}>
          <PlanGantt stages={d.stages} today={d.today} target={f.target} />
          <div className="mt-4">
            <Table head={["Stage", "Planned", "Actual", "Forecast", ...(customer ? [] : ["Slip"])]}
              rows={d.stages.map((s) => [<span key="name" className={cn(s.status === "current" && "font-semibold")}>{s.name}{s.status === "current" && <span className="ml-1 text-[11px] font-normal text-primary-text">now</span>}</span>,
                s.plan_start ? `${fmtDate(s.plan_start)} → ${fmtDate(s.plan_end)}` : "—",
                s.actual_start ? `${fmtDate(s.actual_start)} → ${s.actual_end ? fmtDate(s.actual_end) : "now"}` : s.status === "skipped" ? "skipped" : "—",
                s.forecast_end ? `${fmtDate(s.forecast_start)} → ${fmtDate(s.forecast_end)}` : "—",
                ...(customer ? [] : [slip(s.slip_days)])])}
              tone={(i, c) => (c === 4 && (d.stages[i].slip_days ?? 0) > 0 ? "font-medium text-bad" : undefined)} />
          </div>
        </Section>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Section n title="What's next" sub="the coming stages, as forecast" className={hide("timeline")}>
            <ol className="grid grid-cols-1 gap-2">
              {d.milestones.map((m, i) => (
                <li key={m.stage} className="flex items-center gap-3 rounded-xl bg-muted/50 px-3 py-2 text-[13px]">
                  <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold", i === 0 ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground")}>{i + 1}</span>
                  <span className="min-w-0 flex-1 font-medium">{m.stage}</span>
                  <span className="text-[13px] text-muted-foreground">{fmtDate(m.start)} → <span className="font-medium text-foreground">{fmtDate(m.end)}</span></span>
                  {!customer && m.planned_end && m.end && m.end > m.planned_end && <span className="text-[12px] font-medium text-bad">plan {fmtDate(m.planned_end)}</span>}
                </li>
              ))}
              {d.milestones.length === 0 && <li className="text-[13px] text-muted-foreground">Nothing left: the rollout is complete.</li>}
            </ol>
          </Section>

          <Section n title={customer ? "Decisions and open points" : "Risks, issues, decisions, blockers"} sub={`${d.raid.filter((x) => x.open).length} open`} className={hide("raid")}>
            <ul className="divide-y divide-border text-[13px]">
              {d.raid.map((x) => {
                const K = RAID_KIND[x.kind]
                return (
                  <li key={x.id} className="flex items-start gap-3 py-2">
                    <K.icon className={cn("mt-1 h-4 w-4 shrink-0", x.kind === "blocker" && x.open ? "text-bad" : "text-muted-foreground")} aria-hidden />
                    <span className="min-w-0 flex-1"><span className={cn("block font-medium", !x.open && "text-muted-foreground")}>{x.title}</span>
                      <span className="block text-[12px] text-muted-foreground">{K.label} · {x.status}{x.owner_name && ` · ${x.owner_name}`}{x.due_date && ` · due ${fmtDate(x.due_date)}`}{x.resolution && ` · ${x.resolution}`}</span></span>
                    {x.kind !== "decision" && <span className={cn("shrink-0 rounded-full px-2 py-1 text-[11px] font-medium", x.impact === "high" ? "bg-warn-soft font-semibold text-warn" : x.impact === "medium" ? "bg-muted text-foreground" : "bg-muted text-muted-foreground")}>{x.impact}</span>}
                  </li>
                )
              })}
              {d.raid.length === 0 && <li className="py-2 text-muted-foreground">Nothing recorded.</li>}
            </ul>
          </Section>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Section n title="Work" sub={`${d.work.done} of ${d.work.total} tasks done${d.work.late ? `, ${d.work.late} late` : ""}`} className={hide("work")}>
            {d.work.burn.length > 1 && (
              <div className="h-40" role="img" aria-label={`Tasks known and done per week: ${d.work.burn.map((w) => `${fmtDate(w.week)} ${w.done} of ${w.total}`).join(", ")}`}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={d.work.burn} margin={{ top: 6, right: 6, bottom: 0, left: -18 }} accessibilityLayer={false}>
                    <XAxis dataKey="week" tickFormatter={(x: string) => fmtDate(x).replace(/ \d{4}$/, "")} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                    <ChartTip {...tip} labelFormatter={(x) => `week of ${fmtDate(String(x))}`} />
                    <Area type="stepAfter" dataKey="total" name="Tasks known" stroke="var(--input)" fill="var(--muted)" isAnimationActive={false} />
                    <Area type="stepAfter" dataKey="done" name="Done" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.25} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="mt-3 grid grid-cols-1 gap-2 text-[13px]">
              {d.work.by_stage.filter((b) => b.total).map((b) => (
                <div key={b.stage} className="flex items-center gap-3">
                  <span className="w-32 truncate">{b.stage}</span>
                  <span className="flex h-2 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden><span className="bg-primary" style={{ width: `${(b.done / b.total) * 100}%` }} /><span className="bg-bad-line" style={{ width: `${(b.late / b.total) * 100}%` }} /></span>
                  <span className="w-24 text-right tabular-nums text-muted-foreground">{b.done}/{b.total}{b.late ? <span className="text-bad"> · {b.late} late</span> : ""}</span>
                </div>
              ))}
            </div>
          </Section>

          {!customer && d.people ? (
            <Section n title="People" sub="who carries the work" className={hide("work")}>
              <Table head={["Person", "Role", "Open", "Done", "Late"]} rows={d.people.map((p) => [p.name, p.role ?? "—", p.open, p.done, p.late])} tone={(i, c) => (c === 4 && d.people![i].late ? "font-medium text-bad" : undefined)} />
              {d.work.open && d.work.open.length > 0 && (
                <>
                  <h3 className="mb-1 mt-4 text-[13px] font-semibold text-nav-fg">Open tasks</h3>
                  <Table head={["Task", "Stage", "Who", "Due"]} rows={d.work.open.slice(0, 12).map((t) => [t.title, t.stage ?? "—", t.who ?? "—", t.due_date ? (t.late ? `${fmtDate(t.due_date)} · late` : fmtDate(t.due_date)) : "—"])}
                    tone={(i, c) => (c === 3 && d.work.open![i].late ? "font-medium text-bad" : undefined)} />
                </>
              )}
            </Section>
          ) : (
            <Section n title="Team" className={hide("team")}><ul className="grid grid-cols-1 gap-1 text-[13px]">{d.team.map((m) => <li key={m.name} className="flex justify-between"><span className="font-medium">{m.name}</span><span className="text-muted-foreground">{m.role}</span></li>)}</ul></Section>
          )}
        </div>

        <Section n title="History" sub="time in each stage against its SLA, decisions, and what moved" className={hide("history")}>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <div>
              <Table head={["Stage", "Entered", "Left", "Days", "SLA"]}
                rows={d.history.dwell.map((x) => [x.stage, fmtDate(x.entered), x.left ? fmtDate(x.left) : "still here", x.days ?? "—", x.sla ? `${x.sla} d` : "—"])}
                tone={(i, c) => (c === 3 && d.history.dwell[i].over ? "font-medium text-warn" : undefined)} />
              {d.history.approvals.length > 0 && (
                <>
                  <h3 className="mb-1 mt-4 text-[13px] font-semibold text-nav-fg">Customer approvals</h3>
                  <Table head={["Stage", "Status", "Asked", "Decided"]} rows={d.history.approvals.map((a) => [a.stage, a.status, fmtDate(a.requested_at), a.decided_at ? `${fmtDate(a.decided_at)}${a.decided_by ? ` · ${a.decided_by}` : ""}` : "—"])} />
                </>
              )}
            </div>
            <div className="grid grid-cols-1 content-start gap-4">
              {!customer && d.plan_changes && d.plan_changes.length > 0 && (
                <div>
                  <h3 className="mb-1 text-[13px] font-semibold text-nav-fg">What moved in the plan</h3>
                  <ul className="divide-y divide-border text-[13px]">{d.plan_changes.slice(0, 10).map((c, i) => (
                    <li key={i} className="py-2">{c.field === "baseline" ? <span className="font-medium">Re-baselined</span> : <><span className="font-medium">{c.stage}</span> {c.field} {c.old ? fmtDate(c.old) : "unset"} → {c.new ? fmtDate(c.new) : "unset"}</>}
                      {c.reason && <span className="text-muted-foreground"> — {c.reason}</span>}<span className="block text-[12px] text-muted-foreground">{c.author} · {fmtDate(c.created_at)}</span></li>))}</ul>
                </div>
              )}
              {d.history.notes.length > 0 && (
                <div>
                  <h3 className="mb-1 text-[13px] font-semibold text-nav-fg">Notes</h3>
                  <ul className="grid grid-cols-1 gap-2 text-[13px]">{d.history.notes.slice(0, 8).map((n, i) => <li key={i}><span className="text-[12px] text-muted-foreground">{n.author} · {n.stage} · {fmtDate(n.created_at)}</span><p>{n.note}</p></li>)}</ul>
                </div>
              )}
              {d.documents && d.documents.length > 0 && (
                <div>
                  <h3 className="mb-1 text-[13px] font-semibold text-nav-fg">Documents</h3>
                  <ul className="grid grid-cols-1 gap-1 text-[13px]">{d.documents.slice(0, 12).map((x, i) => <li key={i} className="flex justify-between gap-3"><span className="truncate">{"filename" in x ? x.filename : x.category}</span><span className="shrink-0 text-muted-foreground">{"filename" in x ? `${x.category} · ${fmtDate(x.uploaded_at)}` : `${x.count} file${x.count === 1 ? "" : "s"}`}</span></li>)}</ul>
                </div>
              )}
            </div>
          </div>
        </Section>
      </div>
      {closing && <p className="mt-4 whitespace-pre-line text-[14px] leading-relaxed">{closing}</p>}
      <p className="mt-4 text-[12px] text-muted-foreground">Odin · {d.company} · {customer ? "customer copy" : "internal"} · generated {fmtWhen(d.generated_at, true)}</p>
    </div>
  )
}
