import { useEffect, useState, type FormEvent } from "react"
import { useSearchParams } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AuthLayout } from "@/components/Brand"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, postForm, session } from "@/lib/api"

// Partners and customers have no password: they ask for a one-time link.
// The reply never says whether the address is known (no enumeration).
export default function LinkRequest() {
  const [params] = useSearchParams()
  const [email, setEmail] = useState("")
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(params.get("expired") ? "That sign-in link is invalid or has expired — request a new one." : null)
  useEffect(() => {
    document.title = "Sign in by email · Odin"
    // the expired-link flash arrives here; ?expired already covers the wording
    session().then((s) => { if (s.messages?.length && !params.get("expired")) setMessage(s.messages.join(" ")) }).catch(() => {})
  }, [params])
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await postForm("/auth/link", { email: email.trim() })
      setMessage(r.messages.join(" ") || "If that address is on a project, a sign-in link is on its way")
    } catch (err) { setMessage(err instanceof ApiError ? err.message : "Could not send the request") } finally { setBusy(false) }
  }
  return (
    <AuthLayout>
      <Card className="w-full max-w-sm">
        <CardHeader><CardTitle className="text-[20px] font-bold tracking-tight">Sign in by email</CardTitle></CardHeader>
        <CardContent>
          <p className="mb-4 text-[13px] text-muted-foreground">Partners and customers sign in with a link sent to the email address they were invited with. It works once and expires in 30 minutes.</p>
          {message && <Alert className="mb-4" role="status"><AlertDescription>{message}</AlertDescription></Alert>}
          <form onSubmit={submit} className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <Button type="submit" disabled={busy || !email.trim()}>{busy ? "Sending…" : "Email me a sign-in link"}</Button>
          </form>
          <p className="mt-4 text-center text-[12.5px] text-muted-foreground"><a href="/login" className="text-primary-text hover:underline">Staff sign-in</a></p>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
