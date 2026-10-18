import { useEffect, useState, type FormEvent } from "react"
import { PageHeader } from "@/components/PageHeader"
import { PanelTitle } from "@/components/PanelTitle"
import { toast } from "@/lib/toast"
import { field, fieldAuto, danger } from "@/lib/ui"
import { askConfirm } from "@/lib/confirm"
import { Link } from "react-router-dom"
import { UserAvatar } from "@/components/UserAvatar"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Field } from "@/components/ui/field"
import { Notice } from "@/components/Notice"
import { HandOverDialog } from "@/components/HandOverDialog"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ApiError, createSignupLink, postForm, revokeAllSignupLinks, revokeSignupLink, signupLinks, users as fetchUsers, type AdminUser, type User } from "@/lib/api"
import { cn } from "@/lib/utils"
import { fmtWhen } from "@/lib/format"
import { copyWithToast } from "@/lib/copy"
import { MIN_PASSWORD } from "@/lib/password"
import { useLoad } from "@/lib/useLoad"
import { LoadFailed } from "@/components/LoadFailed"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { filterUsers, noFilter, type UserFilter } from "@/lib/userFilter"


export default function Users({ user }: { user: User }) {
  const minPassword = user.prefs?.password_min_length ?? MIN_PASSWORD   // the admin's policy, not a number typed here (review P2-38)
  const { data, error: failed, reload: load } = useLoad("users", fetchUsers)
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState<UserFilter>(noFilter)
  useEffect(() => { document.title = "Users · Odin" }, [])

  // true when the save went through: forms clear what was typed only then
  // onError: a refusal shown by the form it came from (the dialog, Add a team
  // member) instead of in the page banner behind them (sim roles-7)
  async function send(path: string, fields: Record<string, string>, confirmText?: string, onError?: (m: string) => void): Promise<boolean> {
    if (busy) return false   // buttons stay focusable while a save runs (review P2-41), so a click lands here
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

  if (failed) return <LoadError message={failed.message} />
  if (!data) return <PageSkeleton />
  const pending = data.users.filter((u) => u.pending)
  const people = data.users.filter((u) => !u.pending)
  const shown = filterUsers(people, f)
  const flagged = people.filter((u) => u.review.length).length

  return (
    <div className="px-5 pb-6 pt-4">
      <PageHeader title="Users" lede={`${people.filter((u) => u.active).length} active · ${people.filter((u) => u.kind === "external").length} external${pending.length ? ` · ${pending.length} waiting` : ""}`}
        actions={<a href="/users/export.csv" className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>} />

      {pending.length > 0 && <Pending people={pending} roles={data.roles} busy={busy} send={send} />}

      <div className="mt-3 grid grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
        <div role="search" className="mb-3 flex flex-wrap items-center gap-2">
          <Input type="search" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Search name, username, email or role" aria-label="Search users" className="h-8 w-72 text-[13px]" />
          <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} aria-label="Filter by role" className={fieldAuto}>
            <option value="">Any role</option>
            {data.roles.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as UserFilter["status"] })} aria-label="Filter by status" className={fieldAuto}>
            <option value="all">Any status</option>
            <option value="active">Active</option>
            <option value="inactive">Deactivated</option>
          </select>
          <Button size="sm" variant={f.review ? "default" : "outline"} aria-pressed={f.review} onClick={() => setF({ ...f, review: !f.review })}>Access review{flagged ? ` (${flagged})` : ""}</Button>
        </div>
        {f.review && <p className="mb-3 max-w-prose text-[13px] text-muted-foreground">Accounts with no sign-in for {data.review_days} days, and partners or customers whose rollouts have all closed. Deactivate ends their sessions now and is audited. The window is a policy under Settings › People. Odin gives no one rights beyond their role, so there is nothing else to review.</p>}
        {/* one row per person, as a receipt: who on the left, role and state in
            the middle, one Manage button on the right; the rarely used
            controls (email, sign-in options, password, deactivate) live in
            the Manage dialog, so the list stays readable */}
        <section className="min-w-0 panel" aria-label="Team members">
          {shown.length === 0 && <p className="p-4 text-[13px] text-muted-foreground">{f.review ? "Nothing to review: every active account has signed in recently and has a rollout open." : "No one matches."}</p>}
          <ul className="divide-y divide-border">
            {/* keyed by id alone: an email change or a deactivation keeps Manage open (review P3-38) */}
            {shown.map((u) => <Row key={u.id} u={u} review={f.review} roles={data.roles} me={data.me} microsoftOnly={data.microsoft_only} minPassword={minPassword} capacityDefault={data.capacity_default}
              colleagues={people.filter((c) => c.active && c.kind === "internal" && c.id !== u.id)} busy={busy} send={send} />)}
          </ul>
        </section>
        </div>
        <div className="grid grid-cols-1 content-start gap-4">
          <AddUser roles={data.roles} minPassword={minPassword} busy={busy} send={send} />
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
  const [declining, setDeclining] = useState<AdminUser | null>(null)
  return (
    <section className="mt-3 rounded-lg bg-warn-soft/60 p-4" aria-label="Waiting for approval">
      <PanelTitle n={false} className="mb-2" hint="asked to use Odin, not yet allowed in">Waiting for approval</PanelTitle>
      <ul className="grid grid-cols-1 gap-2">
        {people.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="min-w-0 flex-1"><span className="font-medium">{u.name}</span> <span className="text-muted-foreground">{u.email && u.email.toLowerCase() === u.username.toLowerCase() ? u.email : `${u.username} · ${u.email}`} · asked {fmtWhen(u.created_at, true)}
              {u.signup_label ? ` · via sign-up link "${u.signup_label}"` : u.microsoft ? " · via Microsoft sign-in" : ""}{u.signup_project ? ` · joins ${u.signup_project} as ${u.signup_project_role}` : ""}
              </span></span>
            <select value={role[u.id] ?? (u.signup_label ? u.role : "Viewer")} onChange={(e) => setRole({ ...role, [u.id]: e.target.value })} aria-label={`Role for ${u.name}`} className={fieldAuto}>
              {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <Button size="sm" className="h-7" disabled={busy} onClick={() => send(`/users/${u.id}/approve`, { role: role[u.id] ?? (u.signup_label ? u.role : "Viewer") })}>Approve</Button>
            <Button size="sm" variant="ghost" className="h-7" disabled={busy} onClick={() => setDeclining(u)}>Decline</Button>
          </li>
        ))}
      </ul>
      {declining && <DeclineDialog u={declining} busy={busy} send={send} onClose={() => setDeclining(null)} />}
    </section>
  )
}

