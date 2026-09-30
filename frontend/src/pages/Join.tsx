import { useEffect, useState, type FormEvent } from "react"
import { useParams } from "react-router-dom"
import { CheckCircle2, Mail, MessageSquare } from "lucide-react"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, joinInfo, joinSubmit, type JoinInfo } from "@/lib/api"
import { cn } from "@/lib/utils"
import { fmtDate } from "@/lib/format"

// A sign-up link from an admin: the new colleague gives their details and a
// password, picks how Odin should reach them, and waits for approval. Nothing
// is active until an admin approves the request on the Users page.
export default function Join() {
  const token = useParams().token ?? ""
  const [info, setInfo] = useState<JoinInfo | null>(null)
  const [bad, setBad] = useState<string | null>(null)
  const [f, setF] = useState({ name: "", username: "", email: "", password: "", confirm: "", notify_via: "email" as "email" | "teams" })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  useEffect(() => {
    document.title = "Join Odin"
    joinInfo(token).then(setInfo).catch((e) => setBad(e instanceof ApiError ? e.message : "This sign-up link could not be opened"))
  }, [token])
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (f.password !== f.confirm) { setError("The two passwords differ"); return }
    setBusy(true); setError(null)
    try { await joinSubmit(token, { name: f.name, username: f.username, email: f.email, password: f.password, notify_via: f.notify_via }); setDone(true) }
    catch (x) { setError(x instanceof ApiError ? x.message : "Could not reach Odin — try again") } finally { setBusy(false) }
  }

  if (bad) return <AuthLayout><AuthHeading title="Link not valid">{bad}</AuthHeading></AuthLayout>
  if (!info) return <AuthLayout><p className="text-sm text-muted-foreground">Opening your invitation…</p></AuthLayout>
  if (done) return (
    <AuthLayout>
      <AuthHeading title="Request sent"><span className="inline-flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4 text-ok" aria-hidden /> An admin will review it.</span></AuthHeading>
      <p className="text-[13.5px] text-muted-foreground">Once approved, sign in with <b className="text-foreground">{f.username}</b> and the password you chose{info.project ? `; you will already be on ${info.project}` : ""}.</p>
      <a href="/login" className="mt-6 inline-block text-[13.5px] text-primary-text hover:underline">Go to sign-in</a>
    </AuthLayout>
  )
  const label = "grid gap-1.5 text-[13px] font-medium"
  return (
    <AuthLayout>
      <AuthHeading title={`Join ${info.company} on Odin`}>
        You are invited as <b className="text-foreground">{info.role}</b>{info.project ? <> on <b className="text-foreground">{info.project}</b> ({info.project_role})</> : null}. The link works until {fmtDate(info.expires_at)}.
      </AuthHeading>
      <form onSubmit={submit} className="grid gap-4" noValidate>
        <label className={label}>Full name<Input required autoComplete="name" value={f.name} onChange={set("name")} className="h-10" /></label>
        <label className={label}>Work email<Input required type="email" autoComplete="email" value={f.email} onChange={set("email")} className="h-10"
          placeholder={info.domains.length ? `you@${info.domains[0]}` : "you@company.com"} /></label>
        <label className={label}>Username<Input required autoComplete="username" value={f.username} onChange={set("username")} className="h-10" placeholder="e.g. omar.haddad" /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className={label}>Password<Input required type="password" autoComplete="new-password" value={f.password} onChange={set("password")} className="h-10" /></label>
          <label className={label}>Again<Input required type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} className="h-10" /></label>
        </div>
        <p className="-mt-2 text-[12px] text-muted-foreground">At least 12 characters, mixing letters with numbers or symbols.</p>
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium">How should Odin reach you?</legend>
          <div className="grid grid-cols-2 gap-2" role="radiogroup">
            {([["email", "Email", Mail], ["teams", "Microsoft Teams", MessageSquare]] as const).map(([v, text, Icon]) => (
              <button key={v} type="button" role="radio" aria-checked={f.notify_via === v} onClick={() => setF({ ...f, notify_via: v })}
                className={cn("flex h-11 items-center justify-center gap-2 rounded-lg border text-[13px]", f.notify_via === v ? "border-primary bg-accent font-medium" : "border-input hover:bg-muted")}>
                <Icon className="h-4 w-4" aria-hidden />{text}</button>
            ))}
          </div>
          <p className="mt-1.5 text-[12px] text-muted-foreground">Always in Odin's bell too. Change it later on your account page.</p>
        </fieldset>
        {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
        <Button type="submit" className="h-11 text-sm" disabled={busy || !f.name || !f.email || !f.username || !f.password}>{busy ? "Sending…" : "Ask to join"}</Button>
      </form>
    </AuthLayout>
  )
}
