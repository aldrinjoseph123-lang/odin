import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { Navigate, useParams } from "react-router-dom"
import { Trash2 } from "lucide-react"
import { Button, buttonVariants } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { StageListEditor, stageRowsKey } from "@/components/StageListEditor"
import { ApiError, postForm, settingsData, type BackupRun, type BackupsView, type Policy, type SettingsData, type User } from "@/lib/api"
import { Ago } from "@/components/Ago"
import { cn } from "@/lib/utils"
import { isDark } from "@/lib/theme"
import { DocTemplates } from "@/components/DocTemplates"
import { AISettings } from "@/components/AISettings"
import { SlaCheck } from "@/components/SlaCheck"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

const selectClass = "h-8 rounded-md border border-input bg-background px-2 text-[13px]"
type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

function Panel({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} aria-label={title} className="panel p-4">
      <h2 data-n className="mb-3 text-[12px] font-semibold text-nav-fg">{title}{hint && <span className="sr-only">, </span>}{hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}</h2>
      {children}
    </section>
  )
}

// Settings → one area per address (/settings/<section>); the side menu is
// SettingsLayout. Each area draws only its own panels and loads without
// asking Microsoft for anything unless it is Integrations.
const TITLES: Record<string, { title: string; lede: string }> = {
  general: { title: "General", lede: "How the workspace reads for everyone." },
  security: { title: "Sign-in & security", lede: "Sessions, passwords, uploads and outside access." },
  people: { title: "Sign-up & activity", lede: "Sign-up links, and whether Odin records each person's active time." },
  workflow: { title: "Projects & workflow", lede: "What new projects start with, their stages and the alerts they raise." },
  notifications: { title: "Notifications", lede: "Which channels carry project events; each person tunes their own email." },
  integrations: { title: "Integrations", lede: "Microsoft 365 mail, Teams and OneDrive, and the Kibana dashboards." },
  ai: { title: "AI", lede: "The AI server, its health, and which features pass on today's model." },
  reports: { title: "Reports", lede: "The weekly portfolio report: who gets it, when, and what rides along." },
  documents: { title: "Documents", lede: "Brand, sections and wording for reports and the sign-off." },
  api: { title: "API tokens", lede: "Read-only access for scripts: projects, stages, tasks and saved reports." },
  audit: { title: "Retention", lede: "How long the audit trail, notifications and activity are kept." },
  map: { title: "System map & changes", lede: "How this version of Odin works, what changed, and the known gaps." },
  backups: { title: "Backups", lede: "Scheduled, restore-tested copies of the database, documents and pictures." },
}

