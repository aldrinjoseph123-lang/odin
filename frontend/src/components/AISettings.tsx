import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { CheckCircle2, CircleDashed, Clock, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Ago } from "@/components/Ago"
import { aiSettings, ApiError, postForm, type AICheck, type AIFeatureView, type AIView, type Policy } from "@/lib/api"
import { cn } from "@/lib/utils"

type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

function Panel({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="panel p-4">
      <h2 data-n className="mb-3 text-[12px] font-semibold text-nav-fg">{title}{hint && <span className="sr-only">, </span>}{hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}</h2>
      {children}
    </section>
  )
}

// A state is a word and an icon, never colour alone.
const TONE = {
  ok: "bg-ok-soft text-ok", warn: "bg-warn-soft text-warn", bad: "bg-bad-soft text-bad", none: "bg-muted text-muted-foreground",
} as const
function Pill({ tone, icon, children }: { tone: keyof typeof TONE; icon: ReactNode; children: ReactNode }) {
  return <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-medium", TONE[tone])}>{icon}{children}</span>
}
const ICON = "h-3.5 w-3.5"
const FEATURE_STATE: Record<AIFeatureView["state"], [keyof typeof TONE, ReactNode, string]> = {
  passed: ["ok", <CheckCircle2 className={ICON} key="i" />, "Passed"],
  slow: ["warn", <Clock className={ICON} key="i" />, "Slow"],
  failed: ["bad", <XCircle className={ICON} key="i" />, "Failed"],
  pending: ["none", <CircleDashed className={ICON} key="i" />, "Not yet validated"],
}

