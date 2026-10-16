import { useState, type FormEvent } from "react"
import { danger } from "@/lib/ui"
import { ShieldCheck } from "lucide-react"
import { PanelTitle } from "@/components/PanelTitle"
import { Field } from "@/components/ui/field"
import { Notice } from "@/components/Notice"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, twoStep, twoStepCodes, twoStepConfirm, twoStepOff, twoStepSetup } from "@/lib/api"
import { copyWithToast } from "@/lib/copy"
import { fmtDate } from "@/lib/format"
import { useUnsavedGuard } from "@/lib/useUnsavedGuard"
import { useLoad } from "@/lib/useLoad"
import { LoadFailed } from "@/components/LoadFailed"

// Two-step sign-in on the Account page: set up with an authenticator app (QR
// code or the key typed in), recovery codes shown once, new codes or turning
// it off with the password and a code. Required by the admin: no way off, and
// sign-in lands here until it is set up.
export function TwoStepPanel() {
  const { data: s, error: failed, reload: load } = useLoad("two-step", twoStep)
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null)
  const [codes, setCodes] = useState<string[] | null>(null)
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [mode, setMode] = useState<"off" | "codes" | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)   // setting up: the password first
  // the codes are shown once: leaving before they are kept asks first (review P3-38)
  useUnsavedGuard(codes !== null, "Leave this page? Your recovery codes are shown only once: download or copy them first.")
  if (!s) return failed ? <LoadFailed what="two-step sign-in" onRetry={() => void load()} /> : null
  if (!s.password) return null

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
    // in the page, and the address kept a moment: some browsers start the download after the click returns
    const a = Object.assign(document.createElement("a"), { href: url, download: "odin-recovery-codes.txt" })
    document.body.append(a); a.click(); a.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }
  const codeField = (label: string) => (
    <Field label={label}>
      <Input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="numeric" maxLength={24} className="h-8 w-40 tracking-[0.15em] tabular-nums" />
    </Field>
  )

  return (
    <section className="grid grid-cols-1 content-start gap-3 panel p-4" aria-label="Two-step sign-in">
      <PanelTitle className="mb-0" icon={<ShieldCheck className="h-3.5 w-3.5" aria-hidden />} hint={s.enabled ? `on since ${fmtDate(s.enabled_at)}` : s.required ? "required by your admin" : "off"}>Two-step sign-in</PanelTitle>
      {s.required && !s.enabled && !codes && <Alert><AlertDescription>Your admin requires two-step sign-in. Set it up to continue using Odin.</AlertDescription></Alert>}
      {err && <Notice bad>{err}</Notice>}

      {codes && (
        <div className="grid grid-cols-1 gap-2 rounded-lg bg-muted/60 p-3">
          <p className="text-[13px] font-medium">Your recovery codes: keep them somewhere safe. Each works once if you lose your phone; they are not shown again.</p>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[13px]" aria-label="Recovery codes">{codes.map((c) => <li key={c}>{c}</li>)}</ul>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={save}>Download as a file</Button>
            <Button size="sm" variant="outline" onClick={() => void copyWithToast(codes.join("\n"), "recovery codes")}>Copy</Button>
            <Button size="sm" onClick={() => { setCodes(null); if (s.required) window.setTimeout(() => window.location.assign("/"), 0) }}>I have saved them</Button>
          </div>
        </div>
      )}

      {!s.enabled && !setup && !codes && (
        <>
          <p className="text-[13px] text-muted-foreground">After your password, Odin also asks for a code from an authenticator app on your phone (Microsoft Authenticator, Google Authenticator, 1Password and the like), so a stolen password alone is not enough.</p>
          {!asking ? <div><Button size="sm" disabled={busy} onClick={() => setAsking(true)}>Set up two-step sign-in</Button></div> : (
            <form onSubmit={start} className="flex flex-wrap items-end gap-2">
              <Field label="Your password"><Input type="password" autoComplete="current-password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} className="h-8 w-56" /></Field>
              <Button type="submit" size="sm" loading={busy} disabled={!password}>Continue</Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => { setAsking(false); setPassword("") }}>Cancel</Button>
            </form>
          )}
        </>
      )}

      {setup && (
        <form onSubmit={confirm} className="grid grid-cols-1 gap-3">
          <p className="text-[13px] text-muted-foreground">1. In your authenticator app, add an account and scan this code.</p>
          {/* black on white whatever the theme: scanners need the contrast */}
          <div className="w-fit rounded-lg bg-white p-2" role="img" aria-label="QR code for your authenticator app" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
          <p className="text-[13px] text-muted-foreground">Can't scan? Type this key instead: <code className="select-all break-all rounded bg-muted px-1 font-mono text-[12px] text-foreground">{setup.secret.match(/.{1,4}/g)!.join(" ")}</code></p>
          <p className="text-[13px] text-muted-foreground">2. Enter the 6-digit code the app shows.</p>
          <div className="flex flex-wrap items-end gap-2">{codeField("Code")}<Button type="submit" size="sm" loading={busy} disabled={code.replace(/\D/g, "").length !== 6}>Turn on</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSetup(null)}>Cancel</Button></div>
        </form>
      )}

      {s.enabled && !codes && (
        <>
          <p className="text-[13px] text-muted-foreground">{s.recovery_left} recovery code{s.recovery_left === 1 ? "" : "s"} left.{s.recovery_left <= 2 ? " Make new ones now." : ""}</p>
          {!mode && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setMode("codes")}>New recovery codes</Button>
              {!s.required && <Button size="sm" variant="ghost" className={danger} onClick={() => setMode("off")}>Turn off</Button>}
            </div>
          )}
          {mode && (
            <form onSubmit={prove} className="grid grid-cols-1 gap-2">
              <p className="text-[13px] text-muted-foreground">{mode === "off" ? "Confirm it is you to turn two-step sign-in off." : "Confirm it is you. The old codes stop working."}</p>
              <Field label="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="h-8 max-w-xs" /></Field>
              {codeField("Authenticator or recovery code")}
              <div className="flex gap-2"><Button type="submit" size="sm" variant={mode === "off" ? "destructive" : "default"} loading={busy} disabled={!password || !code}>{mode === "off" ? "Turn off" : "Make new codes"}</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => { setMode(null); setErr(null) }}>Cancel</Button></div>
            </form>
          )}
        </>
      )}
    </section>
  )
}
