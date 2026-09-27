import { useEffect, useState, type FormEvent } from "react"
import { useParams } from "react-router-dom"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AuthLayout } from "@/components/Brand"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
  useEffect(() => {
    document.title = token ? "Choose a new password · Odin" : "Reset your password · Odin"
    session().then((s) => { if (s.messages?.length) setMessage(s.messages.join(" ")) }).catch(() => {})
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
      <Card className="w-full max-w-sm">
        <CardHeader><CardTitle className="text-[20px] font-bold tracking-tight">{token ? "Choose a new password" : "Reset your password"}</CardTitle></CardHeader>
        <CardContent>
          <p className="mb-4 text-[13px] text-muted-foreground">
            {token ? "At least 12 characters. Every device signed in to this account will be signed out." : "Enter the email on your account and we will send a link that works once for 30 minutes."}
          </p>
          {message && <Alert className="mb-4" role="status"><AlertDescription>{message}</AlertDescription></Alert>}
          {done ? <a href="/login" className="inline-flex h-9 w-full items-center justify-center rounded-lg bg-primary text-[13px] font-medium text-primary-foreground">Sign in</a> :
          <form onSubmit={submit} className="grid gap-3">
            {token ? (
              <div className="grid gap-1.5"><Label htmlFor="pw">New password</Label>
                <Input id="pw" type="password" autoComplete="new-password" minLength={12} required autoFocus value={pw} onChange={(e) => setPw(e.target.value)} /></div>
            ) : (
              <div className="grid gap-1.5"><Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></div>
            )}
            <Button type="submit" disabled={busy || (token ? pw.length < 12 : !email.trim())}>{busy ? "Working…" : token ? "Set password" : "Email me a reset link"}</Button>
          </form>}
          <p className="mt-4 text-center text-[12.5px] text-muted-foreground"><a href="/login" className="text-primary-text hover:underline">Back to sign-in</a></p>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