// The reason is optional, one line, kept on the account and in the audit log; Odin does not email the person.
export function DeclineDialog({ u, busy, send, onClose }: { u: AdminUser; busy: boolean; send: (p: string, f: Record<string, string>) => Promise<boolean>; onClose: () => void }) {
  const [reason, setReason] = useState("")
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (await send(`/users/${u.id}/decline`, { reason: reason.trim() })) onClose()
  }
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid grid-cols-1 gap-4">
          <DialogHeader>
            <DialogTitle>Decline {u.name}?</DialogTitle>
            <DialogDescription>They stay unable to sign in, and Odin does not tell them. Your reason is kept on the account and in the audit log.</DialogDescription>
          </DialogHeader>
          <Field label="Reason (optional)" hint={`${reason.length} of 300`}>
            <Input value={reason} onChange={(e) => setReason(e.target.value.replace(/[\r\n]+/g, " "))} maxLength={300} placeholder="e.g. not on the rollout team" className="h-8 text-[13px]" />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="destructive" loading={busy}>Decline</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// How this person gets in. When Microsoft sign-in is required, a password is
// the exception an admin keeps for emergencies; otherwise everyone has one.
function signInText(u: AdminUser, microsoftOnly: boolean) {
  if (u.kind === "external") return "Email link"
  const ways = microsoftOnly ? ["Microsoft", u.password_login && "password kept"] : [u.microsoft && "Microsoft", "Password"]
  return [...ways, u.two_step && "two-step"].filter(Boolean).join(" · ")
}

