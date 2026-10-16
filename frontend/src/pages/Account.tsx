import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react"
import { usePref } from "@/lib/usePref"
import { PageHeader } from "@/components/PageHeader"
import { toast } from "@/lib/toast"
import { PanelTitle } from "@/components/PanelTitle"
import { danger } from "@/lib/ui"
import { Segmented } from "@/components/Segmented"
import { Field } from "@/components/ui/field"
import { askConfirm } from "@/lib/confirm"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { account, accountEmail, accountMicrosoft, ApiError, calendarFeedOff, makeCalendarFeed, postForm, type Delivery, type User } from "@/lib/api"
import { UserAvatar } from "@/components/UserAvatar"
import { ACCENTS, THEMES, applyTheme, useAppearance } from "@/lib/theme"
import { MIN_PASSWORD, passwordRule } from "@/lib/password"
import { Notice } from "@/components/Notice"
import { cn } from "@/lib/utils"
import { ActivityPanel } from "@/components/ActivityPanel"
import { fmtWhen, viewersText } from "@/lib/format"
import { TwoStepPanel } from "@/components/TwoStepPanel"
import { LoadError, PageSkeleton } from "@/components/PageSkeleton"

// Arrow keys move the choice in a radio group and Tab reaches only the chosen
// one, as in any radio group (review P3-48).
function arrows(e: KeyboardEvent<HTMLDivElement>) {
  const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0
  const radios = [...e.currentTarget.querySelectorAll<HTMLButtonElement>("[role=radio]")]
  const at = radios.indexOf(document.activeElement as HTMLButtonElement)
  if (!step || at < 0) return
  e.preventDefault()
  const to = radios[(at + step + radios.length) % radios.length]
  to.focus(); to.click()
}

