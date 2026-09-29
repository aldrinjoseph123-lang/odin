import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, login, session, type SignIn } from "@/lib/api"

// ?next= is honoured only when relative — the same open-redirect rule Flask applies.
function destinationAfterLogin(user: { must_change_password: boolean; home: "dashboard" | "board" }): string {
  if (user.must_change_password) return "/account"
  const next = new URLSearchParams(window.location.search).get("next") ?? ""
  return next.startsWith("/") && !next.startsWith("//") ? next : user.home === "board" ? "/board" : "/dashboard"
}

const field = "h-11 text-base"   // 44 px: a comfortable target on a phone; 16 px stops iOS zooming in on focus

// Three ways in, one page: staff with Microsoft (when set up), staff with a
// password (unless the admin requires Microsoft; /login/password is the
// emergency form for flagged accounts), and partners with an email link.
export default function Login() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [show, setShow] = useState(false)
  const [caps, setCaps] = useState(false)
  const [error, setError] = useState<{ field: "username" | "password" | "form"; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [signin, setSignin] = useState<SignIn | null>(null)
  const userRef = useRef<HTMLInputElement>(null)
  const passRef = useRef<HTMLInputElement>(null)
  const emergency = window.location.pathname === "/login/password"
  const next = new URLSearchParams(window.location.search).get("next")

  useEffect(() => {
    document.title = emergency ? "Emergency sign-in · Odin" : "Sign in · Odin"
    // e.g. "Your session has ended — please sign in again", queued before the redirect here
    session().then((s) => { setSignin(s.signin ?? { microsoft: false, microsoft_only: false }); if (s.messages?.length) setNotice(s.messages.join(" ")) })
      .catch(() => setSignin({ microsoft: false, microsoft_only: false }))
  }, [emergency])
  const showPassword = emergency || (signin !== null && !signin.microsoft_only)
  const microsoft = !emergency && !!signin?.microsoft

  async function submit(event: FormEvent) {
    event.preventDefault()
    // The button stays enabled: say what's missing, beside the field, instead.
    if (!username.trim()) { setError({ field: "username", text: "Enter your username" }); userRef.current?.focus(); return }
    if (!password) { setError({ field: "password", text: "Enter your password" }); passRef.current?.focus(); return }
    setBusy(true)
    setError(null)
    try {
      const { user } = await login(username.trim(), password)
      window.location.assign(destinationAfterLogin(user))
    } catch (err) {
      setError({ field: err instanceof ApiError ? "password" : "form", text: err instanceof ApiError ? err.message : "Could not reach Odin — check your connection and try again" })
      setBusy(false)
      passRef.current?.select()
    }
  }
  const capsCheck = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.("CapsLock") ?? false)

  return (
    <AuthLayout>
      <AuthHeading title={emergency ? "Emergency sign-in" : "Sign in to Odin"}>
        {emergency ? "For accounts an admin allowed to keep a password. Each use is recorded and the admins are told."
          : microsoft ? "Staff sign in with their work account." : "Use the username and password your admin gave you."}
      </AuthHeading>

      {notice && <Alert className="mb-5" role="status"><AlertDescription>{notice}</AlertDescription></Alert>}

      {microsoft && (
        <a href={`/auth/microsoft${next ? `?next=${encodeURIComponent(next)}` : ""}`}
          className="flex h-11 w-full items-center justify-center gap-2.5 rounded-lg border border-input bg-background text-sm font-medium outline-none transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
          {/* the four-square Microsoft logo, in Microsoft's colours per their sign-in button rules */}
          <svg viewBox="0 0 21 21" className="h-[18px] w-[18px]" aria-hidden><path fill="#F25022" d="M1 1h9v9H1z" /><path fill="#7FBA00" d="M11 1h9v9h-9z" /><path fill="#00A4EF" d="M1 11h9v9H1z" /><path fill="#FFB900" d="M11 11h9v9h-9z" /></svg>
          Sign in with Microsoft
        </a>
      )}
      {microsoft && showPassword && <p className="my-5 flex items-center gap-3 text-[12px] text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">or with a password</p>}

      {showPassword && (
        <form onSubmit={submit} className="grid gap-4" noValidate aria-busy={busy}>
          {error?.field === "form" && <Alert variant="destructive" role="alert"><AlertDescription>{error.text}</AlertDescription></Alert>}
          <div className="grid gap-1.5">
            <Label htmlFor="username" className="text-[13.5px]">Username</Label>
            <Input id="username" ref={userRef} name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus={!microsoft}
              value={username} onChange={(e) => { setUsername(e.target.value); if (error?.field === "username") setError(null) }}
              aria-invalid={error?.field === "username" || undefined} aria-describedby={error?.field === "username" ? "username-error" : undefined} className={field} />
            {error?.field === "username" && <p id="username-error" role="alert" className="text-[13px] text-bad">{error.text}</p>}
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <Label htmlFor="password" className="text-[13.5px]">Password</Label>
              {!emergency && <a href="/auth/reset" className="text-[13px] text-primary-text hover:underline">Forgot password?</a>}
            </div>
            <div className="relative">
              <Input id="password" ref={passRef} name="password" type={show ? "text" : "password"} autoComplete="current-password"
                value={password} onChange={(e) => { setPassword(e.target.value); if (error?.field === "password") setError(null) }}
                onKeyUp={capsCheck} onKeyDown={capsCheck} onBlur={() => setCaps(false)}
                aria-invalid={error?.field === "password" || undefined} aria-describedby={[error?.field === "password" && "password-error", caps && "caps-warning"].filter(Boolean).join(" ") || undefined}
                className={`${field} pr-12`} />
              <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
                className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50">
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {caps && <p id="caps-warning" className="text-[13px] text-warn">Caps Lock is on</p>}
            {error?.field === "password" && <p id="password-error" role="alert" className="text-[13px] text-bad">{error.text}</p>}
          </div>
          <Button type="submit" disabled={busy} className="mt-1 h-11 text-sm">
            {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Signing in…</> : "Sign in"}
          </Button>
        </form>
      )}

      {/* Partners and customers have no password: their way in is the email link. */}
      {!emergency && (
        <a href="/auth/link" className="mt-8 flex min-h-11 items-center justify-between gap-3 panel px-4 py-3 text-[13.5px] outline-none transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
          <span><span className="block font-medium">Partner or customer?</span><span className="text-muted-foreground">Get a one-time sign-in link by email</span></span>
          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        </a>
      )}
    </AuthLayout>
  )
}
