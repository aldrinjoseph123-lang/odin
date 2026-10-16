import { useEffect, useState, type ComponentProps, type FormEvent } from "react"
import { useParams } from "react-router-dom"
import { CheckCircle2 } from "lucide-react"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { Notice } from "@/components/Notice"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, joinInfo, joinSubmit, session, type JoinInfo } from "@/lib/api"
import { MIN_PASSWORD, passwordRule } from "@/lib/password"
import { fmtDate } from "@/lib/format"

// A sign-up link from an admin: the new colleague gives their details and a
// password, picks how Odin should reach them, and waits for approval. Nothing
// is active until an admin approves the request on the Users page.
export default function Join() {
  const token = useParams().token ?? ""
  const [info, setInfo] = useState<JoinInfo | null>(null)
  const [bad, setBad] = useState<string | null>(null)
  const [f, setF] = useState({ name: "", username: "", email: "", password: "", confirm: "" })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [minLength, setMinLength] = useState(MIN_PASSWORD)   // the admin's password policy, once the session answers
  useEffect(() => {
    document.title = "Join Odin"
    session().then((s) => { if (s.signin?.password_min_length) setMinLength(s.signin.password_min_length) }).catch(() => {})
    joinInfo(token).then(setInfo).catch((e) => setBad(e instanceof ApiError ? e.message : "This sign-up link could not be opened"))
  }, [token])
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (f.password !== f.confirm) { setError("The two passwords differ"); return }
    setBusy(true); setError(null)
    try { await joinSubmit(token, { name: f.name, username: f.username, email: f.email, password: f.password }); setDone(true) }
    catch (x) { setError(x instanceof ApiError ? x.message : "Could not reach Odin — try again") } finally { setBusy(false) }
  }

  if (bad) return (
    <AuthLayout>
      <AuthHeading title="This sign-up link does not work">It may have expired, been used up or been revoked. Ask whoever sent it for a new one; if you already have an account, sign in.</AuthHeading>
      <p className="text-[13px] text-muted-foreground">{bad}</p>
      <a href="/login" className="mt-6 inline-block text-[14px] text-primary-text hover:underline">Go to sign-in</a>
    </AuthLayout>
  )
  if (!info) return <AuthLayout><p className="text-sm text-muted-foreground">Opening your invitation…</p></AuthLayout>
  if (done) return (
    <AuthLayout>
      <AuthHeading title="Request sent"><span className="inline-flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-ok" aria-hidden /> An admin will review it.</span></AuthHeading>
      <p className="text-[14px] text-muted-foreground">Once approved, sign in with <b className="text-foreground">{f.username}</b> and the password you chose{info.project ? `; you will already be on ${info.project}` : ""}. Odin emails <b className="text-foreground">{f.email}</b> when that happens; until then sign-in will not work.</p>
      <a href="/login" className="mt-6 inline-block text-[14px] text-primary-text hover:underline">Go to sign-in</a>
    </AuthLayout>
  )
  // the same field as the other sign-in pages: 14 px label, 44 px input
  const row = (id: string, text: string, input: Partial<ComponentProps<typeof Input>>) => (
    <div className="grid grid-cols-1 gap-2"><Label htmlFor={id} className="text-[14px]">{text}</Label><Input id={id} required className="h-11 text-base" {...input} /></div>
  )
  return (
    <AuthLayout>
      <AuthHeading title={`Join ${info.company} on Odin`}>
        You are invited as <b className="text-foreground">{info.role}</b>{info.project ? <> on <b className="text-foreground">{info.project}</b> ({info.project_role})</> : null}. The link works until {fmtDate(info.expires_at)}.
      </AuthHeading>
      <form onSubmit={submit} className="grid grid-cols-1 gap-4">
        {row("name", "Full name", { autoComplete: "name", value: f.name, onChange: set("name") })}
        {row("email", "Work email", { type: "email", autoComplete: "email", value: f.email, onChange: set("email"), placeholder: info.domains.length ? `you@${info.domains[0]}` : "you@company.com" })}
        {row("username", "Username", { autoComplete: "username", value: f.username, onChange: set("username"), placeholder: "e.g. omar.haddad" })}
        <div className="grid grid-cols-2 gap-3">
          {row("password", "Password", { type: "password", autoComplete: "new-password", minLength, value: f.password, onChange: set("password") })}
          {row("confirm", "Again", { type: "password", autoComplete: "new-password", value: f.confirm, onChange: set("confirm") })}
        </div>
        <p className="-mt-2 text-[12px] text-muted-foreground">{passwordRule(minLength)}</p>
        {error && <Notice bad>{error}</Notice>}
        <Button type="submit" className="h-11 text-sm" loading={busy}>Ask to join</Button>
      </form>
    </AuthLayout>
  )
}