export default function Account({ user }: { user: User }) {
  const [me, setMe] = useState<Awaited<ReturnType<typeof account>> | null>(null)
  const [email, setEmail] = useState("")
  const [emailPw, setEmailPw] = useState("")
  const [name, setName] = useState("")
  const [pw, setPw] = useState({ current_password: "", new_password: "" })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const look = useAppearance()   // the header button changes it too: one source for both (review P2-33)
  const [fieldError, setFieldError] = useState<Record<string, string>>({})   // a refusal sits by its form, not in a toast that leaves (review P2-36)
  const [picture, setPicture] = useState<string | null>(null)
  const minPassword = user.prefs?.password_min_length ?? MIN_PASSWORD
  const [microsoft, setMicrosoft] = useState<{ available: boolean; linked: boolean } | null>(null)
  const [slash, setSlash] = usePref("shortcut.slash", true)   // read by the shell's key handler
  // whether the address on file was proven by its emailed link (review P2-3)
  const [mailCheck, setMailCheck] = useState<{ verified: boolean; checkable: boolean } | null>(null)
  async function load() {
    const m = await account(); setMe(m); setEmail(m.email ?? ""); setName(m.name)
    accountEmail().then(setMailCheck).catch(() => setMailCheck(null))
  }
  useEffect(() => {
    document.title = "Account · Odin"
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your account."))   // test report UX-8: it hung on the skeleton
    accountMicrosoft().then(setMicrosoft).catch(() => setMicrosoft(null))
  }, [])
  // `form`: where a refusal shows (under that form); without it, a toast
  async function send(path: string, fields: Record<string, string> | FormData, after?: () => void, form?: string) {
    setBusy(true)
    if (form) setFieldError((e) => ({ ...e, [form]: "" }))
    try {
      const r = await postForm(path, fields)
      { const said = r.messages.join(" "); if (said) toast(said) }
      await load(); after?.()
      // a forced password change done: the shell's gate lets the rest of the app open again
      if (r.messages.includes("Password updated") && me?.must_change_password) window.location.assign("/board")
    } catch (e) {
      const m = e instanceof ApiError ? e.message : "That did not save"
      if (form) setFieldError((x) => ({ ...x, [form]: m })); else toast(m, { tone: "bad" })
    } finally { setBusy(false) }
  }
  async function linkMicrosoft() {
    setBusy(true)
    try {
      const r = await postForm("/account/microsoft")
      if (r.location) window.location.assign(r.location)   // off to Microsoft; it comes back to this page
    } catch (e) { toast(e instanceof ApiError ? e.message : "Could not start the Microsoft sign-in", { tone: "bad" }); setBusy(false) }
  }
  if (error) return <LoadError message={error} />
  if (!me) return <PageSkeleton />
  return (
    <div className="px-5 pb-6 pt-4">
      <PageHeader title="Account" lede={`${me.name} · ${me.username}${me.kind === "external" ? ` · ${user.external_role === "Customer" ? "customer" : "partner"} access` : ""}`} />
      {me.must_change_password && <Alert className="mt-3"><AlertDescription>Set a new password before continuing. The one you were given is a shared secret.</AlertDescription></Alert>}
      <div className="mt-3 grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <section className="grid grid-cols-1 content-start gap-3 panel p-4">
          <PanelTitle className="mb-0" hint="yours, on every device you sign in on">Appearance</PanelTitle>
          {/* busy keeps the focus where it is: the handler ignores a press, nothing is disabled (P2-41) */}
          <Segmented label="Theme" value={look.theme} full onChange={(t) => { if (busy || t === look.theme) return; applyTheme(t, look.accent); void send("/account/appearance", { theme: t, accent: look.accent }) }}
            options={THEMES.map((t) => ({ value: t, label: t === "system" ? "Follow the device" : t === "light" ? "Light" : "Dark" }))} />
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Accent colour" onKeyDown={arrows}>
            {ACCENTS.map((c) => (
              <button key={c.key} type="button" role="radio" aria-checked={look.accent === c.key} tabIndex={look.accent === c.key ? 0 : -1} aria-label={c.label} title={c.label} aria-disabled={busy || undefined}
                onClick={() => { if (busy || c.key === look.accent) return; applyTheme(look.theme, c.key); void send("/account/appearance", { theme: look.theme, accent: c.key }) }}
                className={cn("h-7 w-7 rounded-full border-2 ring-1 ring-border ring-offset-1 ring-offset-background transition-transform", look.accent === c.key ? "scale-110 border-foreground" : "border-transparent hover:scale-105")}
                style={{ background: c.swatch }} />
            ))}
          </div>
          <p className="text-[12px] text-muted-foreground">The accent is the soft colour the app spends on selection and the primary action. Blue is the default. Red is offered, but overdue items are red too, so a red accent makes them harder to spot.</p>
          {me.kind !== "external" && (
            <>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="mr-1 text-[13px] text-muted-foreground">Home page</span>
                <Segmented label="Home page" value={me.home as "dashboard" | "board"} onChange={(k) => { if (!busy && k !== me.home) void send("/account/home", { home: k }, load) }}
                  options={[{ value: "dashboard", label: "Dashboard" }, { value: "board", label: "Flow" }]} />
              </div>
              <p className="text-[12px] text-muted-foreground">Where sign-in and the Odin logo land.</p>
            </>
          )}
          {/* single-key shortcuts must be able to go (WCAG 2.1.4): / search, ? the shortcuts sheet, 1-4 the flow's views; kept in this browser */}
          <label className="mt-1 flex items-center gap-2 text-[13px]">
            <Switch aria-label="Single-key shortcuts" checked={slash} onCheckedChange={(v) => { setSlash(v); toast(v ? "Single-key shortcuts on" : "Single-key shortcuts off") }} />
            Single-key shortcuts
          </label>
          <p className="text-[12px] text-muted-foreground">/ opens search, ? lists the shortcuts, 1–4 switch the flow's views. In this browser. {navigator.platform.includes("Mac") ? "⌘ K" : "Ctrl K"} always opens search.</p>
        </section>
        <form onSubmit={(e: FormEvent<HTMLFormElement>) => {
          e.preventDefault()
          const form = e.currentTarget   // read now: the event is gone by the time the upload ends, and the old file stayed picked
          const fd = new FormData(form)
          if (!(fd.get("avatar") as File | null)?.name) { setPicture("Choose a picture first."); return }
          setPicture(null)
          void send("/account/avatar", fd, () => form.reset())
        }} className="grid grid-cols-1 content-start gap-3 panel p-4">
          <PanelTitle className="mb-0" hint="shown wherever your name is">Picture</PanelTitle>
          <div className="flex flex-wrap items-center gap-3">
            <UserAvatar name={me.name} url={me.avatar_url} className="h-14 w-14" textClass="text-[17px]" />
            <div className="grid min-w-0 grid-cols-1 gap-2">
              <Input type="file" name="avatar" accept="image/png,image/jpeg,image/gif,image/webp" aria-label="Choose a picture" className="h-auto w-full py-1" onChange={() => setPicture(null)} />
              <div className="flex gap-2">
                <Button type="submit" size="sm" variant="outline" loading={busy}>Upload</Button>
                {me.avatar_url && <Button type="button" size="sm" variant="ghost" className={danger} disabled={busy}
                  onClick={async () => { if (!busy && await askConfirm("Remove your picture? Your initials show instead, wherever your name appears.", "Remove")) void send("/account/avatar/remove", {}) }}>Remove</Button>}
              </div>
              {picture && <Notice bad>{picture}</Notice>}
              <p className="text-[12px] text-muted-foreground">PNG, JPG, GIF or WebP, up to 2 MB. Square images look best.</p>
            </div>
          </div>
        </form>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (name.trim()) void send("/account/name", { name: name.trim() }, () => window.setTimeout(() => window.location.reload(), 400)) }} className="grid grid-cols-1 content-start gap-2 panel p-4">
          <PanelTitle className="mb-0" hint="as others see it">Name</PanelTitle>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label="Your name" className="h-8 text-[13px]" />
          <div><Button type="submit" size="sm" loading={busy} disabled={!name.trim() || name.trim() === me.name}>Save name</Button></div>
          <p className="text-[12px] text-muted-foreground">Notes you already wrote keep the name they were written under.</p>
        </form>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send("/account/email", { email, password: emailPw }, () => setEmailPw(""), "email") }} className="grid grid-cols-1 content-start gap-2 panel p-4">
          <PanelTitle className="mb-0" hint="for notifications">Email</PanelTitle>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" aria-label="Email address" className="h-8 text-[13px]" />
          {/* password reset links go to this address, so changing it takes the password */}
          {me.has_password && email !== (me.email ?? "") && (
            <Field label="Current password"><Input type="password" value={emailPw} onChange={(e) => setEmailPw(e.target.value)} required autoComplete="current-password" className="h-8 text-[13px]" /></Field>
          )}
          {fieldError.email && <Notice bad>{fieldError.email}</Notice>}
          <div><Button type="submit" size="sm" loading={busy} disabled={email === (me.email ?? "") || (me.has_password && !emailPw)}>Save email</Button></div>
          {mailCheck?.checkable && !mailCheck.verified && email === (me.email ?? "") && (
            <p className="text-[12px] text-muted-foreground">Not confirmed yet · <button type="button" className="text-primary-text hover:underline" aria-disabled={busy || undefined}
              onClick={() => { if (!busy) void send("/account/email/verify", {}) }}>Send link</button></p>
          )}
        </form>
        {me.kind === "internal" ? (
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send("/account", pw, () => setPw({ current_password: "", new_password: "" }), "password") }} className={cn("grid grid-cols-1 content-start gap-2 panel p-4", me.must_change_password && "order-first ring-2 ring-primary lg:col-span-2")}>
            <PanelTitle className="mb-0">Change password</PanelTitle>
            <Field label="Current password"><Input autoFocus={me.must_change_password} type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required autoComplete="current-password" className="h-8 text-[13px]" /></Field>
            <Field label="New password" hint={`${passwordRule(minPassword)} A few unrelated words work well.`}><Input type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required minLength={minPassword} autoComplete="new-password" className="h-8 text-[13px]" /></Field>
            {fieldError.password && <Notice bad>{fieldError.password}</Notice>}
            <div><Button type="submit" size="sm" loading={busy} disabled={!pw.new_password}>Update password</Button></div>
          </form>
        ) : (
          <p className="panel p-4 text-[13px] text-muted-foreground">Partner accounts sign in with an email link and have no password.</p>
        )}
        <NotifyForm key={me.email_kinds.map((k) => `${k.key}:${k.mode}`).join("|")} me={me} busy={busy} onSave={(modes) => send("/account/notifications", modes)} />
        {me.calendar && <CalendarFeed createdAt={me.calendar.created_at} onChange={load} />}
        {me.kind !== "external" && <TwoStepPanel />}
        {microsoft?.available && !microsoft.linked && (
          <section className="grid grid-cols-1 content-start gap-2 panel p-4">
            <PanelTitle className="mb-0">Microsoft sign-in</PanelTitle>
            <p className="text-[13px] text-muted-foreground">Link your Microsoft work account to sign in with it. You sign in to Microsoft once to prove it is yours.</p>
            <div><Button type="button" size="sm" variant="outline" loading={busy} onClick={() => void linkMicrosoft()}>Link Microsoft</Button></div>
          </section>
        )}
        {me.activity && <ActivityPanel n a={me.activity} note={`Odin counts the minutes it is open, visible and in use (idle time never counts) and when you were last seen. ${viewersText(me.activity_viewers)}`} />}
        <section className="grid grid-cols-1 content-start gap-2 panel p-4">
          <PanelTitle className="mb-0">Sessions</PanelTitle>
          <p className="text-[13px] text-muted-foreground">Signed in on a shared or lost device? End every other session; this one stays signed in.</p>
          <div><Button type="button" size="sm" variant="outline" disabled={busy} onClick={async () => { if (!busy && await askConfirm("Sign out of every other device? Anyone signed in as you elsewhere has to sign in again.", "Sign out")) void send("/account/sign-out-others", {}) }}>Sign out of other devices</Button></div>
        </section>
      </div>
    </div>
  )
}

