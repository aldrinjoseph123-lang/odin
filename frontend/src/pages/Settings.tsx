import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { Trash2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { StageListEditor, stageRowsKey } from "@/components/StageListEditor"
import { ApiError, postForm, settingsData, type SettingsData, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { PageSkeleton } from "@/components/PageSkeleton"

const selectClass = "h-8 rounded-md border border-input bg-background px-2 text-[13px]"
type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

function Panel({ title, hint, children, id }: { title: string; hint?: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="rounded-lg border border-border p-4">
      <h3 className="mb-3 text-[12px] font-semibold text-nav-fg">{title}{hint && <span className="ml-2 font-normal text-muted-foreground">{hint}</span>}</h3>
      {children}
    </section>
  )
}

export default function Settings(_props: { user: User }) {
  const [data, setData] = useState<SettingsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [teamId, setTeamId] = useState("")
  const load = useCallback(async (team = teamId) => {
    try { setData(await settingsData(team)); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load settings") }
  }, [teamId])
  useEffect(() => { document.title = "Settings · Odin"; void load() }, [load])

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

  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!data) return <PageSkeleton />

  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Settings</h1>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <a href="/users" className={buttonVariants({ variant: "outline", size: "sm" })}>Users</a>
          <a href="/settings/rbac" className={buttonVariants({ variant: "outline", size: "sm" })}>Role permissions</a>
          <a href="/settings/contacts" className={buttonVariants({ variant: "outline", size: "sm" })}>Contacts & partners</a>
          <a href="/audit-logs" className={buttonVariants({ variant: "outline", size: "sm" })}>Audit log</a>
        </div>
      </div>
      {notice && (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status">
          <span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* min-w-0 on every grid item: a wide table scrolls inside its panel
          instead of stretching the page on a phone */}
      <div className="mt-3 grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <Panel title="Stage templates" hint="a new project copies one, then owns its list" id="templates">
          <div className="grid gap-5">
            {data.templates.map((t) => <Template key={`${t.id}:${t.name}`} t={t} onlyOne={data.templates.length <= 1} busy={busy} send={send} />)}
          </div>
          <AddForm placeholder="New template name (e.g. EDR rollout)" label="New template name" button="Add template" busy={busy} onSubmit={(name) => send("/settings/templates/add", { name })} />
          <p className="mt-2 text-[11.5px] text-muted-foreground">A new template starts as a copy of the first one. The last stage in any list is the closed stage for projects using it.</p>
        </Panel>

        <div className="grid content-start gap-4 [&>*]:min-w-0">
          <Panel title="Document categories">
            <ul className="grid gap-1.5 text-[13px]">
              {data.doc_categories.map((c) => (
                <li key={c.id} className="flex items-center gap-2">
                  <span className="flex-1">{c.name}</span>
                  <button type="button" disabled={busy} onClick={() => send(`/settings/doc-categories/${c.id}/delete`, {}, `Delete category ${c.name}?`)} aria-label={`Delete ${c.name}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>
                </li>
              ))}
            </ul>
            <AddForm placeholder="New category name" label="New document category name" button="Add category" busy={busy} onSubmit={(name) => send("/settings/doc-categories/add", { name })} />
          </Panel>
          <AlertTypes key={JSON.stringify(data.alerts)} data={data} busy={busy} send={send} />
        </div>

        <Microsoft key={`${data.m365.azure_app.client_id ?? ""}|${data.m365.azure_app.tenant_id ?? ""}|${data.m365.oauth_client_configured}`} data={data} busy={busy} send={send} teamId={teamId} onTeam={(id) => { setTeamId(id); void load(id) }} />
        <Integrations key={JSON.stringify(data.toggles)} data={data} busy={busy} send={send} />
      </div>
    </div>
  )
}

function AddForm({ placeholder, label, button, busy, onSubmit }: { placeholder: string; label: string; button: string; busy: boolean; onSubmit: (name: string) => Promise<unknown> }) {
  const [name, setName] = useState("")
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) void onSubmit(name.trim()).then(() => setName("")) }} className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={placeholder} aria-label={label} maxLength={80} className="h-8 w-full text-[13px] sm:w-72" />
      <Button type="submit" size="sm" variant="outline" disabled={busy || !name.trim()}>{button}</Button>
    </form>
  )
}

function Template({ t, onlyOne, busy, send }: { t: SettingsData["templates"][number]; onlyOne: boolean; busy: boolean; send: Send }) {
  const [name, setName] = useState(t.name)   // remounted by key when the saved name changes
  const base = `/settings/templates/${t.id}`
  return (
    <div className="border-b border-border pb-4 last:border-0 last:pb-0">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <form onSubmit={(e) => { e.preventDefault(); if (name.trim() && name !== t.name) void send(`${base}/rename`, { name }) }} className="flex min-w-0 flex-1 items-center gap-1.5">
          <Input value={name} onChange={(e) => setName(e.target.value)} aria-label={`Rename template ${t.name}`} maxLength={80} className="h-8 min-w-40 flex-1 text-[13.5px] font-semibold" />
          {name !== t.name && <Button type="submit" size="sm" variant="outline" disabled={busy}>Rename</Button>}
        </form>
        <span className="whitespace-nowrap text-[12px] text-muted-foreground">{t.projects} project{t.projects === 1 ? "" : "s"}</span>
        <button type="button" disabled={busy || onlyOne} onClick={() => send(`${base}/delete`, {}, `Delete template ${t.name}? Projects keep their own copies.`)} aria-label={`Delete template ${t.name}`} className="text-muted-foreground hover:text-bad disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
      <StageListEditor key={stageRowsKey(t.stages)} rows={t.stages} busy={busy} send={send} label={t.name}
        paths={{ add: `${base}/stages/add`, rename: (s) => `${base}/stages/${s}/rename`, move: (s) => `${base}/stages/${s}/move`, remove: (s) => `${base}/stages/${s}/delete`, sla: `${base}/sla` }} />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => send(`${base}/sla/from-measured`, {}, "Overwrite this template's SLAs with measured averages?")}>Set SLAs from measured averages</Button>
        <span className="text-[11.5px] text-muted-foreground">From projects created with this template. Applies to new projects; existing ones keep their own.</span>
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
          <thead><tr className="text-left text-[11.5px] font-normal text-muted-foreground">{["Alert", "Threshold (days)", "Severity", "Email", "Teams", "In-app"].map((h) => <th key={h} className="pb-1.5 pr-2 font-normal">{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.key} className="border-t border-border">
                <td className="py-1.5 pr-2">{a.title}</td>
                <td className="py-1.5 pr-2">{a.threshold_days != null ? <Input type="number" min={0} value={a.threshold_days} onChange={(e) => set(a.key, { threshold_days: Number(e.target.value) })} aria-label={`Threshold days for ${a.title}`} className="h-7 w-16 text-[12.5px]" /> : <span className="text-muted-foreground">—</span>}</td>
                <td className="py-1.5 pr-2">
                  <select value={a.severity} onChange={(e) => set(a.key, { severity: e.target.value as typeof a.severity })} aria-label={`Severity for ${a.title}`} className={cn(selectClass, "h-7 text-[12.5px]")}>
                    <option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option>
                  </select>
                </td>
                {(["notify_email", "notify_teams", "notify_inapp"] as const).map((k) => (
                  <td key={k} className="py-1.5 pr-2"><input type="checkbox" checked={a[k]} onChange={(e) => set(a.key, { [k]: e.target.checked })} aria-label={`${k.replace("notify_", "")} notification for ${a.title}`} className="h-3.5 w-3.5 accent-primary" /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table></div>
        <Button type="submit" size="sm" variant="outline" className="mt-3" disabled={busy}>Save alert settings</Button>
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
        <p className="mb-2 text-[13px]">Azure app <span className="font-mono text-[12.5px]">{m.azure_app.client_id}</span> <span className="text-muted-foreground">({m.azure_app.source})</span>
          <button type="button" onClick={() => setEditing(true)} className="ml-2 text-[12px] text-primary-text hover:underline">Edit</button></p>
      )}
      {editing && (
        <form onSubmit={(e) => { e.preventDefault(); void send("/settings/azure-app", app).then(() => setApp({ ...app, client_secret: "" })) }} className="mb-3 grid max-w-md gap-2">
          {!m.oauth_client_configured && <p className="text-[12.5px] text-muted-foreground">Enter the Azure AD app registration's details (AZURE_SETUP.md explains the one-time step in the Azure portal).</p>}
          <label className="grid gap-1 text-[12px] text-muted-foreground">Application (client) ID<Input value={app.client_id} onChange={(e) => setApp({ ...app, client_id: e.target.value })} required aria-label="Application (client) ID" className="h-8 font-mono text-[12.5px]" /></label>
          <label className="grid gap-1 text-[12px] text-muted-foreground">Directory (tenant) ID<Input value={app.tenant_id} onChange={(e) => setApp({ ...app, tenant_id: e.target.value })} required aria-label="Directory (tenant) ID" className="h-8 font-mono text-[12.5px]" /></label>
          <label className="grid gap-1 text-[12px] text-muted-foreground">Client secret<Input type="password" value={app.client_secret} onChange={(e) => setApp({ ...app, client_secret: e.target.value })} required={!m.azure_app.has_secret} aria-label="Client secret" placeholder={m.azure_app.has_secret ? "leave blank to keep the saved secret" : "paste the secret value, not its ID"} className="h-8 text-[12.5px]" /></label>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy || !app.client_id || !app.tenant_id}>Save</Button>
            {m.oauth_client_configured && <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>}
            {m.oauth_client_configured && <Button type="button" size="sm" variant="outline" className="ml-auto text-bad hover:text-bad" disabled={busy} onClick={() => send("/settings/azure-app/clear", {}, "Clear Azure credentials and disconnect Microsoft 365?")}>Clear & disconnect</Button>}
          </div>
        </form>
      )}
      {m.oauth_client_configured && !m.connected && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <a href="/integrations/connect" className={buttonVariants({ size: "sm" })}>Connect Microsoft 365</a>
          <span className="text-[12.5px] text-muted-foreground">Sign in with an admin account and grant Outlook, Teams and OneDrive access.</span>
        </div>
      )}
      {m.connected && (
        <div className="mt-2 grid gap-2 text-[13px]">
          <p>Connected as <span className="font-medium">{m.connected_email ?? "—"}</span> · Teams channel <span className="font-medium">{m.channel_id ? `${m.team_name} / ${m.channel_name}` : "not selected yet"}</span>
            <button type="button" disabled={busy} onClick={() => send("/integrations/disconnect", {}, "Disconnect Microsoft 365? Notifications, mirroring and backup stop until you reconnect.")} className="ml-2 text-[12px] text-bad hover:underline">Disconnect</button></p>
          {m.teams_error && <p className="text-[12.5px] text-bad">Could not load teams: {m.teams_error}</p>}
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

function Integrations({ data, busy, send }: { data: SettingsData; busy: boolean; send: Send }) {
  const [t, setT] = useState(data.toggles)   // remounted by key when saved values change
  const items: { key: keyof typeof t; label: string }[] = [
    { key: "notify_email_enabled", label: "Email notifications on project events (new project, stage change, task assigned)" },
    { key: "notify_teams_enabled", label: "Teams channel notifications for the same events, plus the daily alert digest" },
    { key: "onedrive_mirror_uploads_enabled", label: "Mirror every uploaded document to OneDrive" },
    { key: "onedrive_backup_enabled", label: "Allow scheduled full backups to OneDrive (needs the cron entry from AZURE_SETUP.md)" },
    { key: "guest_links_enabled", label: "Keep the legacy anonymous guest links working (turn off once invited partner and customer accounts have replaced them; every old link then stops)" },
  ]
  function submit(e: FormEvent) {
    e.preventDefault()
    void send("/settings/integrations", Object.fromEntries(items.filter((i) => t[i.key]).map((i) => [i.key, "on"])))
  }
  return (
    <Panel title="Integrations">
      <form onSubmit={submit} className="grid gap-2 text-[13px]">
        {items.map((i) => (
          <label key={i.key} className="flex items-start gap-2">
            <input type="checkbox" checked={t[i.key]} onChange={(e) => setT({ ...t, [i.key]: e.target.checked })} aria-label={i.label} className="mt-1 h-3.5 w-3.5 accent-primary" />
            <span>{i.label}</span>
          </label>
        ))}
        <div><Button type="submit" size="sm" variant="outline" disabled={busy}>Save integration settings</Button></div>
      </form>
      <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/integrations/test-email")}>Send test email</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/integrations/test-teams")}>Send test Teams message</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => send("/settings/integrations/backup-now")}>Back up to OneDrive now</Button>
      </div>
    </Panel>
  )
}
