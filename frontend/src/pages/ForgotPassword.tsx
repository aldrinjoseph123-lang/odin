import { useEffect, useState, type FormEvent } from "react"
import { useParams } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, postForm, session } from "@/lib/api"

// Two steps on one page: ask for a link (/auth/reset), then set the new
// password from it (/auth/reset/<token>). Replies never say whether an
// address has an account.
export default function ForgotPassword() {
  const token = useParams().token
  const [email, setEmail] = useState("")
  const [pw, setPw] = useState("")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [minutes, setMinutes] = useState(30)   // the link lifetime from Settings, once the session answers
  useEffect(() => {
    document.title = token ? "Choose a new password · Odin" : "Reset your password · Odin"
    session().then((s) => { if (s.signin?.link_minutes) setMinutes(s.signin.link_minutes); if (s.messages?.length) setMessage(s.messages.join(" ")) }).catch(() => {})
  }, [token])
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = token ? await postForm(`/auth/reset/${token}`, { new_password: pw }) : await postForm("/auth/reset", { email: email.trim() })
      if (token && r.location === "/login") { setDone(true); setMessage(r.messages.join(" ") || "Password changed"); return }
      setMessage(r.messages.join(" ") || null)
    } catch (err) { setMessage(err instanceof ApiError ? err.message : "Could not reach the server") } finally { setBusy(false) }
  }
  return (
    <AuthLayout>
      <AuthHeading title={token ? "Choose a new password" : "Reset your password"}>
        {token ? "At least 12 characters. Every device signed in to this account will be signed out."
          : `Enter the email on your account. We'll send a link that works once, for ${minutes} minutes.`}
      </AuthHeading>
      {message && <Alert className="mb-5" role="status"><AlertDescription>{message}</AlertDescription></Alert>}
      {done ? <a href="/login" className={buttonVariants({ className: "h-11 w-full text-sm" })}>Sign in</a> : (
        <form onSubmit={submit} className="grid grid-cols-1 gap-4" aria-busy={busy}>
          {token ? (
            <div className="grid grid-cols-1 gap-1.5"><Label htmlFor="pw" className="text-[14px]">New password</Label>
              <Input id="pw" type="password" autoComplete="new-password" minLength={12} required autoFocus value={pw} onChange={(e) => setPw(e.target.value)} className="h-11 text-base" /></div>
          ) : (
            <div className="grid grid-cols-1 gap-1.5"><Label htmlFor="email" className="text-[14px]">Email</Label>
              <Input id="email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className="h-11 text-base" /></div>
          )}
          <Button type="submit" className="mt-1 h-11 text-sm" disabled={busy}>
            {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Working…</> : token ? "Set password" : "Email me a reset link"}
          </Button>
        </form>
      )}
      <a href="/login" className="mt-6 inline-flex min-h-11 items-center gap-1.5 text-[14px] text-primary-text hover:underline"><ArrowLeft className="h-4 w-4" aria-hidden /> Back to sign-in</a>
    </AuthLayout>
  )
}
