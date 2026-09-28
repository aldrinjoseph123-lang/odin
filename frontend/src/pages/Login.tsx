import { useEffect, useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AuthLayout } from "@/components/Brand"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, login, session, type SignIn } from "@/lib/api"

// After a successful login the rest of the app is still Jinja, so this is a
// full navigation, not a router push. ?next= is honoured only when relative —
// the same open-redirect rule Flask applies.
function destinationAfterLogin(mustChangePassword: boolean): string {
  if (mustChangePassword) return "/account"
  const next = new URLSearchParams(window.location.search).get("next") ?? ""
  return next.startsWith("/") && !next.startsWith("//") ? next : "/board"
}

export default function Login() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [signin, setSignin] = useState<SignIn | null>(null)
  // /login/password is the emergency form for accounts an admin flagged; it
  // always shows the password fields, even when staff must use Microsoft.
  const emergency = window.location.pathname === "/login/password"
  // e.g. "Your session has ended — please sign in again", queued before the redirect here
  useEffect(() => {
    session().then((s) => { setSignin(s.signin ?? { microsoft: false, microsoft_only: false }); if (s.messages?.length) setNotice(s.messages.join(" ")) })
      .catch(() => setSignin({ microsoft: false, microsoft_only: false }))
  }, [])
  const showPassword = emergency || !signin?.microsoft_only
  const next = new URLSearchParams(window.location.search).get("next")

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { user } = await login(username.trim(), password)
      window.location.assign(destinationAfterLogin(user.must_change_password))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server — try again")
      setBusy(false)
    }
  }

  return (
    <AuthLayout>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-[20px] font-bold tracking-tight">{emergency ? "Emergency sign-in" : "Sign in"}</CardTitle>
        </CardHeader>
        <CardContent>
          {notice && <Alert className="mb-4" role="status"><AlertDescription>{notice}</AlertDescription></Alert>}
          {emergency && <p className="mb-4 text-[12.5px] text-muted-foreground">For accounts an admin allowed to keep a password. Every use is recorded and the admins are told.</p>}
          {signin?.microsoft && !emergency && (
            <a href={`/auth/microsoft${next ? `?next=${encodeURIComponent(next)}` : ""}`}
              className="flex h-10 w-full items-center justify-center gap-2.5 rounded-lg border border-input bg-background text-[13.5px] font-medium hover:bg-muted">
              {/* the four-square Microsoft logo, their colours by their brand rules */}
              <svg viewBox="0 0 21 21" className="h-4 w-4" aria-hidden><path fill="#F25022" d="M1 1h9v9H1z" /><path fill="#7FBA00" d="M11 1h9v9h-9z" /><path fill="#00A4EF" d="M1 11h9v9H1z" /><path fill="#FFB900" d="M11 11h9v9h-9z" /></svg>
              Sign in with Microsoft
            </a>
          )}
          {signin?.microsoft && showPassword && !emergency && <p className="my-4 flex items-center gap-3 text-[11.5px] text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">or with a password</p>}
          {signin && showPassword && (
          <form onSubmit={submit} className="grid gap-4" noValidate>
            {error && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="grid gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={busy || !username || !password}>
              {busy ? "Signing in…" : "Log in"}
            </Button>
            <a href="/auth/reset" className="text-center text-[12.5px] text-muted-foreground hover:text-foreground hover:underline">Forgot password?</a>
          </form>
          )}
          {/* External partners and customers have no password; Flask serves the
              link-request page and the link itself outside Cloudflare Access. */}
          <p className="mt-4 text-center text-[12.5px] text-muted-foreground">
            Partner or customer? <a href="/auth/link" className="text-primary-text hover:underline">Sign in with an email link</a>
          </p>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
