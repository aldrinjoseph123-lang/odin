import { useEffect, useState, type FormEvent } from "react"
import { useParams } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, postForm, session } from "@/lib/api"
import { MIN_PASSWORD, passwordRule } from "@/lib/password"

// Two steps on one page: ask for a link (/auth/reset), then set the new
// password from it (/auth/reset/<token>). Replies never say whether an
// address has an account.
export default function ForgotPassword() {
  const token = useParams().token
  const [email, setEmail] = useState("")
  const [pw, setPw] = useState("")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; bad?: boolean } | null>(null)
  const [done, setDone] = useState(false)
  const [minutes, setMinutes] = useState(30)   // the link lifetime from Settings, once the session answers
  const [minLength, setMinLength] = useState(MIN_PASSWORD)   // the password policy, likewise
  useEffect(() => {
    document.title = token ? "Choose a new password · Odin" : "Reset your password · Odin"
    session().then((s) => {
      if (s.signin?.link_minutes) setMinutes(s.signin.link_minutes)
      if (s.signin?.password_min_length) setMinLength(s.signin.password_min_length)
      if (s.messages?.length) setMessage({ text: s.messages.join(" "), bad: true })   // the only flash sent here is a dead reset link
    }).catch(() => {})
  }, [token])
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = token ? await postForm(`/auth/reset/${token}`, { new_password: pw }) : await postForm("/auth/reset", { email: email.trim() })
      if (token && r.location === "/login") { setDone(true); setMessage({ text: r.messages.join(" ") || "Password changed" }); return }
      setMessage(r.messages.length ? { text: r.messages.join(" ") } : null)
    } catch (err) { setMessage({ text: err instanceof ApiError ? err.message : "Could not reach the server", bad: true }) } finally { setBusy(false) }
  }
  return (
    <AuthLayout>
      <AuthHeading title={token ? "Choose a new password" : "Reset your password"}>
        {token ? `${passwordRule(minLength)} Every device signed in to this account will be signed out.`
          : `Enter the email on your account. We'll send a link that works once, for ${minutes} minutes.`}
      </AuthHeading>
      {message && <Alert className="mb-5" role={message.bad ? "alert" : "status"} variant={message.bad ? "destructive" : "default"}><AlertDescription>{message.text}</AlertDescription></Alert>}
      {/* a failed reset (an expired or used link) leads to a new one, not to a dead end */}
      {token && message?.bad && !done && <p className="-mt-2 mb-5 text-[14px]"><a href="/auth/reset" className="text-primary-text hover:underline">Request a new link</a></p>}
      {done ? <a href="/login" className={buttonVariants({ className: "h-11 w-full text-sm" })}>Sign in</a> : (
        <form onSubmit={submit} className="grid grid-cols-1 gap-4" aria-busy={busy}>
          {token ? (
            <div className="grid grid-cols-1 gap-2"><Label htmlFor="pw" className="text-[14px]">New password</Label>
              <Input id="pw" type="password" autoComplete="new-password" minLength={minLength} required autoFocus value={pw} onChange={(e) => setPw(e.target.value)} className="h-11 text-base" /></div>
          ) : (
            <div className="grid grid-cols-1 gap-2"><Label htmlFor="email" className="text-[14px]">Email</Label>
              <Input id="email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className="h-11 text-base" /></div>
          )}
          <Button type="submit" className="mt-1 h-11 text-sm" loading={busy}>
            {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Working…</> : token ? "Set password" : "Email me a reset link"}
          </Button>
        </form>
      )}
      <a href="/login" className="mt-6 inline-flex min-h-11 items-center gap-2 text-[14px] text-primary-text hover:underline"><ArrowLeft className="h-4 w-4" aria-hidden /> Back to sign-in</a>
    </AuthLayout>
  )
}
