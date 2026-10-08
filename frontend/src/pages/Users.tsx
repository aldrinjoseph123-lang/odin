import { useCallback, useEffect, useState, type FormEvent } from "react"
import { Link } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { UserAvatar } from "@/components/UserAvatar"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, createSignupLink, postForm, revokeAllSignupLinks, revokeSignupLink, signupLinks, users as fetchUsers, type AdminUser, type SignupLinks, type User, type UsersData } from "@/lib/api"
import { cn } from "@/lib/utils"
import { fmtWhen } from "@/lib/format"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

const fmt = (iso: string | null, withTime = false) => fmtWhen(iso, withTime)
const selectClass = "h-7 rounded-md border border-input bg-background px-2 text-[13px] disabled:opacity-60"

export default function Users(_props: { user: User }) {
  const [data, setData] = useState<UsersData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setData(await fetchUsers()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load users") }
  }, [])
  useEffect(() => { void load(); document.title = "Users · Odin" }, [load])

  async function send(path: string, fields: Record<string, string>, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      setNotice(r.messages.join(" ") || null)
      await load()
    } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }

  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />
  const pending = data.users.filter((u) => u.pending)
  const people = data.users.filter((u) => !u.pending)

  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Users</h1>
        <p className="text-[13px] text-muted-foreground">{people.filter((u) => u.active).length} active · {people.filter((u) => u.kind === "external").length} external{pending.length ? ` · ${pending.length} waiting` : ""}</p>
        <div className="ml-auto flex items-center gap-2">
          <a href="/users/export.csv" className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>
        </div>
      </div>
      {notice && (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-2 text-[13px]" role="status">
          <span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {pending.length > 0 && <Pending people={pending} roles={data.roles} busy={busy} send={send} />}

      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 overflow-auto panel">
          <table className="w-full border-collapse text-[13px]">
            <thead className="bg-card">
              <tr className="border-b border-border text-left text-[12px] font-normal text-muted-foreground">
                {["Name", "Username", "Email", "Role", "Status", "Sign-in", "Last sign-in", "Created", ""].map((h, i) => <th key={i} className={cn("px-3 py-2 font-normal", (i === 1 || i >= 6) && i !== 8 && "hidden xl:table-cell")}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {people.map((u) => <Row key={`${u.id}:${u.email ?? ""}`} u={u} roles={data.roles} me={data.me} microsoftOnly={data.microsoft_only} busy={busy} send={send} />)}
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-1 content-start gap-4">
          <AddUser roles={data.roles} busy={busy} send={send} />
          <SignupLinksPanel />
        </div>
      </div>
    </div>
  )
}

// Colleagues who signed in with Microsoft for the first time: an admin lets
// them in with a role, or declines (the account stays, inactive).
function Pending({ people, roles, busy, send }: { people: AdminUser[]; roles: string[]; busy: boolean; send: (p: string, f: Record<string, string>, c?: string) => Promise<void> }) {
  const [role, setRole] = useState<Record<number, string>>({})
  return (
    <section className="mt-3 rounded-lg bg-warn-soft/60 p-4" aria-label="Waiting for approval">
      <h2 className="mb-2 text-[12px] font-semibold text-nav-fg">Waiting for approval <span className="font-normal text-muted-foreground">asked to use Odin, not yet allowed in</span></h2>
      <ul className="grid grid-cols-1 gap-2">
        {people.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="min-w-0 flex-1"><span className="font-medium">{u.name}</span> <span className="text-muted-foreground">{u.username} · {u.email} · asked {fmt(u.created_at, true)}
              {u.signup_label ? ` · via sign-up link "${u.signup_label}"` : u.microsoft ? " · via Microsoft sign-in" : ""}{u.signup_project ? ` · joins ${u.signup_project} as ${u.signup_project_role}` : ""}
              {u.notify_via === "teams" ? " · prefers Teams" : ""}</span></span>
            <select value={role[u.id] ?? (u.signup_label ? u.role : "Viewer")} onChange={(e) => setRole({ ...role, [u.id]: e.target.value })} aria-label={`Role for ${u.name}`} className={selectClass}>
              {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <Button size="sm" className="h-7" disabled={busy} onClick={() => send(`/users/${u.id}/approve`, { role: role[u.id] ?? (u.signup_label ? u.role : "Viewer") })}>Approve</Button>
            <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => send(`/users/${u.id}/decline`, {}, `Decline ${u.name}? They stay unable to sign in.`)}>Decline</Button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Row({ u, roles, me, microsoftOnly, busy, send }: { u: AdminUser; roles: string[]; me: number; microsoftOnly: boolean; busy: boolean; send: (p: string, f: Record<string, string>, c?: string) => Promise<void> }) {
  const [email, setEmail] = useState(u.email ?? "")   // the row remounts (key) when the saved email changes
  const [pw, setPw] = useState("")
  const [resetting, setResetting] = useState(false)
  const self = u.id === me
  return (
    <tr className={cn("border-b border-border last:border-0", !u.active && "text-muted-foreground")}>
      <td className="px-3 py-2 font-medium"><span className="inline-flex items-center gap-2"><UserAvatar name={u.name} url={u.avatar_url} className="h-6 w-6" /><span title={u.username}>{u.name}</span></span>{u.kind === "external" && <Badge variant="secondary" className="ml-2">External</Badge>}{self && <span className="ml-2 text-[12px] font-normal text-muted-foreground">you</span>}</td>
      <td className="hidden px-3 py-2 text-muted-foreground xl:table-cell">{u.username}</td>
      <td className="px-3 py-2">
        <form onSubmit={(e) => { e.preventDefault(); if (email !== (u.email ?? "")) void send(`/users/${u.id}/email`, { email }) }} className="flex items-center gap-1">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" aria-label={`Email for ${u.name}`} className="h-7 w-40 text-[13px]" />
          {email !== (u.email ?? "") && <Button type="submit" size="sm" variant="outline" className="h-7" disabled={busy}>Save</Button>}
        </form>
      </td>
      <td className="px-3 py-2">
        {/* External is a kind of account, not a role to hand out: an invited
            partner stays External, staff never become it */}
        <select value={u.role} disabled={self || busy || u.kind === "external"} onChange={(e) => send(`/users/${u.id}/role`, { role: e.target.value })} aria-label={`Role for ${u.name}`} className={selectClass}>
          {roles.filter((r) => (r === "External") === (u.kind === "external")).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </td>
      <td className="px-3 py-2">{u.active ? "Active" : <span className="text-muted-foreground">Deactivated</span>}</td>
      <td className="px-3 py-2 text-[13px]">
        {u.kind === "external" ? <span className="text-muted-foreground">Email link</span> : (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {u.microsoft && <Badge variant="secondary">Microsoft</Badge>}
            {u.two_step && <span className="inline-flex items-center gap-1"><Badge variant="secondary">Two-step</Badge>
              <Button size="sm" variant="ghost" className="h-6 px-2 text-[12px]" disabled={busy} aria-label={`Reset two-step sign-in for ${u.name}`}
                onClick={() => send(`/users/${u.id}/two-step-reset`, {}, `Reset two-step sign-in for ${u.name}? Use this when they lost their phone and recovery codes. Their sessions end.`)}>Reset</Button></span>}
            <label className="flex items-center gap-2 whitespace-nowrap" title="Keeps a password when staff must use Microsoft: the emergency way in">
              <input type="checkbox" checked={u.password_login} disabled={busy} onChange={(e) => send(`/users/${u.id}/password-login`, e.target.checked ? { allowed: "on" } : {})} className="h-3.5 w-3.5 accent-primary" />
              Password
            </label>
          </span>
        )}
      </td>
      <td className="hidden whitespace-nowrap px-3 py-2 text-muted-foreground xl:table-cell">{u.last_login_at ? <Ago iso={u.last_login_at} /> : "—"}</td>
      <td className="hidden whitespace-nowrap px-3 py-2 text-muted-foreground xl:table-cell">{fmt(u.created_at)}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          {!self && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => send(`/users/${u.id}/active`, { active: u.active ? "0" : "1" }, u.active ? `Deactivate ${u.name}? Their open sessions end now.` : undefined)}>{u.active ? "Deactivate" : "Reactivate"}</Button>}
          {u.kind !== "external" && (!microsoftOnly || u.password_login) && (resetting ? (
            <form onSubmit={(e) => { e.preventDefault(); void send(`/users/${u.id}/reset-password`, { new_password: pw }).then(() => { setPw(""); setResetting(false) }) }} className="flex items-center gap-1">
              <Input type="password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} placeholder="New password" aria-label={`New password for ${u.name}`} minLength={12} required className="h-7 w-36 text-[13px]" />
              <Button type="submit" size="sm" className="h-7" disabled={busy || pw.length < 12}>Set</Button>
              <Button type="button" size="sm" variant="ghost" className="h-7" onClick={() => setResetting(false)}>Cancel</Button>
            </form>
          ) : <Button size="sm" variant="ghost" className="h-7" onClick={() => setResetting(true)}>Reset password</Button>)}
        </div>
      </td>
    </tr>
  )
}

function AddUser({ roles, busy, send }: { roles: string[]; busy: boolean; send: (p: string, f: Record<string, string>) => Promise<void> }) {
  const [f, setF] = useState({ name: "", username: "", email: "", password: "", role: "Member" })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  function submit(e: FormEvent) {
    e.preventDefault()
    void send("/users", f).then(() => setF({ name: "", username: "", email: "", password: "", role: "Member" }))
  }
  return (
    <form onSubmit={submit} className="grid grid-cols-1 content-start gap-2 panel p-4">
      <h2 className="text-[12px] font-semibold text-nav-fg">Add a team member</h2>
      <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Full name<Input value={f.name} onChange={set("name")} required aria-label="Full name" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Username<Input value={f.username} onChange={set("username")} required aria-label="Username" autoComplete="off" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Email (for notifications)<Input type="email" value={f.email} onChange={set("email")} placeholder="name@company.com" aria-label="Email" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Temporary password<Input type="password" value={f.password} onChange={set("password")} required minLength={12} aria-label="Temporary password" autoComplete="new-password" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Role
        <select value={f.role} onChange={set("role")} aria-label="Role" className="h-8 rounded-md border border-input bg-background px-2 text-[13px]">
          {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      <Button type="submit" size="sm" className="mt-1" disabled={busy || !f.name || !f.username || f.password.length < 12}>Create user</Button>
      <p className="text-[12px] text-muted-foreground">They change the password on first sign-in. Partners and customers are invited from a project's Team panel instead.</p>
    </form>
  )
}

// Sign-up links: a link for a new colleague to request an account themselves.
// Requests land in "Waiting for approval" above; nothing is active until approved.
const field = "h-8 w-full rounded-md border border-input bg-background px-2 text-[13px]"
function SignupLinksPanel() {
  const [d, setD] = useState<SignupLinks | null>(null)
  const [f, setF] = useState({ label: "", role: "Contributor", project_id: "", project_role: "Coordinator", days: 0, max_uses: 1 })
  const [made, setMade] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => signupLinks().then(setD).catch(() => setErr("Could not load the links")), [])
  useEffect(() => { void load() }, [load])
  if (!d) return null
  async function make(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null); setCopied(false)
    try {
      const r = await createSignupLink({ label: f.label, role: f.role, project_id: f.project_id ? Number(f.project_id) : null, project_role: f.project_id ? f.project_role : null, days: f.days, max_uses: f.max_uses })
      setMade(r.link); setF({ ...f, label: "" }); await load()
    } catch (x) { setErr(x instanceof ApiError ? x.message : "That did not work") } finally { setBusy(false) }
  }
  const open = d.links.filter((l) => l.state === "open")
  return (
    <section className="panel p-4" aria-label="Sign-up links">
      <h2 data-n className="mb-1 text-[12px] font-semibold text-nav-fg">Sign-up links</h2>
      <p className="mb-3 text-[12px] text-muted-foreground">Send a new colleague a link; they fill in their details and you approve them above.</p>
      {!d.enabled && <p className="mb-3 rounded-lg bg-muted/60 p-3 text-[13px]">Sign-up links are switched off, so no link works and none can be made. Turn them on under <Link to="/settings/people" className="text-primary-text hover:underline">Settings → Sign-up &amp; activity</Link>.</p>}
      {d.enabled && <form onSubmit={make} className="grid grid-cols-1 gap-2 text-[13px]">
        <label className="grid grid-cols-1 gap-1 font-medium">For<input className={field} required maxLength={80} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="e.g. Omar, field engineer" /></label>
        <div className="grid grid-cols-2 gap-2">
          <label className="grid grid-cols-1 gap-1 font-medium">Role<select className={field} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{d.roles.map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">Valid for<select className={field} value={f.days} onChange={(e) => setF({ ...f, days: Number(e.target.value) })}><option value={0}>{d.default_days} day{d.default_days > 1 ? "s" : ""} (default)</option>{[1, 3, 7, 14, 30].filter((n) => n !== d.default_days).map((n) => <option key={n} value={n}>{n} day{n > 1 ? "s" : ""}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">Project<select className={field} value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })}><option value="">None</option>{d.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">As<select className={field} value={f.project_role} disabled={!f.project_id} onChange={(e) => setF({ ...f, project_role: e.target.value })}>{d.project_roles.map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">Uses<select className={field} value={f.max_uses} onChange={(e) => setF({ ...f, max_uses: Number(e.target.value) })}>{[1, 5, 10, 25].map((n) => <option key={n} value={n}>{n === 1 ? "One person" : `Up to ${n}`}</option>)}</select></label>
        </div>
        {err && <p className="text-bad" role="alert">{err}</p>}
        <Button type="submit" size="sm" disabled={busy || !f.label.trim()}>Create link</Button>
      </form>}
      {made && (
        <div className="mt-3 grid grid-cols-1 gap-2 rounded-lg bg-muted/60 p-3">
          <input readOnly value={made} aria-label="New sign-up link" onFocus={(e) => e.currentTarget.select()} className="h-8 rounded-md border border-input bg-background px-2 font-mono text-[12px]" />
          <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(made).then(() => setCopied(true)).catch(() => {})}>{copied ? "Copied" : "Copy the link"}</Button>
          <p className="text-[12px] text-muted-foreground">Shown once. Send it by Teams or email yourself.</p>
        </div>
      )}
      {d.links.length > 0 && (
        <ul className="mt-3 divide-y divide-border text-[13px]">
          {d.links.slice(0, 12).map((l) => (
            <li key={l.id} className="flex items-center gap-2 py-2">
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{l.label}</span>
                <span className="block truncate text-[12px] text-muted-foreground">{l.role}{l.project ? ` · ${l.project}` : ""} · {l.uses}/{l.max_uses} used · {l.state === "open" ? `until ${fmtWhen(l.expires_at)}` : l.state}</span></span>
              {l.state === "open" && <Button size="sm" variant="ghost" className="h-7 text-bad" disabled={busy} onClick={() => { if (confirm(`Revoke the link for ${l.label}?`)) void revokeSignupLink(l.id).then(load) }}>Revoke</Button>}
            </li>
          ))}
        </ul>
      )}
      {open.length === 0 && d.links.length > 0 && <p className="mt-2 text-[12px] text-muted-foreground">No open links.</p>}
      {open.length > 1 && <Button size="sm" variant="ghost" className="mt-2 h-7 text-bad" disabled={busy}
        onClick={() => { if (confirm(`Revoke all ${open.length} open links? Anyone holding one can no longer sign up with it.`)) void revokeAllSignupLinks().then(load) }}>Revoke all open links</Button>}
    </section>
  )
}