export default function Settings(_props: { user: User }) {
  const section = useParams().section ?? ""
  const [data, setData] = useState<SettingsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [teamId, setTeamId] = useState("")
  const load = useCallback(async (team = teamId) => {
    try { setData(await settingsData(section, team)); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load settings") }
  }, [teamId, section])
  useEffect(() => { if (TITLES[section]) { document.title = `${TITLES[section].title} · Settings · Odin`; setNotice(null); void load() } }, [load, section])

  const send: Send = async (path, fields = {}, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return null
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      setNotice(r.messages.join(" ") || null)
      await load()
      return r
    } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save"); return null } finally { setBusy(false) }
  }

  if (!TITLES[section]) return <Navigate to="/settings/general" replace />
  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />
  // one small titled card per topic, each with its own Save (9 Oct 2026, the user's call)
  const policyForm = (area: Policy["area"]) => {
    const mine = data.policies.filter((p) => p.area === area)
    const groups = [...new Set(mine.map((p) => p.group))]
    return (
      <div className="gap-4 lg:columns-2 [&>*]:mb-4 [&>*]:min-w-0 [&>*]:break-inside-avoid [&>*:last-child]:mb-0">
        {groups.map((g) => {
          const ps = mine.filter((p) => p.group === g)
          return <PolicyForm key={`${g}:${JSON.stringify(ps.map((p) => p.value))}`} title={g} hint={GROUP_HINTS[g]}
            area={area} policies={ps} templates={data.templates} busy={busy} send={send} />
        })}
      </div>
    )
  }

  return (
    <div className="px-5 pb-6 pt-4">
      <h1 className="text-[17px] font-semibold tracking-tight">{TITLES[section].title}</h1>
      <p className="mt-1 text-[13px] text-muted-foreground">{TITLES[section].lede}</p>
      {notice && (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-2 text-[13px]" role="status">
          <span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* min-w-0 on every grid item: a wide table scrolls inside its panel
          instead of stretching the page on a phone */}
      <div className={cn("mt-4 grid gap-4 [&>*]:min-w-0", section !== "map" && "max-w-5xl")}>
        {section === "general" && policyForm("general")}
        {section === "people" && policyForm("people")}
        {section === "security" && (
          <>
            <Sso key={JSON.stringify(data.sso)} sso={data.sso} busy={busy} send={send} />
            {policyForm("security")}
            <Toggles data={data} busy={busy} send={send} title="Outside access" keys={[
              { key: "guest_links_enabled", label: "Keep the legacy anonymous guest links working (turn off once invited partner and customer accounts have replaced them; every old link then stops)" },
            ]} />
          </>
        )}
        {section === "workflow" && (
          <>
            {policyForm("workflow")}
            <Panel title="Stage templates" hint="a new project copies one, then owns its list" id="templates">
              <div className="grid grid-cols-1 gap-5">
                {data.templates.map((t) => <Template key={`${t.id}:${t.name}`} t={t} onlyOne={data.templates.length <= 1} busy={busy} send={send} />)}
              </div>
              <AddForm placeholder="New template name (e.g. EDR rollout)" label="New template name" button="Add template" busy={busy} onSubmit={(name) => send("/settings/templates/add", { name })} />
              <p className="mt-2 text-[12px] text-muted-foreground">A new template starts as a copy of the first one. The last stage in any list is the closed stage for projects using it.</p>
              <SlaCheck templates={data.templates} busy={busy} send={send} />
            </Panel>
            <div className="grid grid-cols-1 gap-4 [&>*]:min-w-0">{/* alert types is a wide table: full width */}
              <Panel title="Document categories" hint="untick to keep a kind from partners and customers">
                <ul className="grid grid-cols-1 gap-2 text-[13px]">
                  {data.doc_categories.map((c) => (
                    <li key={c.id} className="flex items-center gap-2">
                      <span className="flex-1">{c.name}</span>
                      <label className="flex items-center gap-2 text-[12px] text-muted-foreground" title="Partners and customers on the project can see and download these">
                        <input type="checkbox" checked={c.partners} disabled={busy} onChange={(e) => send(`/settings/doc-categories/${c.id}/partners`, e.target.checked ? { partners: "on" } : {})}
                          aria-label={`Partners see ${c.name}`} className="h-3.5 w-3.5 accent-primary" />partners</label>
                      <button type="button" disabled={busy} onClick={() => send(`/settings/doc-categories/${c.id}/delete`, {}, `Delete category ${c.name}?`)} aria-label={`Delete ${c.name}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>
                    </li>
                  ))}
                </ul>
                <AddForm placeholder="New category name" label="New document category name" button="Add category" busy={busy} onSubmit={(name) => send("/settings/doc-categories/add", { name })} />
              </Panel>
              <AlertTypes key={JSON.stringify(data.alerts)} data={data} busy={busy} send={send} />
            </div>
          </>
        )}
        {section === "notifications" && policyForm("notifications")}
        {section === "notifications" && (
          <div><Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/notifications/test-webhook")}>Send a test to the Teams webhook</Button></div>
        )}
        {section === "notifications" && (
          <Toggles data={data} busy={busy} send={send} title="Channels" keys={[
            { key: "notify_email_enabled", label: "Email notifications on project events (stage changes, approvals, assignments, mentions, due tasks)" },
            { key: "notify_teams_enabled", label: "Teams channel posts for stage changes and decisions, plus the daily alert digest" },
          ]} extra={<>
            {!data.m365.connected && <p className="basis-full text-[13px] text-warn" role="note">Microsoft 365 is not connected (Settings → Integrations), so email and Teams channel posts cannot be delivered. The bell and the Teams webhook still work.</p>}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/integrations/test-email")}>Send test email</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/integrations/test-teams")}>Send test Teams message</Button>
          </>} />
        )}
        {section === "integrations" && (
          <>
            <Microsoft key={`${data.m365.azure_app.client_id ?? ""}|${data.m365.azure_app.tenant_id ?? ""}|${data.m365.oauth_client_configured}`} data={data} busy={busy} send={send} teamId={teamId} onTeam={(id) => { setTeamId(id); void load(id) }} />
            <Toggles data={data} busy={busy} send={send} title="OneDrive" keys={[
              { key: "onedrive_mirror_uploads_enabled", label: "Mirror every uploaded document to OneDrive" },
            ]} />
            {policyForm("integrations")}
          </>
        )}
        {section === "ai" && (
          <AISettings key={JSON.stringify(data.policies.filter((p) => p.area === "ai").map((p) => p.value))}
            policies={data.policies.filter((p) => p.area === "ai")} busy={busy} send={send}
            schedule={policyForm("ai_schedule")} />
        )}
        {section === "documents" && <DocTemplates />}
        {section === "reports" && (
          <>
            {!data.public_url_set && <p className="rounded-md bg-warn-soft px-3 py-2 text-[13px] text-warn">Set the public web address under General, so the links in scheduled mail point at Odin and not at the server's own name.</p>}
            {policyForm("reports")}
            <div><Button size="sm" variant="outline" disabled={busy} onClick={() => send("/settings/reports/send-test")}>Send this week's report to me now</Button></div>
          </>
        )}
        {section === "api" && <ApiTokens tokens={data.api_tokens} busy={busy} send={send} />}
        {section === "map" && <SystemMap />}
        {section === "audit" && (
          <>
            {policyForm("audit")}
            <Panel title="Archives" hint="written nightly before rows are removed; included in every backup">
              {data.audit_archives.length === 0 ? <p className="text-[13px] text-muted-foreground">Nothing archived yet: no row is older than the retention period.</p> : (
                <ul className="grid grid-cols-1 gap-1 text-[13px]">{data.audit_archives.map((a) => <li key={a.name} className="flex justify-between gap-3"><span className="font-mono text-[12px]">{a.name}</span><span className="text-muted-foreground">{bytes(a.size)}</span></li>)}</ul>
              )}
              <p className="mt-3 text-[12px] text-muted-foreground">The full trail is on the <a href="/audit-logs" className="text-primary-text hover:underline">Audit log</a> page, with a CSV export.</p>
            </Panel>
          </>
        )}
        {section === "backups" && data.backups && (
          <>
            <Scheduler view={data.backups} busy={busy} send={send} />
            {policyForm("backups")}
            <BackupHistory runs={data.backups.runs} />
          </>
        )}
      </div>
    </div>
  )
}

// One admin policy area, drawn from the server's own list (policies.py), so a
// limit or a choice is defined once. Numbers carry their range; ticks post "on".
// a card's subtitle, where the title alone leaves a question
const GROUP_HINTS: Record<string, string> = {
  "Sessions": "applies at everyone's next request", "Sign-up links": "links are made and revoked on the Users page",
  "Where copies go": "a local copy is always kept on the server", "Watching the server": "applies from the next heartbeat",
  "Health colours": "green, amber or red on every project",
}
// the longer explanation of a setting, one tap away
function WhatIsThis({ label, text }: { label: string; text: string }) {
  return (
    <Popover>
      <PopoverTrigger render={<button type="button" />} aria-label={`What is ${label}?`} className="ml-1 rounded-sm font-medium text-primary-text hover:underline">What is this?</PopoverTrigger>
      <PopoverContent align="start" className="w-80 text-[13px] leading-relaxed wrap-anywhere">{text}</PopoverContent>
    </Popover>
  )
}
const DATE_EXAMPLES: Record<string, string> = { "d MMM yyyy": "27 Sep", "yyyy-MM-dd": "2026-09-27", "dd/MM/yyyy": "27/09/2026", "MM/dd/yyyy": "09/27/2026" }
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
// The system map is a self-contained page shipped with each release; the
// change log opens first. It follows the app's light or dark theme.
function SystemMap() {
  return (
    <iframe title="Odin System Map" src={`/settings/map/page?embed=1&tab=changes&theme=${isDark() ? "dark" : "light"}`}
      className="h-[calc(100dvh-200px)] min-h-[640px] w-full rounded-xl border border-border bg-background" />
  )
}

function PolicyForm({ area, title, hint, policies, templates, busy, send }: {
  area: Policy["area"]; title: string; hint?: string; policies: Policy[]; templates: SettingsData["templates"]; busy: boolean; send: Send
}) {
  const [v, setV] = useState<Record<string, Policy["value"]>>(() => Object.fromEntries(policies.map((p) => [p.key, p.value])))
  const dirty = policies.some((p) => JSON.stringify(p.value) !== JSON.stringify(v[p.key]))
  function submit(e: FormEvent) {
    e.preventDefault()
    const fields: Record<string, string> = {}
    for (const p of policies) {
      const x = v[p.key]
      if (p.kind === "bool") fields[p.key] = x ? "on" : "0"   // explicit: an absent tick would read as off
      else fields[p.key] = Array.isArray(x) ? x.join(",") : String(x)
    }
    void send(`/settings/policies/${area}`, fields)
  }
  const optionLabel = (p: Policy, c: string) =>
    p.key === "default_template" ? templates.find((t) => String(t.id) === c)?.name ?? c
      : p.key === "date_format" ? DATE_EXAMPLES[c] ?? c
        : p.key === "default_theme" ? (c === "system" ? "Follow the device" : cap(c)) : p.key === "default_accent" ? cap(c)
          : p.key === "mfa_required" ? ({ off: "Optional (each person decides)", admins: "Required for admins", everyone: "Required for everyone" }[c] ?? c) : c
  return (
    <Panel title={title} hint={hint}>
      <form onSubmit={submit} className="grid grid-cols-1 gap-4">
        <div className="grid grid-cols-1 gap-4">
          {policies.map((p) => (
            <div key={p.key} className="grid min-w-0 content-start gap-1">
              {p.kind === "bool" ? (
                <label className="flex items-start gap-2 text-[13px] font-medium">
                  <Switch checked={!!v[p.key]} onCheckedChange={(c) => setV({ ...v, [p.key]: c })} className="mt-1" />{p.label}
                </label>
              ) : (
                <label htmlFor={`pol-${p.key}`} className="text-[13px] font-medium">{p.label}</label>
              )}
              {p.kind === "int" && (
                <Input id={`pol-${p.key}`} type="number" min={p.min} max={p.max} required value={String(v[p.key])} onChange={(e) => setV({ ...v, [p.key]: e.target.value === "" ? "" : Number(e.target.value) })} className="h-8 w-28 text-[13px]" />
              )}
              {p.kind === "time" && (
                <Input id={`pol-${p.key}`} type="time" required value={String(v[p.key])} onChange={(e) => setV({ ...v, [p.key]: e.target.value })} className="h-8 w-32 text-[13px]" />
              )}
              {(p.kind === "url" || p.kind === "domains" || p.kind === "emails") && (
                <Input id={`pol-${p.key}`} type={p.kind === "url" ? "url" : "text"} maxLength={p.max} placeholder={p.key === "sharepoint_site" ? "https://contoso.sharepoint.com/sites/IT" : p.key === "teams_webhook_url" ? "https://…logic.azure.com/workflows/…" : p.kind === "url" ? "https://odin.example.com" : p.kind === "emails" ? "ceo@company.com, delivery@company.com" : "partner.com, vendor.ae"}
                  value={Array.isArray(v[p.key]) ? (v[p.key] as string[]).join(", ") : String(v[p.key] ?? "")} onChange={(e) => setV({ ...v, [p.key]: e.target.value })} className="h-8 max-w-md text-[13px]" />
              )}
              {p.kind === "text" && !p.multiline && (
                <Input id={`pol-${p.key}`} required maxLength={p.max} value={String(v[p.key])} onChange={(e) => setV({ ...v, [p.key]: e.target.value })} className="h-8 max-w-sm text-[13px]" />
              )}
              {p.kind === "text" && p.multiline && (
                <textarea id={`pol-${p.key}`} rows={4} maxLength={p.max} value={String(v[p.key] ?? "")} onChange={(e) => setV({ ...v, [p.key]: e.target.value })}
                  className="w-full max-w-2xl rounded-md border border-input bg-background p-2 text-[13px] leading-relaxed" />
              )}
              {p.kind === "dates" && (
                <textarea id={`pol-${p.key}`} rows={5} maxLength={p.max} value={String(v[p.key] ?? "")} onChange={(e) => setV({ ...v, [p.key]: e.target.value })} spellCheck={false}
                  placeholder={"2026-12-02 National Day\n2027-03-20 to 2027-03-22 Eid al-Fitr"} className="w-full max-w-2xl rounded-md border border-input bg-background p-2 font-mono text-[13px]" />
              )}
              {p.kind === "lines" && (
                <textarea id={`pol-${p.key}`} rows={4} maxLength={p.max} value={String(v[p.key] ?? "")} onChange={(e) => setV({ ...v, [p.key]: e.target.value })} spellCheck={false}
                  placeholder={"SOC overview | https://kibana.example.com/app/dashboards#/view/…?embed=true"} className="w-full max-w-2xl rounded-md border border-input bg-background p-2 font-mono text-[13px]" />
              )}
              {p.kind === "choice" && (
                <select id={`pol-${p.key}`} value={String(v[p.key])} onChange={(e) => setV({ ...v, [p.key]: e.target.value })} className={cn(selectClass, "max-w-sm")}>
                  {p.key === "default_template" && <option value="">First template ({templates[0]?.name ?? "none"})</option>}
                  {(p.choices ?? []).map((c) => <option key={c} value={c}>{optionLabel(p, c)}</option>)}
                </select>
              )}
              {p.kind === "multi" && (
                <fieldset className="flex flex-wrap gap-2" aria-label={p.label}>
                  {(p.choices ?? []).map((c) => {
                    const list = (v[p.key] as string[]) ?? []
                    const on = list.includes(c)
                    return (
                      <label key={c} className={cn("flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1 text-[13px] has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50",
                        on ? "border-primary bg-accent text-accent-foreground" : "border-border text-nav-fg hover:bg-muted")}>
                        <input type="checkbox" className="sr-only" checked={on} onChange={() => setV({ ...v, [p.key]: on ? list.filter((x) => x !== c) : [...list, c] })} />{c}
                      </label>
                    )
                  })}
                </fieldset>
              )}
              {(p.hint || p.help) && (
                <p className="text-[12px] text-muted-foreground wrap-anywhere">
                  {p.hint ?? p.help}{p.kind === "int" && p.min != null ? ` ${p.min}–${p.max}.` : ""}
                  {p.hint && p.help && <WhatIsThis label={p.label} text={p.help} />}
                </p>
              )}
            </div>
          ))}
        </div>
        <div><Button type="submit" size="sm" loading={busy} disabled={!dirty}>Save</Button></div>
      </form>
    </Panel>
  )
}

// Read-only API tokens: shown once when made (in the notice above), then
// only their name, age, last use and expiry; revoking is immediate.
function ApiTokens({ tokens, busy, send }: { tokens: SettingsData["api_tokens"]; busy: boolean; send: Send }) {
  const [name, setName] = useState("")
  const [days, setDays] = useState("90")
  const now = new Date().toISOString()
  return (
    <>
      <Panel title="New token">
        <form onSubmit={(e) => { e.preventDefault(); void send("/settings/api-tokens", { name, days }).then((r) => { if (r) setName("") }) }} className="flex flex-wrap items-end gap-2">
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">What uses it<Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Power BI refresh" maxLength={80} required className="h-8 w-64 text-[13px]" /></label>
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Valid for
            <select value={days} onChange={(e) => setDays(e.target.value)} className={selectClass}><option value="30">30 days</option><option value="90">90 days</option><option value="365">1 year</option></select>
          </label>
          <Button type="submit" size="sm" loading={busy} disabled={!name.trim()}>Create token</Button>
        </form>
        <p className="mt-3 text-[12px] text-muted-foreground">
          Send it as <code className="font-mono">Authorization: Bearer &lt;token&gt;</code> to <code className="font-mono">/api/v1/projects</code>, <code className="font-mono">/api/v1/projects/&lt;id&gt;</code> and <code className="font-mono">/api/v1/projects/&lt;id&gt;/report</code>. It can read every project and change nothing. Behind Cloudflare Access, /api/v1 needs its own Access policy (a service token).
        </p>
      </Panel>
      <Panel title="Tokens">
        {tokens.length === 0 ? <p className="text-[13px] text-muted-foreground">No tokens yet.</p> : (
          <div className="overflow-x-auto"><table className="w-full text-[13px]">
            <thead><tr className="text-left text-[12px] text-muted-foreground">{["Name", "Made", "Last used", "Expires", ""].map((h) => <th key={h} className="pb-2 pr-3 font-normal">{h}</th>)}</tr></thead>
            <tbody>
              {tokens.map((t) => {
                const dead = !!t.revoked_at || t.expires_at < now
                return (
                  <tr key={t.id} className={cn("border-t border-border", dead && "text-muted-foreground")}>
                    <td className="py-2 pr-3 font-medium">{t.name}</td>
                    <td className="whitespace-nowrap py-2 pr-3"><Ago iso={t.created_at} /> · {t.created_by}</td>
                    <td className="whitespace-nowrap py-2 pr-3">{t.last_used_at ? <Ago iso={t.last_used_at} /> : "never"}</td>
                    <td className="whitespace-nowrap py-2 pr-3">{t.revoked_at ? "revoked" : t.expires_at < now ? "expired" : t.expires_at.slice(0, 10)}</td>
                    <td className="py-2 text-right">{!dead && <Button size="sm" variant="ghost" className="h-7 text-bad hover:text-bad" disabled={busy} onClick={() => send(`/settings/api-tokens/${t.id}/revoke`, {}, `Revoke ${t.name}? Anything using it stops working now.`)}>Revoke</Button>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table></div>
        )}
      </Panel>
    </>
  )
}

// Whether the schedule is really being kept: the scheduler process leaves a
// heartbeat every minute; without it, nothing runs on its own.
function Scheduler({ view, busy, send }: { view: BackupsView; busy: boolean; send: Send }) {
  return (
    <Panel title="Status">
      {view.scheduler_alive
        ? <p className="text-[13px]">The scheduler is running. Next backup: <span className="font-medium">{view.next_run ?? "no day selected"}</span>.</p>
        : <p className="rounded-md bg-warn-soft px-3 py-2 text-[13px] text-warn">
            {view.scheduler_seen ? <>The scheduler was last seen <Ago iso={view.scheduler_seen} />.</> : "The scheduler has never run."} Backups and the daily digest only happen on their own while it runs:
            start the <code className="font-mono text-[12px]">scheduler</code> service (docker compose up -d), or have cron run <code className="font-mono text-[12px]">python scheduler.py --once</code> every few minutes.
          </p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={busy} onClick={() => send("/settings/integrations/backup-now")}>Back up now</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/backups/test-share")}>Test the network share</Button>
      </div>
    </Panel>
  )
}

const bytes = (n: number | null) => (n == null ? "—" : n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)
function BackupHistory({ runs }: { runs: BackupRun[] }) {
  return (
    <Panel title="History" hint="the last 20 runs">
      {runs.length === 0 ? <p className="text-[13px] text-muted-foreground">No backups yet. Back up now to make the first one.</p> : (
        <div className="overflow-x-auto"><table className="w-full text-[13px]">
          <thead><tr className="text-left text-[12px] text-muted-foreground">{["When", "Result", "Restore test", "Copies", "Size"].map((h) => <th key={h} className="pb-2 pr-3 font-normal">{h}</th>)}</tr></thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-border align-top">
                <td className="whitespace-nowrap py-2 pr-3"><Ago iso={r.started_at} /><span className="block text-[12px] text-muted-foreground">{r.trigger}{r.actor ? ` · ${r.actor}` : ""}</span></td>
                <td className="py-2 pr-3">{r.ok ? <span className="text-ok">Done</span> : <span className="font-medium text-bad">Problem</span>}</td>
                <td className="py-2 pr-3">{r.restore_ok == null ? <span className="text-muted-foreground">off</span> : r.restore_ok ? <span className="text-ok">Passed</span> : <span className="font-medium text-bad">Failed</span>}
                  {r.restore_detail && <span className="block text-[12px] text-muted-foreground">{r.restore_detail}</span>}</td>
                <td className="py-2 pr-3 text-[13px]">{r.destinations}</td>
                <td className="whitespace-nowrap py-2 pr-3 text-muted-foreground">{bytes(r.size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </Panel>
  )
}

// Microsoft sign-in for staff: its own app registration (not the mail one),
// and the switch that hides the password form. The server refuses to require
// Microsoft until at least one admin keeps a password.
function Sso({ sso, busy, send }: { sso: SettingsData["sso"]; busy: boolean; send: Send }) {
  const [f, setF] = useState({ client_id: sso.client_id ?? "", tenant_id: sso.tenant_id ?? "", client_secret: "" })
  const [enforced, setEnforced] = useState(sso.enforced)
  const status = !sso.configured ? "Not set up: staff sign in with a password." : sso.enforced ? "Required: staff sign in with Microsoft only." : "Set up: staff can use Microsoft or a password."
  return (
    <Panel title="Microsoft sign-in" hint="staff; partners keep their email link">
      <form onSubmit={(e) => { e.preventDefault(); void send("/settings/sso", { ...f, ...(enforced ? { enforced: "on" } : {}) }).then((r) => { if (r) setF({ ...f, client_secret: "" }) }) }} className="grid grid-cols-1 gap-3">
        <p className="text-[13px]">{status}</p>
        <div className="grid grid-cols-1 gap-1 text-[13px]">
          <span className="text-muted-foreground">Redirect URI to add to the app registration (Authentication → Web)</span>
          <code className="w-fit max-w-full break-all rounded-md border border-border bg-secondary px-2 py-1 font-mono text-[12px]">{sso.redirect_uri}</code>
          <span className="text-muted-foreground">In Entra ID: a separate app registration, single tenant, ID tokens only; a client secret under Certificates &amp; secrets.</span>
        </div>
        <div className="grid grid-cols-1 max-w-md gap-2">
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Application (client) ID<Input value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })} className="h-8 font-mono text-[13px]" /></label>
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Directory (tenant) ID<Input value={f.tenant_id} onChange={(e) => setF({ ...f, tenant_id: e.target.value })} className="h-8 font-mono text-[13px]" /></label>
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Client secret<Input type="password" value={f.client_secret} onChange={(e) => setF({ ...f, client_secret: e.target.value })} placeholder={sso.has_secret ? "leave blank to keep the saved secret" : "paste the secret value"} className="h-8 text-[13px]" /></label>
        </div>
        <label className="flex items-start gap-2 text-[13px]">
          <Switch checked={enforced} onCheckedChange={setEnforced} disabled={!sso.configured} className="mt-1" />
          <span>Staff must sign in with Microsoft <span className="block text-[12px] text-muted-foreground">The password form disappears. Accounts ticked "Password" on the Users page ({sso.password_admins} admin{sso.password_admins === 1 ? "" : "s"} now) keep an emergency form at /login/password; each use is recorded and the admins are told.</span></span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" size="sm" loading={busy}>Save</Button>
          {sso.configured && <a href="/auth/microsoft" className={buttonVariants({ size: "sm", variant: "outline" })}>Try Microsoft sign-in</a>}
          {sso.configured && <Button type="button" size="sm" variant="ghost" className="ml-auto text-bad hover:text-bad" disabled={busy}
            onClick={() => send("/settings/sso", { clear: "1" }, "Remove Microsoft sign-in? Staff go back to passwords; anyone who only ever used Microsoft will need a password reset.")}>Remove</Button>}
        </div>
      </form>
    </Panel>
  )
}

// The on/off integration switches live in one route that saves all five at
// once, so each area posts its own boxes plus everyone else's saved values.
type ToggleKey = keyof SettingsData["toggles"]
function Toggles({ data, busy, send, title, keys, extra }: { data: SettingsData; busy: boolean; send: Send; title: string; keys: { key: ToggleKey; label: string }[]; extra?: ReactNode }) {
  const [t, setT] = useState(data.toggles)
  useEffect(() => { setT(data.toggles) }, [data.toggles])
  const dirty = keys.some((k) => t[k.key] !== data.toggles[k.key])
  function submit(e: FormEvent) {
    e.preventDefault()
    void send("/settings/integrations", Object.fromEntries((Object.keys(t) as ToggleKey[]).filter((k) => t[k]).map((k) => [k, "on"])))
  }
  return (
    <Panel title={title}>
      <form onSubmit={submit} className="grid grid-cols-1 gap-2 text-[13px]">
        {keys.map((i) => (
          <label key={i.key} className="flex items-start gap-2">
            <Switch checked={t[i.key]} onCheckedChange={(c) => setT({ ...t, [i.key]: c })} className="mt-1" />
            <span>{i.label}</span>
          </label>
        ))}
        <div><Button type="submit" size="sm" variant="outline" loading={busy} disabled={!dirty}>Save</Button></div>
      </form>
      {extra && <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">{extra}</div>}
    </Panel>
  )
}

function AddForm({ placeholder, label, button, busy, onSubmit }: { placeholder: string; label: string; button: string; busy: boolean; onSubmit: (name: string) => Promise<unknown> }) {
  const [name, setName] = useState("")
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) void onSubmit(name.trim()).then((r) => { if (r) setName("") }) }} className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={placeholder} aria-label={label} maxLength={80} className="h-8 w-full text-[13px] sm:w-72" />
      <Button type="submit" size="sm" variant="outline" loading={busy} disabled={!name.trim()}>{button}</Button>
    </form>
  )
}

function Template({ t, onlyOne, busy, send }: { t: SettingsData["templates"][number]; onlyOne: boolean; busy: boolean; send: Send }) {
  const [name, setName] = useState(t.name)   // remounted by key when the saved name changes
  const base = `/settings/templates/${t.id}`
  return (
    <div className="border-b border-border pb-4 last:border-0 last:pb-0">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <form onSubmit={(e) => { e.preventDefault(); if (name.trim() && name !== t.name) void send(`${base}/rename`, { name }) }} className="flex min-w-0 flex-1 items-center gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} aria-label={`Rename template ${t.name}`} maxLength={80} className="h-8 min-w-40 flex-1 text-[14px] font-semibold" />
          {name !== t.name && <Button type="submit" size="sm" variant="outline" loading={busy}>Rename</Button>}
        </form>
        <span className="whitespace-nowrap text-[12px] text-muted-foreground">{t.projects} project{t.projects === 1 ? "" : "s"}</span>
        <button type="button" disabled={busy || onlyOne} onClick={() => send(`${base}/delete`, {}, `Delete template ${t.name}? Projects keep their own copies.`)} aria-label={`Delete template ${t.name}`} className="text-muted-foreground hover:text-bad disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
      <StageListEditor key={stageRowsKey(t.stages)} rows={t.stages} busy={busy} send={send} label={t.name}
        paths={{ add: `${base}/stages/add`, rename: (s) => `${base}/stages/${s}/rename`, move: (s) => `${base}/stages/${s}/move`, remove: (s) => `${base}/stages/${s}/delete`, sla: `${base}/sla` }} />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => send(`${base}/sla/from-measured`, {}, "Overwrite this template's SLAs with measured averages?")}>Set SLAs from measured averages</Button>
        <span className="text-[12px] text-muted-foreground">From projects created with this template. Applies to new projects; existing ones keep their own.</span>
      </div>
    </div>
  )
}

function AlertTypes({ data, busy, send }: { data: SettingsData; busy: boolean; send: Send }) {
  const [rows, setRows] = useState(data.alerts)   // remounted by key when saved values change
  function submit(e: FormEvent) {
    e.preventDefault()
    // the route reads checkboxes as "on" and thresholds by name; absent means off
    const fields: Record<string, string> = {}
    for (const a of rows) {
      if (a.threshold_days != null) fields[`threshold::${a.key}`] = String(a.threshold_days)
      fields[`severity::${a.key}`] = a.severity
      if (a.notify_email) fields[`notify_email::${a.key}`] = "on"
      if (a.notify_teams) fields[`notify_teams::${a.key}`] = "on"
      if (a.notify_inapp) fields[`notify_inapp::${a.key}`] = "on"
    }
    void send("/settings/alerts", fields)
  }
  const set = (key: string, patch: Partial<SettingsData["alerts"][number]>) => setRows(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  return (
    <Panel title="Alert types" hint="In-app is the master switch; email and Teams also need their toggle under Integrations">
      <form onSubmit={submit}>
        <div className="overflow-x-auto"><table className="w-full text-[13px]">
          <thead><tr className="text-left text-[12px] font-normal text-muted-foreground">{["Alert", "Threshold (days)", "Severity", "Email", "Teams", "In-app"].map((h) => <th key={h} className="pb-2 pr-2 font-normal">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.key} className="border-t border-border">
                <td className="py-2 pr-2">{a.title}</td>
                <td className="py-2 pr-2">{a.threshold_days != null ? <Input type="number" min={0} value={a.threshold_days} onChange={(e) => set(a.key, { threshold_days: Number(e.target.value) })} aria-label={`Threshold days for ${a.title}`} className="h-7 w-16 text-[13px]" /> : <span className="text-muted-foreground">—</span>}</td>
                <td className="py-2 pr-2">
                  <select value={a.severity} onChange={(e) => set(a.key, { severity: e.target.value as typeof a.severity })} aria-label={`Severity for ${a.title}`} className={cn(selectClass, "h-7 text-[13px]")}>
                    <option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option>
                  </select>
                </td>
                {(["notify_email", "notify_teams", "notify_inapp"] as const).map((k) => (
                  <td key={k} className="py-2 pr-2"><input type="checkbox" checked={a[k]} onChange={(e) => set(a.key, { [k]: e.target.checked })} aria-label={`${k.replace("notify_", "")} notification for ${a.title}`} className="h-3.5 w-3.5 accent-primary" /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table></div>
        <Button type="submit" size="sm" variant="outline" className="mt-3" loading={busy}>Save alert settings</Button>
      </form>
    </Panel>
  )
}

function Microsoft({ data, busy, send, teamId, onTeam }: { data: SettingsData; busy: boolean; send: Send; teamId: string; onTeam: (id: string) => void }) {
  const m = data.m365
  const [editing, setEditing] = useState(!m.oauth_client_configured)
  const [app, setApp] = useState({ client_id: m.azure_app.client_id ?? "", tenant_id: m.azure_app.tenant_id ?? "", client_secret: "" })
  const [channelId, setChannelId] = useState(m.channel_id ?? "")   // remounted by key when the app registration changes
  return (
    <Panel title="Microsoft 365" hint="mail, Teams and OneDrive through one Azure app">
      {m.oauth_client_configured && !editing && (
        <p className="mb-2 text-[13px]">Azure app <span className="font-mono text-[13px]">{m.azure_app.client_id}</span> <span className="text-muted-foreground">({m.azure_app.source})</span>
          <button type="button" onClick={() => setEditing(true)} className="ml-2 text-[12px] text-primary-text hover:underline">Edit</button></p>
      )}
      {editing && (
        <form onSubmit={(e) => { e.preventDefault(); void send("/settings/azure-app", app).then((r) => { if (r) setApp({ ...app, client_secret: "" }) }) }} className="mb-3 grid grid-cols-1 max-w-md gap-2">
          {!m.oauth_client_configured && <p className="text-[13px] text-muted-foreground">Enter the details of the app registration made once in the Azure portal (Microsoft Entra ID → App registrations): its tenant ID, client ID and a client secret.</p>}
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Application (client) ID<Input value={app.client_id} onChange={(e) => setApp({ ...app, client_id: e.target.value })} required aria-label="Application (client) ID" className="h-8 font-mono text-[13px]" /></label>
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Directory (tenant) ID<Input value={app.tenant_id} onChange={(e) => setApp({ ...app, tenant_id: e.target.value })} required aria-label="Directory (tenant) ID" className="h-8 font-mono text-[13px]" /></label>
          <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Client secret<Input type="password" value={app.client_secret} onChange={(e) => setApp({ ...app, client_secret: e.target.value })} required={!m.azure_app.has_secret} aria-label="Client secret" placeholder={m.azure_app.has_secret ? "leave blank to keep the saved secret" : "paste the secret value, not its ID"} className="h-8 text-[13px]" /></label>
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={busy} disabled={!app.client_id || !app.tenant_id}>Save</Button>
            {m.oauth_client_configured && <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>}
            {m.oauth_client_configured && <Button type="button" size="sm" variant="outline" className="ml-auto text-bad hover:text-bad" disabled={busy} onClick={() => send("/settings/azure-app/clear", {}, "Clear Azure credentials and disconnect Microsoft 365?")}>Clear & disconnect</Button>}
          </div>
        </form>
      )}
      {m.oauth_client_configured && !m.connected && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <a href="/integrations/connect" className={buttonVariants({ size: "sm" })}>Connect Microsoft 365</a>
          <span className="text-[13px] text-muted-foreground">Sign in with an admin account and grant Outlook, Teams and OneDrive access.</span>
        </div>
      )}
      {m.connected && (
        <div className="mt-2 grid grid-cols-1 gap-2 text-[13px]">
          <p>Connected as <span className="font-medium">{m.connected_email ?? "—"}</span> · Teams channel <span className="font-medium">{m.channel_id ? `${m.team_name} / ${m.channel_name}` : "not selected yet"}</span>
            <button type="button" disabled={busy} onClick={() => send("/integrations/disconnect", {}, "Disconnect Microsoft 365? Notifications, mirroring and backup stop until you reconnect.")} className="ml-2 text-[12px] text-bad hover:underline">Disconnect</button></p>
          {m.teams_error && <p className="text-[13px] text-bad">Could not load teams: {m.teams_error}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <select value={teamId} onChange={(e) => onTeam(e.target.value)} aria-label="Microsoft Teams team" className={selectClass}>
              <option value="">Choose a team…</option>{m.teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            {teamId && (
              <>
                <select value={channelId} onChange={(e) => setChannelId(e.target.value)} aria-label="Teams channel" className={selectClass}>
                  <option value="">Choose a channel…</option>{m.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <Button size="sm" variant="outline" disabled={busy || !channelId} onClick={() => send("/integrations/channel", { team_id: teamId, channel_id: channelId })}>Save channel</Button>
              </>
            )}
          </div>
        </div>
      )}
    </Panel>
  )
}
