import { useCallback, useEffect, useState, type FormEvent } from "react"
import { ShieldCheck } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, twoStep, twoStepCodes, twoStepConfirm, twoStepOff, twoStepSetup, type TwoStep } from "@/lib/api"
import { fmtDate } from "@/lib/format"

// Two-step sign-in on the Account page: set up with an authenticator app (QR
// code or the key typed in), recovery codes shown once, new codes or turning
// it off with the password and a code. Required by the admin: no way off, and
// sign-in lands here until it is set up.
export function TwoStepPanel() {
  const [s, setS] = useState<TwoStep | null>(null)
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [mode, setMode] = useState<"off" | "codes" | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)   // setting up: the password first
  const load = useCallback(() => twoStep().then(setS).catch(() => setErr("Could not load two-step sign-in")), [])
  useEffect(() => { void load() }, [load])
  if (!s || !s.password) return null

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null)
    try { await fn() } catch (x) { setErr(x instanceof ApiError ? x.message : "That did not work") } finally { setBusy(false) }
  }
  const start = (e: FormEvent) => { e.preventDefault(); void run(async () => { setSetup(await twoStepSetup(password)); setCode(""); setPassword(""); setAsking(false) }) }
  const confirm = (e: FormEvent) => { e.preventDefault(); void run(async () => {
    const r = await twoStepConfirm(code); setCodes(r.recovery_codes); setSetup(null); setCode(""); await load()
  }) }
  const prove = (e: FormEvent) => { e.preventDefault(); void run(async () => {
    if (mode === "off") { await twoStepOff(password, code); await load() } else { setCodes((await twoStepCodes(password, code)).recovery_codes); await load() }
    setMode(null); setPassword(""); setCode("")
  }) }
  const save = () => {
    const url = URL.createObjectURL(new Blob([`Odin recovery codes\nEach works once, instead of the authenticator code.\n\n${codes!.join("\n")}\n`], { type: "text/plain" }))
    const a = Object.assign(document.createElement("a"), { href: url, download: "odin-recovery-codes.txt" })
    a.click(); URL.revokeObjectURL(url)
  }
  const codeField = (label: string) => (
    <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">{label}
      <Input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="numeric" maxLength={12} className="h-8 w-40 tracking-[0.15em] tabular-nums" />
    </label>
  )

  return (
    <section className="grid grid-cols-1 content-start gap-3 panel p-4" aria-label="Two-step sign-in">
      <h2 data-n className="flex items-center gap-1.5 text-[12px] font-semibold text-nav-fg"><ShieldCheck className="h-3.5 w-3.5" aria-hidden /> Two-step sign-in
        <span className="font-normal text-muted-foreground">{s.enabled ? `on since ${fmtDate(s.enabled_at)}` : s.required ? "required by your admin" : "off"}</span></h2>
      {s.required && !s.enabled && !codes && <Alert><AlertDescription>Your admin requires two-step sign-in. Set it up to continue using Odin.</AlertDescription></Alert>}
      {err && <p className="text-[12.5px] text-bad" role="alert">{err}</p>}

      {codes && (
        <div className="grid grid-cols-1 gap-2 rounded-lg bg-muted/60 p-3">
          <p className="text-[12.5px] font-medium">Your recovery codes: keep them somewhere safe. Each works once if you lose your phone; they are not shown again.</p>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[12.5px]" aria-label="Recovery codes">{codes.map((c) => <li key={c}>{c}</li>)}</ul>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={save}>Download as a file</Button>
            <Button size="sm" variant="outline" onClick={() => void navigator.clipboard.writeText(codes.join("\n")).catch(() => {})}>Copy</Button>
            <Button size="sm" onClick={() => { setCodes(null); if (s.required) window.location.assign("/") }}>I have saved them</Button>
          </div>
        </div>
      )}

      {!s.enabled && !setup && !codes && (
        <>
          <p className="text-[12.5px] text-muted-foreground">After your password, Odin also asks for a code from an authenticator app on your phone (Microsoft Authenticator, Google Authenticator, 1Password and the like), so a stolen password alone is not enough.</p>
          {!asking ? <div><Button size="sm" disabled={busy} onClick={() => setAsking(true)}>Set up two-step sign-in</Button></div> : (
            <form onSubmit={start} className="flex flex-wrap items-end gap-2">
              <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Your password<Input type="password" autoComplete="current-password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} className="h-8 w-56" /></label>
              <Button type="submit" size="sm" disabled={busy || !password}>Continue</Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => { setAsking(false); setPassword("") }}>Cancel</Button>
            </form>
          )}
        </>
      )}

      {setup && (
        <form onSubmit={confirm} className="grid grid-cols-1 gap-3">
          <p className="text-[12.5px] text-muted-foreground">1. In your authenticator app, add an account and scan this code.</p>
          {/* black on white whatever the theme: scanners need the contrast */}
          <div className="w-fit rounded-lg bg-white p-2" role="img" aria-label="QR code for your authenticator app" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p className="text-[12.5px] text-muted-foreground">Can't scan? Type this key instead: <code className="select-all break-all rounded bg-muted px-1 font-mono text-[12px] text-foreground">{setup.secret.match(/.{1,4}/g)!.join(" ")}</code></p>
          <p className="text-[12.5px] text-muted-foreground">2. Enter the 6-digit code the app shows.</p>
          <div className="flex flex-wrap items-end gap-2">{codeField("Code")}<Button type="submit" size="sm" disabled={busy || code.replace(/\D/g, "").length !== 6}>Turn on</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSetup(null)}>Cancel</Button></div>
        </form>
      )}

      {s.enabled && !codes && (
        <>
          <p className="text-[12.5px] text-muted-foreground">{s.recovery_left} recovery code{s.recovery_left === 1 ? "" : "s"} left.{s.recovery_left <= 2 ? " Make new ones now." : ""}</p>
          {!mode && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setMode("codes")}>New recovery codes</Button>
              {!s.required && <Button size="sm" variant="ghost" className="text-bad" onClick={() => setMode("off")}>Turn off</Button>}
            </div>
          )}
          {mode && (
            <form onSubmit={prove} className="grid grid-cols-1 gap-2">
              <p className="text-[12.5px] text-muted-foreground">{mode === "off" ? "Confirm it is you to turn two-step sign-in off." : "Confirm it is you. The old codes stop working."}</p>
              <label className="grid grid-cols-1 gap-1 text-[12.5px] font-medium">Password<Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="h-8 max-w-xs" /></label>
              {codeField("Authenticator or recovery code")}
              <div className="flex gap-2"><Button type="submit" size="sm" variant={mode === "off" ? "destructive" : "default"} disabled={busy || !password || !code}>{mode === "off" ? "Turn off" : "Make new codes"}</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => { setMode(null); setErr(null) }}>Cancel</Button></div>
            </form>
          )}
        </>
      )}
    </section>
  )
}
