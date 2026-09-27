import { useCallback, useEffect, useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { UserAvatar } from "@/components/UserAvatar"
import { Ago } from "@/components/Ago"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, postForm, users as fetchUsers, type AdminUser, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

const fmt = (iso: string | null, withTime = false) => (iso ? new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString([], withTime ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric" }) : "—")
const selectClass = "h-7 rounded-md border border-input bg-background px-2 text-[12.5px] disabled:opacity-60"

export default function Users(_props: { user: User }) {
  const [data, setData] = useState<{ users: AdminUser[]; roles: string[]; me: number } | null>(null)
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

  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!data) return <div className="p-5 text-[13px] text-muted-foreground">Loading users…</div>

  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Users</h1>
        <p className="text-[13px] text-muted-foreground">{data.users.filter((u) => u.active).length} active · {data.users.filter((u) => u.kind === "external").length} external</p>
        <div className="ml-auto flex items-center gap-2">
          <a href="/settings" className={buttonVariants({ variant: "ghost", size: "sm" })}>Settings</a>
          <a href="/users/export.csv" className={buttonVariants({ variant: "outline", size: "sm" })}>Export CSV</a>
        </div>
      </div>
      {notice && (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status">
          <span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 overflow-auto rounded-lg border border-border">
          <table className="w-full border-collapse text-[13px]">
            <thead className="bg-background">
              <tr className="border-b border-border text-left text-[11.5px] font-normal text-muted-foreground">
                {["Name", "Username", "Email", "Role", "Status", "Last sign-in", "Created", ""].map((h, i) => <th key={i} className={cn("px-3 py-2 font-normal", (i === 1 || i >= 5) && i !== 7 && "hidden xl:table-cell")}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => <Row key={`${u.id}:${u.email ?? ""}`} u={u} roles={data.roles} me={data.me} busy={busy} send={send} />)}
            </tbody>
          </table>
        </div>
        <AddUser roles={data.roles} busy={busy} send={send} />
      </div>
    </div>
  )
}

function Row({ u, roles, me, busy, send }: { u: AdminUser; roles: string[]; me: number; busy: boolean; send: (p: string, f: Record<string, string>, c?: string) => Promise<void> }) {
  const [email, setEmail] = useState(u.email ?? "")   // the row remounts (key) when the saved email changes
  const [pw, setPw] = useState("")
  const [resetting, setResetting] = useState(false)
  const self = u.id === me
  return (
    <tr className={cn("border-b border-border last:border-0", !u.active && "text-muted-foreground")}>
      <td className="px-3 py-2 font-medium"><span className="inline-flex items-center gap-2"><UserAvatar name={u.name} url={u.avatar_url} className="h-6 w-6" /><span title={u.username}>{u.name}</span></span>{u.kind === "external" && <Badge variant="secondary" className="ml-1.5">External</Badge>}{self && <span className="ml-1.5 text-[11.5px] font-normal text-muted-foreground">you</span>}</td>
      <td className="hidden px-3 py-2 text-muted-foreground xl:table-cell">{u.username}</td>
      <td className="px-3 py-2">
        <form onSubmit={(e) => { e.preventDefault(); if (email !== (u.email ?? "")) void send(`/users/${u.id}/email`, { email }) }} className="flex items-center gap-1">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" aria-label={`Email for ${u.name}`} className="h-7 w-40 text-[12.5px]" />
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
      <td className="px-3 py-2">{u.active ? "Active" : <span className="text-bad">Deactivated</span>}</td>
      <td className="hidden whitespace-nowrap px-3 py-2 text-muted-foreground xl:table-cell">{u.last_login_at ? <Ago iso={u.last_login_at} /> : "—"}</td>
      <td className="hidden whitespace-nowrap px-3 py-2 text-muted-foreground xl:table-cell">{fmt(u.created_at)}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {!self && <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => send(`/users/${u.id}/active`, { active: u.active ? "0" : "1" }, u.active ? `Deactivate ${u.name}? Their open sessions end now.` : undefined)}>{u.active ? "Deactivate" : "Reactivate"}</Button>}
          {u.kind !== "external" && (resetting ? (
            <form onSubmit={(e) => { e.preventDefault(); void send(`/users/${u.id}/reset-password`, { new_password: pw }).then(() => { setPw(""); setResetting(false) }) }} className="flex items-center gap-1">
              <Input type="password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} placeholder="New password" aria-label={`New password for ${u.name}`} minLength={8} required className="h-7 w-36 text-[12.5px]" />
              <Button type="submit" size="sm" className="h-7" disabled={busy || pw.length < 8}>Set</Button>
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
    <form onSubmit={submit} className="grid content-start gap-2 rounded-lg border border-border p-4">
      <h3 className="text-[12px] font-semibold text-nav-fg">Add a team member</h3>
      <label className="grid gap-1 text-[12px] text-muted-foreground">Full name<Input value={f.name} onChange={set("name")} required aria-label="Full name" className="h-8 text-[13px]" /></label>
      <label className="grid gap-1 text-[12px] text-muted-foreground">Username<Input value={f.username} onChange={set("username")} required aria-label="Username" autoComplete="off" className="h-8 text-[13px]" /></label>
      <label className="grid gap-1 text-[12px] text-muted-foreground">Email (for notifications)<Input type="email" value={f.email} onChange={set("email")} placeholder="name@company.com" aria-label="Email" className="h-8 text-[13px]" /></label>
      <label className="grid gap-1 text-[12px] text-muted-foreground">Temporary password<Input type="password" value={f.password} onChange={set("password")} required minLength={8} aria-label="Temporary password" autoComplete="new-password" className="h-8 text-[13px]" /></label>
      <label className="grid gap-1 text-[12px] text-muted-foreground">Role
        <select value={f.role} onChange={set("role")} aria-label="Role" className="h-8 rounded-md border border-input bg-background px-2 text-[13px]">
          {roles.filter((r) => r !== "External").map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      <Button type="submit" size="sm" className="mt-1" disabled={busy || !f.name || !f.username || f.password.length < 8}>Create user</Button>
      <p className="text-[11.5px] text-muted-foreground">They change the password on first sign-in. Partners and customers are invited from a project's Team panel instead.</p>
    </form>
  )
}