// "Tell me about": per kind at once, in the daily summary, or off (email and Teams alike; the bell
// always at once). Save wakes only once a choice differs from what is saved (review P3-41). The
// parent keys it on the saved values, so a save remounts it clean.
const MODES: { value: Delivery; label: string }[] = [{ value: "instant", label: "At once" }, { value: "summary", label: "Daily summary" }, { value: "off", label: "Off" }]
function NotifyForm({ me, busy, onSave }: { me: { kind: string; email_kinds: { key: string; label: string; mode: Delivery }[]; mail_enabled: boolean }; busy: boolean; onSave: (modes: Record<string, Delivery>) => void }) {
  const [mode, setMode] = useState<Record<string, Delivery>>(() => Object.fromEntries(me.email_kinds.map((k) => [k.key, k.mode])))
  const dirty = me.email_kinds.some((k) => mode[k.key] !== k.mode)
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); onSave(mode) }} className="grid grid-cols-1 content-start gap-2 panel p-4">
      <PanelTitle className="mb-0" hint={me.kind === "internal" ? "by email and in Teams; the bell shows everything at once either way" : "by email; the bell shows everything at once either way"}>Tell me about</PanelTitle>
      {me.email_kinds.map((k) => (
        <div key={k.key} className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
          <span className="min-w-0 flex-1">{k.label}</span>
          <Segmented label={k.label} value={mode[k.key]} onChange={(v) => setMode({ ...mode, [k.key]: v })} options={MODES} />
        </div>
      ))}
      <p className="text-[12px] text-muted-foreground">The daily summary is one mail at the digest time on working days, grouped by rollout, with your next step on each.</p>
      {!me.mail_enabled && <p className="text-[12px] text-muted-foreground">Email is not connected on this installation yet, so for now only the bell is used.</p>}
      <div><Button type="submit" size="sm" loading={busy} disabled={!dirty}>Save</Button></div>
    </form>
  )
}