function Row({ u, review, roles, me, microsoftOnly, minPassword, capacityDefault, colleagues, busy, send }: { u: AdminUser; review: boolean; roles: string[]; me: number; microsoftOnly: boolean; minPassword: number; capacityDefault: number; colleagues: AdminUser[]; busy: boolean; send: (p: string, f: Record<string, string>, c?: string) => Promise<boolean> }) {
  const [open, setOpen] = useState(false)
  const [handing, setHanding] = useState(false)
  const self = u.id === me
  const holds = u.holds.tasks + u.holds.rollouts + u.holds.raid
  // the review's one click: the same route as Manage, and staff who hold work get the hand-over first
  const deactivate = () => { if (holds > 0 && u.kind === "internal") setHanding(true); else void send(`/users/${u.id}/active`, { active: "0" }, `Deactivate ${u.name}? Their open sessions end now.`) }
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
          {!u.active && u.declined_reason && <p className="truncate text-[12px] text-muted-foreground" title={u.declined_reason}>Declined: {u.declined_reason}</p>}
        </div>
      </div>
      <div className="flex gap-2 md:order-last md:justify-self-end">
        {review && u.active && !self && <Button size="sm" variant="destructive" disabled={busy} onClick={deactivate} aria-label={`Deactivate ${u.name}`}>Deactivate</Button>}
        <Button size="sm" variant="outline" onClick={() => setOpen(true)} aria-label={`Manage ${u.name}`}>Manage</Button>
      </div>
      <div className="col-span-2 flex items-center gap-4 md:contents">
        <div className="w-32 shrink-0 md:w-auto">
          {/* External is a kind of account, not a role to hand out: an invited
              partner stays External (plain text), staff never become it */}
          {u.kind === "external" ? <span className="text-muted-foreground">External</span> : (
            <select value={u.role} disabled={self} aria-disabled={busy || undefined} onChange={async (e) => { const to = e.target.value; if (await askConfirm(`Make ${u.name} ${to === "Admin" ? "an Admin" : `a ${to}`}? It applies at their next click.`, "Change role")) void send(`/users/${u.id}/role`, { role: to }) }} aria-label={`Role for ${u.name}`} className={cn(fieldAuto, "w-full")}>
              {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          )}
        </div>
        <div className="min-w-0 text-[12px] text-muted-foreground">
          <p className="truncate">{u.active ? signInText(u, microsoftOnly) : <span className="font-medium text-foreground">Deactivated</span>}</p>
          <p>{u.last_login_at ? <>Signed in <Ago iso={u.last_login_at} /></> : "Never signed in"}</p>
          {review && u.review.map((r) => <p key={r} className="font-medium text-warn">{r}</p>)}
        </div>
      </div>
      <Manage u={u} self={self} microsoftOnly={microsoftOnly} minPassword={minPassword} capacityDefault={capacityDefault} colleagues={colleagues} busy={busy} send={send} open={open} onClose={() => setOpen(false)} />
      {handing && <HandOverDialog u={u} colleagues={colleagues} busy={busy} send={send} onClose={() => setHanding(false)} />}
    </li>
  )
}

