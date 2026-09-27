import { useEffect, useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, login, session } from "@/lib/api"

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
  // e.g. "Your session has ended — please sign in again", queued before the redirect here
  useEffect(() => { session().then((s) => { if (s.messages?.length) setNotice(s.messages.join(" ")) }).catch(() => {}) }, [])

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
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-2xl font-bold tracking-tight">Odin</CardTitle>
        </CardHeader>
        <CardContent>
          {notice && <Alert className="mb-4" role="status"><AlertDescription>{notice}</AlertDescription></Alert>}
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
          </form>
          {/* External partners and customers have no password; Flask serves the
              link-request page and the link itself outside Cloudflare Access. */}
          <p className="mt-4 text-center text-[12.5px] text-muted-foreground">
            Partner or customer? <a href="/auth/link" className="text-primary-text hover:underline">Sign in with an email link</a>
          </p>
        </CardContent>
      </Card>
    </main>
  )
}
