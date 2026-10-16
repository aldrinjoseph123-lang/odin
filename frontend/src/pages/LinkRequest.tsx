import { useEffect, useState, type FormEvent } from "react"
import { useSearchParams } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, postForm, session } from "@/lib/api"

// Partners and customers have no password: they ask for a one-time link.
// The reply never says whether the address is known (no enumeration).
export default function LinkRequest() {
  const [params] = useSearchParams()
  const [email, setEmail] = useState("")
  const [busy, setBusy] = useState(false)
  const [minutes, setMinutes] = useState(30)
  const [message, setMessage] = useState<{ text: string; bad?: boolean } | null>(params.get("expired") ? { text: "That sign-in link is invalid or has expired. Request a new one.", bad: true } : null)
  useEffect(() => {
    document.title = "Sign in by email · Odin"
    // the expired-link flash arrives here; ?expired already covers the wording
    session().then((s) => { if (s.signin?.link_minutes) setMinutes(s.signin.link_minutes); if (s.messages?.length && !params.get("expired")) setMessage({ text: s.messages.join(" ") }) }).catch(() => {})
  }, [params])
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await postForm("/auth/link", { email: email.trim() })
      setMessage({ text: r.messages.join(" ") || "If that address is on a rollout, a sign-in link is on its way" })
    } catch (err) { setMessage({ text: err instanceof ApiError ? err.message : "Could not send the request", bad: true }) } finally { setBusy(false) }
  }
  return (
    <AuthLayout>
      <AuthHeading title="Sign in by email">
        Partners and customers get a link at the address they were invited with. It works once, for {minutes} minutes.
      </AuthHeading>
      {message && <Alert className="mb-5" role={message.bad ? "alert" : "status"} variant={message.bad ? "destructive" : "default"}><AlertDescription>{message.text}</AlertDescription></Alert>}
      <form onSubmit={submit} className="grid grid-cols-1 gap-4" aria-busy={busy}>
        <div className="grid grid-cols-1 gap-2">
          <Label htmlFor="email" className="text-[14px]">Email</Label>
          <Input id="email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className="h-11 text-base" />
        </div>
        <Button type="submit" className="mt-1 h-11 text-sm" loading={busy}>
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Sending…</> : "Email me a sign-in link"}
        </Button>
      </form>
      <a href="/login" className="mt-6 inline-flex min-h-11 items-center gap-2 text-[14px] text-primary-text hover:underline"><ArrowLeft className="h-4 w-4" aria-hidden /> Staff sign-in</a>
    </AuthLayout>
  )
}