// Everything about one account that is changed rarely: one dialog, sections
// separated by hairlines; destructive actions last.
function Manage({ u, self, microsoftOnly, minPassword, capacityDefault, colleagues, busy, send, open, onClose }: { u: AdminUser; self: boolean; microsoftOnly: boolean; minPassword: number; capacityDefault: number; colleagues: AdminUser[]; busy: boolean; send: (p: string, f: Record<string, string>, c?: string, onError?: (m: string) => void) => Promise<boolean>; open: boolean; onClose: () => void }) {
  const [email, setEmail] = useState(u.email ?? "")
  const [pw, setPw] = useState("")
  const [problem, setProblem] = useState<string | null>(null)
  const [hours, setHours] = useState(u.capacity_hours == null ? "" : String(u.capacity_hours))
  const [handing, setHanding] = useState(false)
  const holds = u.holds.tasks + u.holds.rollouts + u.holds.raid
  const act = (path: string, fields: Record<string, string>, confirmText?: string) => { setProblem(null); return send(path, fields, confirmText, setProblem) }
  const canReset = u.kind !== "external" && (!microsoftOnly || u.password_login)
  const section = "grid grid-cols-1 gap-2 border-t border-border pt-4"
  return (
    <>
    {/* the hand-over replaces Manage while it is open (no dialog on a dialog); Cancel returns to it with what was typed */}
    <Dialog open={open && !handing} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{u.name}</DialogTitle>
          <DialogDescription>{u.kind === "external" ? "Partner or customer account" : `${u.username} · ${u.role}`} · added {fmtWhen(u.created_at)}</DialogDescription>
        </DialogHeader>
        {problem && <Notice bad>{problem}</Notice>}
        <form onSubmit={(e) => { e.preventDefault(); if (email !== (u.email ?? "")) void act(`/users/${u.id}/email`, { email }) }} className="grid grid-cols-1 gap-2">
          <Field label="Email">
            <span className="flex gap-2">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" maxLength={254} aria-label={`Email for ${u.name}`} className="h-8 flex-1 text-[13px]" />
              <Button type="submit" size="sm" loading={busy} disabled={email === (u.email ?? "")}>Save</Button>
            </span>
          </Field>
        </form>
        {u.kind !== "external" && (
          <form className={section} onSubmit={(e) => { e.preventDefault(); void act(`/users/${u.id}/capacity`, { capacity_hours: hours.trim() }) }}>
            <Field label="Capacity (hours a week)" hint={`Blank takes the workspace default, ${capacityDefault} h. For part-timers; People › Workload counts against it.`}>
              <span className="flex gap-2">
                <Input type="number" min={1} max={80} step={0.5} value={hours} onChange={(e) => setHours(e.target.value)} placeholder={`${capacityDefault} (default)`} aria-label={`Capacity for ${u.name}`} className="h-8 flex-1 text-[13px]" />
                <Button type="submit" size="sm" loading={busy} disabled={hours.trim() === (u.capacity_hours == null ? "" : String(u.capacity_hours))}>Save</Button>
              </span>
            </Field>
          </form>
        )}
        {u.kind !== "external" && (
          <div className={section}>
            <p className="text-[12px] font-medium text-nav-fg">Sign-in</p>
            <p className="max-w-prose text-[13px] text-muted-foreground">{signInText(u, microsoftOnly).replace(/^./, (c) => c.toUpperCase())}.</p>
            {microsoftOnly && (
              <label className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" checked={u.password_login} aria-disabled={busy || undefined} onChange={(e) => act(`/users/${u.id}/password-login`, e.target.checked ? { allowed: "on" } : {})} className="h-4 w-4 accent-primary" />
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
            <Field label="Set a new password" hint="They must change it at their next sign-in; their sessions end.">
              <span className="flex gap-2">
                <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder={`At least ${minPassword} characters`} aria-label={`New password for ${u.name}`} minLength={minPassword} required autoComplete="new-password" className="h-8 flex-1 text-[13px]" />
                <Button type="submit" size="sm" loading={busy}>Set</Button>
              </span>
            </Field>
          </form>
        )}
        {!self && (
          <div className={cn(section, "flex flex-wrap items-center justify-between gap-2")}>
            <span className="text-[13px] text-muted-foreground">{u.active ? "Deactivating ends their sessions now." : "This account can't sign in."}</span>
            <Button size="sm" variant={u.active ? "destructive" : "outline"} disabled={busy}
              onClick={() => { if (u.active && holds > 0 && u.kind === "internal") setHanding(true); else void act(`/users/${u.id}/active`, { active: u.active ? "0" : "1" }, u.active ? `Deactivate ${u.name}? Their open sessions end now.` : undefined).then((ok) => { if (ok) onClose() }) }}>{u.active ? "Deactivate" : "Reactivate"}</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
    {open && handing && <HandOverDialog u={u} colleagues={colleagues} busy={busy} send={send} onClose={(done) => { setHanding(false); if (done) onClose() }} />}
    </>
  )
}

function AddUser({ roles, minPassword, busy, send }: { roles: string[]; minPassword: number; busy: boolean; send: (p: string, f: Record<string, string>, c?: string, onError?: (m: string) => void) => Promise<boolean> }) {
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
      <PanelTitle n={false} className="mb-0">Add a team member</PanelTitle>
      <Field label="Full name"><Input value={f.name} onChange={set("name")} required maxLength={120} className="h-8 text-[13px]" /></Field>
      <Field label="Username"><Input value={f.username} onChange={set("username")} required maxLength={80} autoComplete="off" className="h-8 text-[13px]" /></Field>
      <Field label="Email (for notifications)"><Input type="email" value={f.email} onChange={set("email")} placeholder="name@company.com" maxLength={254} className="h-8 text-[13px]" /></Field>
      <Field label="Temporary password"><Input type="password" value={f.password} onChange={set("password")} required minLength={minPassword} placeholder={`At least ${minPassword} characters`} autoComplete="new-password" className="h-8 text-[13px]" /></Field>
      <Field label="Role">
        <select value={f.role} onChange={set("role")} className={fieldAuto}>
          {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </Field>
      {problem && <Notice bad>{problem}</Notice>}
      <Button type="submit" size="sm" className="mt-1" loading={busy} disabled={!f.name.trim() || !f.username.trim() || f.password.length < minPassword}>Create user</Button>
      <p className="max-w-prose text-[12px] text-muted-foreground">They change the password on first sign-in. Partners and customers are invited from a rollout's Team panel instead.</p>
    </form>
  )
}

// Sign-up links: a link for a new colleague to request an account themselves.
// Requests land in "Waiting for approval" above; nothing is active until approved.
function SignupLinksPanel() {
  const { data: d, error: failed, reload: load } = useLoad("signup-links", signupLinks)
  const [f, setF] = useState({ label: "", role: "Contributor", project_id: "", project_role: "Coordinator", days: 0, max_uses: 1 })
  const [made, setMade] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!d) return failed ? <LoadFailed what="the sign-up links" onRetry={() => void load()} /> : null
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
      <PanelTitle n={false} className="mb-1">Sign-up links</PanelTitle>
      <p className="max-w-prose mb-3 text-[12px] text-muted-foreground">Send a new colleague a link; they fill in their details and you approve them above.</p>
      {!d.enabled && <p className="mb-3 rounded-lg bg-muted/60 p-3 text-[13px]">Sign-up links are switched off, so no link works and none can be made. Turn them on under <Link to="/settings/people" className="text-primary-text hover:underline">Settings › Sign-up &amp; activity</Link>.</p>}
      {d.enabled && <form onSubmit={make} className="grid grid-cols-1 gap-2 text-[13px]">
        <Field label="For"><input className={field} required maxLength={80} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder="e.g. Omar, field engineer" /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Role"><select className={field} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{d.roles.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <Field label="Valid for"><select className={field} value={f.days} onChange={(e) => setF({ ...f, days: Number(e.target.value) })}><option value={0}>{d.default_days} day{d.default_days > 1 ? "s" : ""} (default)</option>{[1, 3, 7, 14, 30].filter((n) => n !== d.default_days).map((n) => <option key={n} value={n}>{n} day{n > 1 ? "s" : ""}</option>)}</select></Field>
          <Field label="Rollout"><select className={field} value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })}><option value="">None</option>{d.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="As"><select className={field} value={f.project_role} disabled={!f.project_id} onChange={(e) => setF({ ...f, project_role: e.target.value })}>{d.project_roles.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <Field label="Uses"><select className={field} value={f.max_uses} onChange={(e) => setF({ ...f, max_uses: Number(e.target.value) })}>{[1, 5, 10, 25].map((n) => <option key={n} value={n}>{n === 1 ? "One person" : `Up to ${n}`}</option>)}</select></Field>
        </div>
        {err && <Notice bad>{err}</Notice>}
        <Button type="submit" size="sm" loading={busy} disabled={!f.label.trim()}>Create link</Button>
      </form>}
      {made && (
        <div className="mt-3 grid grid-cols-1 gap-2 rounded-lg bg-muted/60 p-3">
          <input readOnly value={made} aria-label="New sign-up link" onFocus={(e) => e.currentTarget.select()} className={cn(fieldAuto, "font-mono text-[12px]")} />
          <Button size="sm" variant="outline" onClick={() => void copyWithToast(made, "link").then(setCopied)}>{copied ? "Copied" : "Copy the link"}</Button>
          <p className="max-w-prose text-[12px] text-muted-foreground">Shown once. Send it by Teams or email yourself.</p>
        </div>
      )}
      {d.links.length > 0 && (
        <ul className="mt-3 divide-y divide-border text-[13px]">
          {d.links.slice(0, 12).map((l) => (
            <li key={l.id} className="flex items-center gap-2 py-2">
              <span className="min-w-0 flex-1"><span className="block truncate font-medium" title={l.label}>{l.label}</span>
                <span className="block truncate text-[12px] text-muted-foreground">{l.role}{l.project ? ` · ${l.project}` : ""} · {l.uses}/{l.max_uses} used · {l.state === "open" ? `until ${fmtWhen(l.expires_at)}` : l.state}</span></span>
              {l.state === "open" && <Button size="sm" variant="ghost" className={danger} disabled={busy} onClick={async () => { if (await askConfirm(`Revoke the link for ${l.label}?`)) void revokeSignupLink(l.id).then(load).catch((x) => setErr(x instanceof ApiError ? x.message : "Could not revoke the link")) }}>Revoke</Button>}
            </li>
          ))}
        </ul>
      )}
      {err && !d.enabled && <Notice bad className="mt-2">{err}</Notice>}
      {open.length === 0 && d.links.length > 0 && <p className="max-w-prose mt-2 text-[12px] text-muted-foreground">No open links.</p>}
      {open.length > 1 && <Button size="sm" variant="ghost" className={cn("mt-2", danger)} disabled={busy}
        onClick={async () => { if (await askConfirm(`Revoke all ${open.length} open links? Anyone holding one can no longer sign up with it.`)) void revokeAllSignupLinks().then(load).catch((x) => setErr(x instanceof ApiError ? x.message : "Could not revoke the links")) }}>Revoke all open links</Button>}
    </section>
  )
}
