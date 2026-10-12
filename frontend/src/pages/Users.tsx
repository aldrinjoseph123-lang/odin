import { useCallback, useEffect, useState, type FormEvent } from "react"
import { toast } from "@/lib/toast"
import { field, fieldAuto } from "@/lib/ui"
import { askConfirm } from "@/lib/confirm"
import { Link } from "react-router-dom"
import { UserAvatar } from "@/components/UserAvatar"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, createSignupLink, postForm, revokeAllSignupLinks, revokeSignupLink, signupLinks, users as fetchUsers, type AdminUser, type SignupLinks, type User, type UsersData } from "@/lib/api"
import { cn } from "@/lib/utils"
import { fmtWhen } from "@/lib/format"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"


export default function Users(_props: { user: User }) {
  const [data, setData] = useState<UsersData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setData(await fetchUsers()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load users") }
  }, [])
  useEffect(() => { void load(); document.title = "Users · Odin" }, [load])

  // true when the save went through: forms clear what was typed only then
  // onError: a refusal shown by the form it came from (the dialog, Add a team
  // member) instead of in the page banner behind them (sim roles-7)
  async function send(path: string, fields: Record<string, string>, confirmText?: string, onError?: (m: string) => void): Promise<boolean> {
    if (confirmText && !(await askConfirm(confirmText))) return false
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      { const said = r.messages.join(" "); if (said) toast(said) }
      await load()
      return true
    } catch (e) {
      const m = e instanceof ApiError ? e.message : "That did not save"
      if (onError) onError(m); else toast(m, { tone: "bad" })
      return false
    } finally { setBusy(false) }
  }

  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />
  const pending = data.users.filter((u) => u.pending)
  const people = data.users.filter((u) => !u.pending)

  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Users</h1>
        <p className="max-w-prose text-[13px] text-muted-foreground">{people.filter((u) => u.active).length} active · {people.filter((u) => u.kind === "external").length} external{pending.length ? ` · ${pending.length} waiting` : ""}</p>
        <div className="ml-auto flex items-center gap-2">
          <a href="/users/export.csv" className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>
        </div>
      </div>

      {pending.length > 0 && <Pending people={pending} roles={data.roles} busy={busy} send={send} />}

      <div className="mt-3 grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1fr)_320px]">
        {/* one row per person, as a receipt: who on the left, role and state in
            the middle, one Manage button on the right; the rarely used
            controls (email, sign-in options, password, deactivate) live in
            the Manage dialog, so the list stays readable */}
        <section className="min-w-0 panel" aria-label="Team members">
          <ul className="divide-y divide-border">
            {people.map((u) => <Row key={`${u.id}:${u.email ?? ""}:${u.active}`} u={u} roles={data.roles} me={data.me} microsoftOnly={data.microsoft_only} busy={busy} send={send} />)}
          </ul>
        </section>
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
function Pending({ people, roles, busy, send }: { people: AdminUser[]; roles: string[]; busy: boolean; send: (p: string, f: Record<string, string>, c?: string) => Promise<boolean> }) {
  const [role, setRole] = useState<Record<number, string>>({})
  return (
    <section className="mt-3 rounded-lg bg-warn-soft/60 p-4" aria-label="Waiting for approval">
      <h2 className="mb-2 text-[12px] font-semibold text-nav-fg">Waiting for approval <span className="font-normal text-muted-foreground">asked to use Odin, not yet allowed in</span></h2>
      <ul className="grid grid-cols-1 gap-2">
        {people.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="min-w-0 flex-1"><span className="font-medium">{u.name}</span> <span className="text-muted-foreground">{u.username} · {u.email} · asked {fmtWhen(u.created_at, true)}
              {u.signup_label ? ` · via sign-up link "${u.signup_label}"` : u.microsoft ? " · via Microsoft sign-in" : ""}{u.signup_project ? ` · joins ${u.signup_project} as ${u.signup_project_role}` : ""}
              {u.notify_via === "teams" ? " · prefers Teams" : ""}</span></span>
            <select value={role[u.id] ?? (u.signup_label ? u.role : "Viewer")} onChange={(e) => setRole({ ...role, [u.id]: e.target.value })} aria-label={`Role for ${u.name}`} className={fieldAuto}>
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

// How this person gets in. When Microsoft sign-in is required, a password is
// the exception an admin keeps for emergencies; otherwise everyone has one.
function signInText(u: AdminUser, microsoftOnly: boolean) {
  if (u.kind === "external") return "Email link"
  const ways = microsoftOnly ? ["Microsoft", u.password_login && "password kept"] : [u.microsoft && "Microsoft", "Password"]
  return [...ways, u.two_step && "two-step"].filter(Boolean).join(" · ")
}

function Row({ u, roles, me, microsoftOnly, busy, send }: { u: AdminUser; roles: string[]; me: number; microsoftOnly: boolean; busy: boolean; send: (p: string, f: Record<string, string>, c?: string) => Promise<boolean> }) {
  const [open, setOpen] = useState(false)
  const self = u.id === me
  return (
    // phones: who + Manage on top, role and state on one line under it;
    // md and up: one line, the role/state pair dissolving into grid cells
    <li className={cn("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-2 px-4 py-3 text-[13px] md:grid-cols-[minmax(0,1fr)_128px_190px_auto]", !u.active && "text-muted-foreground")}>
      <div className="flex min-w-0 items-center gap-3">
        <UserAvatar name={u.name} url={u.avatar_url} className="h-8 w-8" />
        <div className="min-w-0">
          <p className="flex min-w-0 items-center gap-2 font-medium">
            <span className="truncate" title={u.name}>{u.name || "(no name)"}</span>
            {self && <span className="shrink-0 text-[12px] font-normal text-muted-foreground">you</span>}
          </p>
          {/* a partner's username is their email: say it once */}
          <p className="truncate text-[12px] text-muted-foreground" title={[u.username, u.email].filter(Boolean).join(" · ")}>
            {u.email && u.email.toLowerCase() === u.username.toLowerCase() ? u.email : `${u.username} · ${u.email || "no email"}`}
          </p>
        </div>
      </div>
      <div className="md:order-last md:justify-self-end">
        <Button size="sm" variant="outline" onClick={() => setOpen(true)} aria-label={`Manage ${u.name}`}>Manage</Button>
      </div>
      <div className="col-span-2 flex items-center gap-4 md:contents">
        <div className="w-32 shrink-0 md:w-auto">
          {/* External is a kind of account, not a role to hand out: an invited
              partner stays External (plain text), staff never become it */}
          {u.kind === "external" ? <span className="text-muted-foreground">External</span> : (
            <select value={u.role} disabled={self || busy} onChange={(e) => send(`/users/${u.id}/role`, { role: e.target.value }, `Make ${u.name} ${e.target.value === "Admin" ? "an Admin" : `a ${e.target.value}`}? It applies at their next click.`)} aria-label={`Role for ${u.name}`} className={cn(fieldAuto, "w-full")}>
              {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          )}
        </div>
        <div className="min-w-0 text-[12px] text-muted-foreground">
          <p className="truncate">{u.active ? signInText(u, microsoftOnly) : <span className="font-medium text-foreground">Deactivated</span>}</p>
          <p>{u.last_login_at ? <>Signed in <Ago iso={u.last_login_at} /></> : "Never signed in"}</p>
        </div>
      </div>
      <Manage u={u} self={self} microsoftOnly={microsoftOnly} busy={busy} send={send} open={open} onClose={() => setOpen(false)} />
    </li>
  )
}

// Everything about one account that is changed rarely: one dialog, sections
// separated by hairlines; destructive actions last.
function Manage({ u, self, microsoftOnly, busy, send, open, onClose }: { u: AdminUser; self: boolean; microsoftOnly: boolean; busy: boolean; send: (p: string, f: Record<string, string>, c?: string, onError?: (m: string) => void) => Promise<boolean>; open: boolean; onClose: () => void }) {
  const [email, setEmail] = useState(u.email ?? "")
  const [pw, setPw] = useState("")
  const [problem, setProblem] = useState<string | null>(null)
  const act = (path: string, fields: Record<string, string>, confirmText?: string) => { setProblem(null); return send(path, fields, confirmText, setProblem) }
  const canReset = u.kind !== "external" && (!microsoftOnly || u.password_login)
  const section = "grid grid-cols-1 gap-2 border-t border-border pt-4"
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{u.name}</DialogTitle>
          <DialogDescription>{u.kind === "external" ? "Partner or customer account" : `${u.username} · ${u.role}`} · added {fmtWhen(u.created_at)}</DialogDescription>
        </DialogHeader>
        {problem && <p className="field-error" role="alert">{problem}</p>}
        <form onSubmit={(e) => { e.preventDefault(); if (email !== (u.email ?? "")) void act(`/users/${u.id}/email`, { email }) }} className="grid grid-cols-1 gap-2">
          <label className="grid grid-cols-1 gap-1 text-[12px] font-medium">Email
            <span className="flex gap-2">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" maxLength={254} aria-label={`Email for ${u.name}`} className="h-8 flex-1 text-[13px]" />
              <Button type="submit" size="sm" loading={busy} disabled={email === (u.email ?? "")}>Save</Button>
            </span>
          </label>
        </form>
        {u.kind !== "external" && (
          <div className={section}>
            <p className="text-[12px] font-medium">Sign-in</p>
            <p className="max-w-prose text-[13px] text-muted-foreground">{signInText(u, microsoftOnly).replace(/^./, (c) => c.toUpperCase())}.</p>
            {microsoftOnly && (
              <label className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" checked={u.password_login} disabled={busy} onChange={(e) => act(`/users/${u.id}/password-login`, e.target.checked ? { allowed: "on" } : {})} className="h-4 w-4 accent-primary" />
                Keep a password too (the emergency way in while Microsoft is required)
              </label>
            )}
            {u.two_step && (
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-muted-foreground">Two-step sign-in is on.</span>
                <Button size="sm" variant="ghost" disabled={busy} aria-label={`Reset two-step sign-in for ${u.name}`}
                  onClick={() => act(`/users/${u.id}/two-step-reset`, {}, `Reset two-step sign-in for ${u.name}? Use this when they lost their phone and recovery codes. Their sessions end.`)}>Reset two-step</Button>
              </div>
            )}
          </div>
        )}
        {canReset && (
          <form className={section} onSubmit={(e) => { e.preventDefault(); void act(`/users/${u.id}/reset-password`, { new_password: pw }).then((ok) => { if (ok) setPw("") }) }}>
            <label className="grid grid-cols-1 gap-1 text-[12px] font-medium">Set a new password
              <span className="flex gap-2">
                <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="At least 12 characters" aria-label={`New password for ${u.name}`} minLength={12} required autoComplete="new-password" className="h-8 flex-1 text-[13px]" />
                <Button type="submit" size="sm" loading={busy}>Set</Button>
              </span>
            </label>
            <p className="max-w-prose text-[12px] text-muted-foreground">They must change it at their next sign-in; their sessions end.</p>
          </form>
        )}
        {!self && (
          <div className={cn(section, "flex flex-wrap items-center justify-between gap-2")}>
            <span className="text-[13px] text-muted-foreground">{u.active ? "Deactivating ends their sessions now." : "This account can't sign in."}</span>
            <Button size="sm" variant={u.active ? "destructive" : "outline"} disabled={busy}
              onClick={() => void act(`/users/${u.id}/active`, { active: u.active ? "0" : "1" }, u.active ? `Deactivate ${u.name}? Their open sessions end now.` : undefined).then((ok) => { if (ok) onClose() })}>{u.active ? "Deactivate" : "Reactivate"}</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function AddUser({ roles, busy, send }: { roles: string[]; busy: boolean; send: (p: string, f: Record<string, string>, c?: string, onError?: (m: string) => void) => Promise<boolean> }) {
  const [f, setF] = useState({ name: "", username: "", email: "", password: "", role: "Member" })
  const [problem, setProblem] = useState<string | null>(null)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  function submit(e: FormEvent) {
    e.preventDefault()
    setProblem(null)
    void send("/users", f, undefined, setProblem).then((ok) => { if (ok) setF({ name: "", username: "", email: "", password: "", role: "Member" }) })
  }
  return (
    <form onSubmit={submit} className="grid grid-cols-1 content-start gap-2 panel p-4">
      <h2 className="text-[12px] font-semibold text-nav-fg">Add a team member</h2>
      <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Full name<Input value={f.name} onChange={set("name")} required maxLength={120} aria-label="Full name" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Username<Input value={f.username} onChange={set("username")} required maxLength={80} aria-label="Username" autoComplete="off" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Email (for notifications)<Input type="email" value={f.email} onChange={set("email")} placeholder="name@company.com" maxLength={254} aria-label="Email" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Temporary password<Input type="password" value={f.password} onChange={set("password")} required minLength={12} aria-label="Temporary password" autoComplete="new-password" className="h-8 text-[13px]" /></label>
      <label className="grid grid-cols-1 gap-1 text-[13px] font-medium">Role
        <select value={f.role} onChange={set("role")} aria-label="Role" className="h-8 rounded-md border border-input bg-background px-2 text-[13px]">
          {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      {problem && <p className="field-error" role="alert">{problem}</p>}
      <Button type="submit" size="sm" className="mt-1" loading={busy}>Create user</Button>
      <p className="max-w-prose text-[12px] text-muted-foreground">They change the password on first sign-in. Partners and customers are invited from a project's Team panel instead.</p>
    </form>
  )
}

// Sign-up links: a link for a new colleague to request an account themselves.
// Requests land in "Waiting for approval" above; nothing is active until approved.
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
      <h2 className="mb-1 text-[12px] font-semibold text-nav-fg">Sign-up links</h2>
      <p className="max-w-prose mb-3 text-[12px] text-muted-foreground">Send a new colleague a link; they fill in their details and you approve them above.</p>
      {!d.enabled && <p className="mb-3 rounded-lg bg-muted/60 p-3 text-[13px]">Sign-up links are switched off, so no link works and none can be made. Turn them on under <Link to="/settings/people" className="text-primary-text hover:underline">Settings › Sign-up &amp; activity</Link>.</p>}
      {d.enabled && <form onSubmit={make} className="grid grid-cols-1 gap-2 text-[13px]">
        <label className="grid grid-cols-1 gap-1 font-medium">For<input className={field} required maxLength={80} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="e.g. Omar, field engineer" /></label>
        <div className="grid grid-cols-2 gap-2">
          <label className="grid grid-cols-1 gap-1 font-medium">Role<select className={field} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{d.roles.map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">Valid for<select className={field} value={f.days} onChange={(e) => setF({ ...f, days: Number(e.target.value) })}><option value={0}>{d.default_days} day{d.default_days > 1 ? "s" : ""} (default)</option>{[1, 3, 7, 14, 30].filter((n) => n !== d.default_days).map((n) => <option key={n} value={n}>{n} day{n > 1 ? "s" : ""}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">Project<select className={field} value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })}><option value="">None</option>{d.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">As<select className={field} value={f.project_role} disabled={!f.project_id} onChange={(e) => setF({ ...f, project_role: e.target.value })}>{d.project_roles.map((r) => <option key={r}>{r}</option>)}</select></label>
          <label className="grid grid-cols-1 gap-1 font-medium">Uses<select className={field} value={f.max_uses} onChange={(e) => setF({ ...f, max_uses: Number(e.target.value) })}>{[1, 5, 10, 25].map((n) => <option key={n} value={n}>{n === 1 ? "One person" : `Up to ${n}`}</option>)}</select></label>
        </div>
        {err && <p className="text-destructive" role="alert">{err}</p>}
        <Button type="submit" size="sm" loading={busy} disabled={!f.label.trim()}>Create link</Button>
      </form>}
      {made && (
        <div className="mt-3 grid grid-cols-1 gap-2 rounded-lg bg-muted/60 p-3">
          <input readOnly value={made} aria-label="New sign-up link" onFocus={(e) => e.currentTarget.select()} className="h-8 rounded-md border border-input bg-background px-2 font-mono text-[12px]" />
          <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(made).then(() => setCopied(true)).catch(() => {})}>{copied ? "Copied" : "Copy the link"}</Button>
          <p className="max-w-prose text-[12px] text-muted-foreground">Shown once. Send it by Teams or email yourself.</p>
        </div>
      )}
      {d.links.length > 0 && (
        <ul className="mt-3 divide-y divide-border text-[13px]">
          {d.links.slice(0, 12).map((l) => (
            <li key={l.id} className="flex items-center gap-2 py-2">
              <span className="min-w-0 flex-1"><span className="block truncate font-medium" title={l.label}>{l.label}</span>
                <span className="block truncate text-[12px] text-muted-foreground">{l.role}{l.project ? ` · ${l.project}` : ""} · {l.uses}/{l.max_uses} used · {l.state === "open" ? `until ${fmtWhen(l.expires_at)}` : l.state}</span></span>
              {l.state === "open" && <Button size="sm" variant="ghost" className="h-7 text-destructive" disabled={busy} onClick={async () => { if (await askConfirm(`Revoke the link for ${l.label}?`)) void revokeSignupLink(l.id).then(load).catch((x) => setErr(x instanceof ApiError ? x.message : "Could not revoke the link")) }}>Revoke</Button>}
            </li>
          ))}
        </ul>
      )}
      {err && !d.enabled && <p className="mt-2 text-[13px] text-destructive" role="alert">{err}</p>}
      {open.length === 0 && d.links.length > 0 && <p className="max-w-prose mt-2 text-[12px] text-muted-foreground">No open links.</p>}
      {open.length > 1 && <Button size="sm" variant="ghost" className="mt-2 h-7 text-bad" disabled={busy}
        onClick={async () => { if (await askConfirm(`Revoke all ${open.length} open links? Anyone holding one can no longer sign up with it.`)) void revokeAllSignupLinks().then(load).catch((x) => setErr(x instanceof ApiError ? x.message : "Could not revoke the links")) }}>Revoke all open links</Button>}
    </section>
  )
}