// The personal calendar feed: an address Outlook subscribes to (Add calendar › From the internet).
// It holds a secret, so it is shown once, when made or rotated; rotating kills the old one.
function CalendarFeed({ createdAt, onChange }: { createdAt: string | null; onChange: () => Promise<void> }) {
  const [url, setUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function make() {
    if (createdAt && !(await askConfirm("Make a new address? The one Outlook uses now stops working; subscribe again with the new one.", "Make a new address"))) return
    setBusy(true)
    try { setUrl((await makeCalendarFeed()).url); await onChange() } catch (e) { toast(e instanceof ApiError ? e.message : "Could not make the feed", { tone: "bad" }) } finally { setBusy(false) }
  }
  async function off() {
    if (!(await askConfirm("Turn the calendar feed off? Calendars subscribed to it stop updating.", "Turn off"))) return
    setBusy(true)
    try { await calendarFeedOff(); setUrl(null); await onChange(); toast("Calendar feed turned off") } catch (e) { toast(e instanceof ApiError ? e.message : "That did not save", { tone: "bad" }) } finally { setBusy(false) }
  }
  return (
    <section className="grid grid-cols-1 content-start gap-2 panel p-4">
      <PanelTitle className="mb-0" hint="for Outlook or any calendar">Calendar feed</PanelTitle>
      <p className="text-[13px] text-muted-foreground">Your tasks with a due date, and the target dates and milestones of your rollouts, in your own calendar. Read only; it refreshes when your calendar checks it.</p>
      {url && (
        <div className="grid grid-cols-1 gap-2">
          <Input readOnly value={url} aria-label="Calendar feed address" onFocus={(e) => e.currentTarget.select()} className="h-8 text-[12px]" />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => { void navigator.clipboard?.writeText(url).then(() => toast("Address copied")) }}>Copy address</Button>
            <span className="text-[12px] text-muted-foreground">Shown once: anyone with it can read your calendar.</span>
          </div>
        </div>
      )}
      {!url && createdAt && <p className="text-[12px] text-muted-foreground">On since {fmtWhen(createdAt)}.</p>}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant={createdAt ? "outline" : "default"} loading={busy} onClick={() => void make()}>{createdAt ? "Make a new address" : "Make a feed"}</Button>
        {createdAt && <Button type="button" size="sm" variant="ghost" className={danger} disabled={busy} onClick={() => void off()}>Turn off</Button>}
      </div>
    </section>
  )
}