// Settings → AI. The server form checks before it saves; status and the
// feature table refresh on their own while a validation runs.
export function AISettings({ policies, busy, send, schedule }: { policies: Policy[]; busy: boolean; send: Send; schedule: ReactNode }) {
  const [view, setView] = useState<AIView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try { setView(await aiSettings()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load the AI status") }
  }, [])
  useEffect(() => { void load() }, [load])
  const working = !!view && (view.jobs[0]?.status === "queued" || view.jobs[0]?.status === "running" || view.status.state === "unknown")
  useEffect(() => {
    if (!working) return
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [working, load])
  const act: Send = async (path, fields, confirmText) => { const r = await send(path, fields, confirmText); await load(); return r }

  return (
    <>
      <Server policies={policies} busy={busy} send={act} hasKey={!!view?.has_key} />
      {error && <p className="text-[13px] text-bad" role="alert">{error}</p>}
      {view && <Status view={view} busy={busy} send={act} />}
      {view && <Features features={view.features} busy={busy} send={act} />}
      {schedule}
    </>
  )
}

function Server({ policies, busy, send, hasKey }: { policies: Policy[]; busy: boolean; send: Send; hasKey: boolean }) {
  const val = (k: string) => policies.find((p) => p.key === k)?.value
  const [f, setF] = useState({ ai_enabled: !!val("ai_enabled"), ai_base_url: String(val("ai_base_url") ?? ""), ai_model: String(val("ai_model") ?? "P24-AI"), ai_allow_external: !!val("ai_allow_external") })
  const [key, setKey] = useState("")
  const [check, setCheck] = useState<AICheck | null>(null)
  const [checking, setChecking] = useState(false)
  const fields = () => ({ ai_base_url: f.ai_base_url, ai_model: f.ai_model, ...(f.ai_enabled ? { ai_enabled: "on" } : {}), ...(f.ai_allow_external ? { ai_allow_external: "on" } : {}) })
  async function runCheck() {
    setChecking(true)
    try {
      const r = (await postForm("/settings/ai/check", { ...fields(), ...(key ? { api_key: key } : {}) })) as unknown as { result: AICheck; messages: string[] }
      setCheck(r.result)
    } catch (e) { setCheck({ ok: false, reason: e instanceof ApiError ? e.message : "The check did not run" }) } finally { setChecking(false) }
  }
  function save(e: FormEvent) { e.preventDefault(); void send("/settings/policies/ai", fields()).then(() => setCheck(null)) }
  const label = (k: string) => policies.find((p) => p.key === k)
  return (
    <Panel title="AI server" hint="any OpenAI-compatible server: Ollama, llama.cpp, vLLM, or a hosted provider">
      <form onSubmit={save} className="grid grid-cols-1 gap-4">
        <label className="flex items-start gap-2 text-[13px] font-medium">
          <input type="checkbox" checked={f.ai_enabled} onChange={(e) => setF({ ...f, ai_enabled: e.target.checked })} className="mt-0.5 h-3.5 w-3.5 accent-primary" />
          <span>{label("ai_enabled")?.label}<span className="block text-[12px] font-normal text-muted-foreground">{label("ai_enabled")?.help}</span></span>
        </label>
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
          <div className="grid content-start gap-1">
            <label htmlFor="ai-url" className="text-[13px] font-medium">{label("ai_base_url")?.label}</label>
            <Input id="ai-url" type="url" maxLength={200} placeholder="http://ai.p24.lan:11434/v1" value={f.ai_base_url} onChange={(e) => { setF({ ...f, ai_base_url: e.target.value }); setCheck(null) }} className="h-8 max-w-md font-mono text-[12.5px]" />
            <p className="text-[12px] text-muted-foreground">{label("ai_base_url")?.help}</p>
          </div>
          <div className="grid content-start gap-1">
            <label htmlFor="ai-model" className="text-[13px] font-medium">{label("ai_model")?.label}</label>
            <Input id="ai-model" required maxLength={120} value={f.ai_model} onChange={(e) => { setF({ ...f, ai_model: e.target.value }); setCheck(null) }} className="h-8 max-w-xs font-mono text-[12.5px]" />
            <p className="text-[12px] text-muted-foreground">{label("ai_model")?.help}</p>
          </div>
          <div className="grid content-start gap-1">
            <label htmlFor="ai-key" className="text-[13px] font-medium">API key</label>
            <div className="flex flex-wrap items-center gap-2">
              <Input id="ai-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={hasKey ? "saved; type to replace" : "none (a local server needs none)"} className="h-8 max-w-xs text-[12.5px]" />
              <Button type="button" size="sm" variant="outline" disabled={busy || !key} onClick={() => void send("/settings/ai/key", { api_key: key }).then(() => setKey(""))}>Save key</Button>
              {hasKey && <Button type="button" size="sm" variant="ghost" className="text-bad hover:text-bad" disabled={busy} onClick={() => void send("/settings/ai/key", { clear: "1" }, "Remove the saved API key?")}>Remove</Button>}
            </div>
            <p className="text-[12px] text-muted-foreground">Stored sealed, like the Microsoft 365 secret, and sent as a bearer token.</p>
          </div>
          <label className="flex items-start gap-2 text-[13px] font-medium">
            <input type="checkbox" checked={f.ai_allow_external} onChange={(e) => { setF({ ...f, ai_allow_external: e.target.checked }); setCheck(null) }} className="mt-0.5 h-3.5 w-3.5 accent-primary" />
            <span>{label("ai_allow_external")?.label}<span className="block text-[12px] font-normal text-muted-foreground">{label("ai_allow_external")?.help}</span></span>
          </label>
        </div>
        {check && (
          <p role="status" className={cn("flex items-start gap-2 rounded-md px-3 py-2 text-[13px]", check.ok ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad")}>
            {check.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}
            <span>{check.ok ? <>The server answers and runs <span className="font-mono">{check.model}</span>. Save to use it; every feature is then validated on it.</> : check.reason}</span>
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={busy || checking || !f.ai_base_url} onClick={() => void runCheck()}>{checking ? "Checking…" : "Check"}</Button>
          <Button type="submit" size="sm" disabled={busy}>Save</Button>
        </div>
      </form>
    </Panel>
  )
}

function Status({ view, busy, send }: { view: AIView; busy: boolean; send: Send }) {
  const s = view.status
  const job = view.jobs[0]
  const running = job && (job.status === "queued" || job.status === "running")
  return (
    <Panel title="Status" hint="the heartbeat asks the server which model it runs; no model work">
      <div className="grid grid-cols-1 gap-3 text-[13px]">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {s.state === "up" && <Pill tone="ok" icon={<CheckCircle2 className={ICON} />}>Answering</Pill>}
          {s.state === "down" && <Pill tone="bad" icon={<XCircle className={ICON} />}>Not answering</Pill>}
          {s.state === "unknown" && <Pill tone="none" icon={<CircleDashed className={ICON} />}>Waiting for the first heartbeat</Pill>}
          {s.state === "off" && <Pill tone="none" icon={<CircleDashed className={ICON} />}>Off</Pill>}
          {s.state === "up" && s.since && <span className="text-muted-foreground">since <Ago iso={s.since} /></span>}
          {s.checked_at && s.state !== "off" && <span className="text-muted-foreground">last heartbeat <Ago iso={s.checked_at} /></span>}
        </div>
        {s.state === "down" && s.error && <p className="text-bad">{s.error}. AI features are paused; Odin is using its usual behaviour.</p>}
        {s.state === "off" && <p className="text-muted-foreground">Odin is not using AI. Set the server above, tick Use AI features, Check, then Save.</p>}
        {s.model && s.state !== "off" && (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
            <dt className="text-muted-foreground">Model</dt><dd className="font-mono text-[12.5px]">{s.model}</dd>
            <dt className="text-muted-foreground">Fingerprint</dt><dd className="break-all font-mono text-[12px] text-muted-foreground">{s.fingerprint} <span className="font-sans">(changes when the model behind the name is rebuilt or replaced; every feature is then validated again)</span></dd>
            {s.seconds != null && <><dt className="text-muted-foreground">One short answer</dt><dd className="tabular-nums">{s.seconds} s</dd></>}
          </dl>
        )}
        {!view.scheduler_alive && s.state !== "off" && (
          <p className="rounded-md border border-warn-line bg-warn-soft px-3 py-2 text-warn">The scheduler is not running, so there is no heartbeat and nothing is validated. Start the <code className="font-mono text-[12px]">scheduler</code> service.</p>
        )}
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <Button size="sm" variant="outline" disabled={busy || running || s.state === "off"} onClick={() => send("/settings/ai/validate")}>Validate now</Button>
          {job && <span className="text-[12.5px] text-muted-foreground">{
            job.status === "queued" ? <>Validation waiting to start (asked <Ago iso={job.created_at} />)…</>
              : job.status === "running" ? <>Validating every feature on its test project (started {job.started_at ? <Ago iso={job.started_at} /> : "now"})…</>
                : job.status === "failed" ? <>Last validation stopped: {job.error}</>
                  : job.result && !job.result.ok ? <>Last validation <Ago iso={job.finished_at ?? job.created_at} />: {job.result.reason}</>
                    : <>Last validation <Ago iso={job.finished_at ?? job.created_at} />{job.result?.model ? <> on <span className="font-mono">{job.result.model}</span></> : null}.{job.payload?.reason ? ` Started because ${job.payload.reason}.` : ""}</>
          }</span>}
        </div>
      </div>
    </Panel>
  )
}

function Features({ features, busy, send }: { features: AIFeatureView[]; busy: boolean; send: Send }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <Panel title="Features" hint="each runs only after passing its test on the current model">
      {features.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No AI features yet. Each one arrives with its own test project and appears here, validated against the server before it runs.</p>
      ) : (
        <div className="overflow-x-auto"><table className="w-full text-[13px]">
          <thead><tr className="text-left text-[11.5px] text-muted-foreground">{["Feature", "On the current model", "Last tested", "Answer time", "On", "Forced", ""].map((h) => <th key={h} className="pb-1.5 pr-3 font-normal">{h}</th>)}</tr></thead>
          <tbody>
            {features.map((f) => {
              const [tone, icon, word] = FEATURE_STATE[f.state]
              const post = (on: boolean, force: boolean) => send(`/settings/ai/features/${f.key}`, { ...(on ? { on: "on" } : {}), ...(force ? { force: "on" } : {}) },
                force && !f.forced ? `Force ${f.label} on? It will run even though it has not passed its test on this model.` : undefined)
              return [
                <tr key={f.key} className="border-t border-border align-top">
                  <td className="py-2 pr-3"><span className="font-medium">{f.label}</span><span className="block text-[12px] text-muted-foreground">{f.description}</span></td>
                  <td className="py-2 pr-3"><Pill tone={tone} icon={icon}>{word}</Pill>{f.detail && <span className="mt-1 block text-[12px] text-muted-foreground">{f.detail}</span>}</td>
                  <td className="whitespace-nowrap py-2 pr-3">{f.checked_at ? <><Ago iso={f.checked_at} /><span className="block font-mono text-[11.5px] text-muted-foreground">{f.model}</span></> : <span className="text-muted-foreground">never</span>}</td>
                  <td className="whitespace-nowrap py-2 pr-3 tabular-nums">{f.seconds != null ? `${f.seconds} s` : "—"}</td>
                  <td className="py-2 pr-3"><input type="checkbox" checked={f.on} disabled={busy} onChange={(e) => void post(e.target.checked, f.forced)} aria-label={`${f.label} on`} className="h-3.5 w-3.5 accent-primary" /></td>
                  <td className="py-2 pr-3"><input type="checkbox" checked={f.forced} disabled={busy || !f.on} onChange={(e) => void post(f.on, e.target.checked)} aria-label={`Force ${f.label} on without a passed test`} className="h-3.5 w-3.5 accent-primary" /></td>
                  <td className="py-2 text-right">{f.output != null && <Button size="sm" variant="ghost" className="h-7" onClick={() => setOpen(open === f.key ? null : f.key)} aria-expanded={open === f.key}>{open === f.key ? "Hide answer" : "Test answer"}</Button>}</td>
                </tr>,
                open === f.key && (
                  <tr key={`${f.key}:out`}><td colSpan={7} className="pb-3">
                    <pre className="max-h-72 overflow-auto rounded-md border border-border bg-secondary p-3 font-mono text-[12px] leading-relaxed">{JSON.stringify(f.output, null, 2)}</pre>
                    <p className="mt-1 text-[11.5px] text-muted-foreground">Prompt {f.prompt} · {f.prompt_hash}</p>
                  </td></tr>
                ),
              ]
            })}
          </tbody>
        </table></div>
      )}
    </Panel>
  )
}
