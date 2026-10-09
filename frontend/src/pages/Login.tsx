import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, login, loginCode, session, type SignIn, type User } from "@/lib/api"

// ?next= is honoured only when relative — the same open-redirect rule Flask applies.
function destinationAfterLogin(user: Pick<User, "must_change_password" | "must_enroll_mfa" | "home">): string {
  if (user.must_change_password || user.must_enroll_mfa) return "/account"
  const next = new URLSearchParams(window.location.search).get("next") ?? ""
  // one leading slash, no second slash or backslash, no control characters ("/\\evil.com" and "/\t/evil.com" leave the site)
  return /^\/(?![\/\\])[^\\\x00-\x1f\x7f]*$/.test(next) ? next : user.home === "board" ? "/board" : "/dashboard"
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
  // two-step sign-in: after the right password, the code (or a recovery code)
  const [codeStep, setCodeStep] = useState(false)
  const [code, setCode] = useState("")
  const [recovery, setRecovery] = useState(false)
  const userRef = useRef<HTMLInputElement>(null)
  const passRef = useRef<HTMLInputElement>(null)
  const emergency = window.location.pathname === "/login/password"
  const next = new URLSearchParams(window.location.search).get("next")

  useEffect(() => {
    document.title = emergency ? "Emergency sign-in · Odin" : "Sign in · Odin"
    // e.g. "Your session has ended — please sign in again", queued before the redirect here
    session().then((s) => { setSignin(s.signin ?? { microsoft: false, microsoft_only: false }); if (s.messages?.length) setNotice(s.messages.join(" ")) })
      .catch(() => { setSignin({ microsoft: false, microsoft_only: false }); setNotice("Odin is not answering just now (it may be restarting). Reload in a moment if signing in fails.") })
  }, [emergency])
  const showPassword = emergency || (signin !== null && !signin.microsoft_only)
  const microsoft = !emergency && !codeStep && !!signin?.microsoft

  async function submit(event: FormEvent) {
    event.preventDefault()
    // The button stays enabled: say what's missing, beside the field, instead.
    if (!username.trim()) { setError({ field: "username", text: "Enter your username" }); userRef.current?.focus(); return }
    if (!password) { setError({ field: "password", text: "Enter your password" }); passRef.current?.focus(); return }
    setBusy(true)
    setError(null)
    try {
      const r = await login(username.trim(), password)
      if (r.code_needed) { setCodeStep(true); setBusy(false); return }
      window.location.assign(destinationAfterLogin(r.user!))
    } catch (err) {
      setError({ field: err instanceof ApiError ? "password" : "form", text: err instanceof ApiError ? err.message : "Could not reach Odin — check your connection and try again" })
      setBusy(false)
      passRef.current?.select()
    }
  }
  async function submitCode(event: FormEvent) {
    event.preventDefault()
    if (!code.trim()) { setError({ field: "form", text: recovery ? "Enter a recovery code" : "Enter the 6-digit code" }); return }
    setBusy(true); setError(null)
    try {
      const { user } = await loginCode(code.trim())
      window.location.assign(destinationAfterLogin(user))
    } catch (err) {
      const again = err instanceof ApiError && (err.status === 410 || err.status === 429)
      if (again) { setCodeStep(false); setPassword(""); setCode("") }
      setError({ field: again ? "password" : "form", text: err instanceof ApiError ? err.message : "Could not reach Odin — check your connection and try again" })
      setBusy(false)
    }
  }
  const capsCheck = (e: KeyboardEvent<HTMLInputElement>) => setCaps(e.getModifierState?.("CapsLock") ?? false)

  return (
    <AuthLayout>
      <AuthHeading title={codeStep ? "Two-step sign-in" : emergency ? "Emergency sign-in" : "Sign in to Odin"}>
        {codeStep ? `Signed in as ${username.trim()}: one more step.` : emergency ? "For accounts an admin allowed to keep a password. Each use is recorded and the admins are told."
          : microsoft ? "Staff sign in with their work account." : "Use the username and password your admin gave you."}
      </AuthHeading>

      {notice && <Alert className="mb-5" role="status"><AlertDescription>{notice}</AlertDescription></Alert>}

      {microsoft && (
        <a href={`/auth/microsoft${next ? `?next=${encodeURIComponent(next)}` : ""}`}
          className="flex h-11 w-full items-center justify-center gap-3 rounded-lg border border-input bg-background text-sm font-medium outline-none transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
          {/* the four-square Microsoft logo, in Microsoft's colours per their sign-in button rules */}
          <svg viewBox="0 0 21 21" className="h-[18px] w-[18px]" aria-hidden><path fill="#F25022" d="M1 1h9v9H1z" /><path fill="#7FBA00" d="M11 1h9v9h-9z" /><path fill="#00A4EF" d="M1 11h9v9H1z" /><path fill="#FFB900" d="M11 11h9v9h-9z" /></svg>
          Sign in with Microsoft
        </a>
      )}
      {microsoft && showPassword && <p className="my-5 flex items-center gap-3 text-[12px] text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">or with a password</p>}

      {codeStep && (
        <form onSubmit={submitCode} className="grid grid-cols-1 gap-4" noValidate aria-busy={busy} aria-label="Two-step sign-in">
          <p className="text-[14px] text-muted-foreground">{recovery ? "Enter one of the recovery codes you saved when you set up two-step sign-in. Each works once." : "Open your authenticator app and enter the 6-digit code for Odin."}</p>
          {error?.field === "form" && <Alert variant="destructive" role="alert"><AlertDescription>{error.text}</AlertDescription></Alert>}
          <div className="grid grid-cols-1 gap-2">
            <Label htmlFor="code" className="text-[14px]">{recovery ? "Recovery code" : "Code"}</Label>
            <Input id="code" name="code" autoFocus autoComplete="one-time-code" inputMode={recovery ? "text" : "numeric"} spellCheck={false} autoCapitalize="none"
              maxLength={recovery ? 12 : 7} value={code} onChange={(e) => { setCode(e.target.value); if (error) setError(null) }} className={`${field} tracking-[0.2em] tabular-nums`} />
          </div>
          <Button type="submit" loading={busy} className="mt-1 h-11 text-sm">
            {busy ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Checking…</> : "Continue"}
          </Button>
          <div className="flex flex-wrap justify-between gap-2 text-[13px]">
            <button type="button" className="text-primary-text hover:underline" onClick={() => { setRecovery(!recovery); setCode(""); setError(null) }}>
              {recovery ? "Use the authenticator code" : "Lost your phone? Use a recovery code"}</button>
            <button type="button" className="text-muted-foreground hover:underline" onClick={() => { setCodeStep(false); setCode(""); setPassword(""); setError(null) }}>Start again</button>
          </div>
        </form>
      )}

      {showPassword && !codeStep && (
        <form onSubmit={submit} className="grid grid-cols-1 gap-4" noValidate aria-busy={busy}>
          {error?.field === "form" && <Alert variant="destructive" role="alert"><AlertDescription>{error.text}</AlertDescription></Alert>}
          <div className="grid grid-cols-1 gap-2">
            <Label htmlFor="username" className="text-[14px]">Username</Label>
            <Input id="username" ref={userRef} name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus={!microsoft}
              value={username} onChange={(e) => { setUsername(e.target.value); if (error?.field === "username") setError(null) }}
              aria-invalid={error?.field === "username" || undefined} aria-describedby={error?.field === "username" ? "username-error" : undefined} className={field} />
            {error?.field === "username" && <p id="username-error" role="alert" className="text-[13px] text-bad">{error.text}</p>}
          </div>
          <div className="grid grid-cols-1 gap-2">
            <Label htmlFor="password" className="text-[14px]">Password</Label>
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
          <Button type="submit" loading={busy} className="mt-1 h-11 text-sm">Sign in</Button>
          {/* after the button, so Tab goes username → password → Sign in */}
          {!emergency && <a href="/auth/reset" className="justify-self-center text-[13px] text-primary-text hover:underline">Forgot password?</a>}
        </form>
      )}

      {/* Partners and customers have no password: their way in is the email link. */}
      {!emergency && !codeStep && (
        <a href="/auth/link" className="mt-8 flex min-h-11 items-center justify-between gap-3 panel px-4 py-3 text-[14px] outline-none transition-colors hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50">
          <span><span className="block font-medium">Partner or customer?</span><span className="text-muted-foreground">Get a one-time sign-in link by email</span></span>
          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        </a>
      )}
    </AuthLayout>
  )
}
