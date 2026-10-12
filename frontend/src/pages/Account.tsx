import { useEffect, useState, type FormEvent } from "react"
import { PageHeader } from "@/components/PageHeader"
import { Segmented } from "@/components/Segmented"
import { toast } from "@/lib/toast"
import { PanelTitle } from "@/components/PanelTitle"
import { chip, danger } from "@/lib/ui"
import { askConfirm } from "@/lib/confirm"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { account, ApiError, postForm, type User } from "@/lib/api"
import { UserAvatar } from "@/components/UserAvatar"
import { ACCENTS, THEMES, applyTheme, type Accent, type Theme } from "@/lib/theme"
import { cn } from "@/lib/utils"
import { ActivityPanel } from "@/components/ActivityPanel"
import { viewersText } from "@/lib/format"
import { TwoStepPanel } from "@/components/TwoStepPanel"
import { LoadError, PageSkeleton } from "@/components/PageSkeleton"

export default function Account({ user }: { user: User }) {
  const [me, setMe] = useState<Awaited<ReturnType<typeof account>> | null>(null)
  const [email, setEmail] = useState("")
  const [emailPw, setEmailPw] = useState("")
  const [name, setName] = useState("")
  const [pw, setPw] = useState({ current_password: "", new_password: "" })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function load() { const m = await account(); setMe(m); setEmail(m.email ?? ""); setName(m.name) }
  useEffect(() => {
    document.title = "Account · Odin"
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Could not load your account."))   // test report UX-8: it hung on the skeleton
  }, [])
  async function send(path: string, fields: Record<string, string> | FormData, after?: () => void) {
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      { const said = r.messages.join(" "); if (said) toast(said) }
      await load(); after?.()
      // a forced password change done: the shell's gate lets the rest of the app open again
      if (r.messages.includes("Password updated") && me?.must_change_password) window.location.assign("/board")
    } catch (e) { toast(e instanceof ApiError ? e.message : "That did not save", { tone: "bad" }) } finally { setBusy(false) }
  }
  if (error) return <LoadError message={error} />
  if (!me) return <PageSkeleton />
  return (
    <div className="px-5 pb-6 pt-4">
      <PageHeader title="My account" lede={`${me.name} · ${me.username}${me.kind === "external" ? ` · ${user.external_role === "Customer" ? "customer" : "partner"} access` : ""}`} />
      {me.must_change_password && <Alert className="mt-3"><AlertDescription>Set a new password before continuing. The one you were given is a shared secret.</AlertDescription></Alert>}
      <div className="mt-3 grid max-w-5xl grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="grid grid-cols-1 content-start gap-3 panel p-4">
          <PanelTitle className="mb-0" hint="yours, on every device you sign in on">Appearance</PanelTitle>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Theme">
            {THEMES.map((t) => (
              <button key={t} type="button" role="radio" aria-checked={me.theme === t} disabled={busy}
                onClick={() => { applyTheme(t, me.accent as Accent); void send("/account/appearance", { theme: t, accent: me.accent }) }}
                className={cn(chip(me.theme === t), "capitalize")}>{t}</button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Accent colour">
            {ACCENTS.map((c) => (
              <button key={c.key} type="button" role="radio" aria-checked={me.accent === c.key} aria-label={c.label} title={c.label} disabled={busy}
                onClick={() => { applyTheme(me.theme as Theme, c.key); void send("/account/appearance", { theme: me.theme, accent: c.key }) }}
                className={cn("h-7 w-7 rounded-full border-2 ring-1 ring-border ring-offset-1 ring-offset-background transition-transform", me.accent === c.key ? "scale-110 border-foreground" : "border-transparent hover:scale-105")}
                style={{ background: c.swatch }} />
            ))}
          </div>
          <p className="text-[12px] text-muted-foreground">The accent is the soft colour the app spends on selection and the primary action. Blue is the default. Red is offered, but overdue items are red too, so a red accent makes them harder to spot.</p>
          {me.kind !== "external" && (
            <>
              <div className="mt-1 flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Home page">
                <span className="mr-1 text-[13px] text-muted-foreground">Home page</span>
                {([["dashboard", "Dashboard"], ["board", "Flow"]] as const).map(([k, label]) => (
                  <button key={k} type="button" role="radio" aria-checked={me.home === k} disabled={busy} onClick={() => void send("/account/home", { home: k }, load)}
                    className={chip(me.home === k)}>{label}</button>
                ))}
              </div>
              <p className="text-[12px] text-muted-foreground">Where sign-in and the Odin logo land.</p>
            </>
          )}
        </section>
        <form onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); if ((fd.get("avatar") as File | null)?.name) void send("/account/avatar", fd, () => e.currentTarget?.reset?.()) }} className="grid grid-cols-1 content-start gap-3 panel p-4">
          <PanelTitle className="mb-0" hint="shown wherever your name is">Picture</PanelTitle>
          <div className="flex flex-wrap items-center gap-3">
            <UserAvatar name={me.name} url={me.avatar_url} className="h-14 w-14" textClass="text-[17px]" />
            <div className="grid min-w-0 grid-cols-1 gap-2">
              <input type="file" name="avatar" accept="image/png,image/jpeg,image/gif,image/webp" aria-label="Choose a picture" className="w-full" />
              <div className="flex gap-2">
                <Button type="submit" size="sm" variant="outline" loading={busy}>Upload</Button>
                {me.avatar_url && <Button type="button" size="sm" variant="ghost" className={danger} disabled={busy} onClick={() => send("/account/avatar/remove", {})}>Remove</Button>}
              </div>
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
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send("/account/email", { email, password: emailPw }, () => setEmailPw("")) }} className="grid grid-cols-1 content-start gap-2 panel p-4">
          <PanelTitle className="mb-0" hint="for notifications">Email</PanelTitle>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" aria-label="Email address" className="h-8 text-[13px]" />
          {/* password reset links go to this address, so changing it takes the password */}
          {me.has_password && email !== (me.email ?? "") && (
            <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Current password<Input type="password" value={emailPw} onChange={(e) => setEmailPw(e.target.value)} required autoComplete="current-password" className="h-8 text-[13px]" /></label>
          )}
          <div><Button type="submit" size="sm" loading={busy} disabled={email === (me.email ?? "") || (me.has_password && !emailPw)}>Save email</Button></div>
        </form>
        {me.kind === "internal" && (
          <section className="grid grid-cols-1 content-start gap-2 panel p-4" aria-label="How Odin reaches you">
            <PanelTitle className="mb-0" hint="besides the bell">Reach me by</PanelTitle>
            <Segmented label="Reach me by" full disabled={busy} value={me.notify_via} onChange={(v) => void send("/account/notify-via", { notify_via: v })}
              options={[{ value: "email", label: "Email" }, { value: "teams", label: "Microsoft Teams" }]} />
            {me.notify_via === "teams" && !me.teams_ready && <p className="text-[12px] text-muted-foreground">Teams is not connected on this installation yet; you get email until it is.</p>}
          </section>
        )}
        {me.kind === "internal" ? (
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send("/account", pw, () => setPw({ current_password: "", new_password: "" })) }} className={cn("grid grid-cols-1 content-start gap-2 panel p-4", me.must_change_password && "order-first ring-2 ring-primary lg:col-span-2")}>
            <PanelTitle className="mb-0">Change password</PanelTitle>
            <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">Current password<Input autoFocus={me.must_change_password} type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required autoComplete="current-password" aria-label="Current password" className="h-8 text-[13px]" /></label>
            <label className="grid grid-cols-1 gap-1 text-[12px] text-muted-foreground">New password<Input type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required minLength={8} autoComplete="new-password" aria-label="New password" className="h-8 text-[13px]" /><span className="text-[12px]">Use a few unrelated words: at least 12 characters, unless your admin set another length.</span></label>
            <div><Button type="submit" size="sm" loading={busy} disabled={!pw.new_password}>Update password</Button></div>
          </form>
        ) : (
          <p className="panel p-4 text-[13px] text-muted-foreground">Partner accounts sign in with an email link and have no password.</p>
        )}
        <form key={me.email_kinds.map((k) => `${k.key}:${k.on}`).join("|")}
          onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); void send("/account/notifications", Object.fromEntries(me.email_kinds.filter((k) => fd.get(k.key)).map((k) => [k.key, "on"]))) }}
          className="grid grid-cols-1 content-start gap-2 panel p-4">
          <PanelTitle className="mb-0" hint="the bell shows everything either way">Email me about</PanelTitle>
          {me.email_kinds.map((k) => (
            <label key={k.key} className="flex items-start gap-2 text-[13px]">
              <Switch name={k.key} defaultChecked={k.on} className="mt-1" />
              <span>{k.label}</span>
            </label>
          ))}
          {!me.mail_enabled && <p className="text-[12px] text-muted-foreground">Email is not connected on this installation yet, so for now only the bell is used.</p>}
          <div><Button type="submit" size="sm" loading={busy}>Save</Button></div>
        </form>
        {me.kind !== "external" && <TwoStepPanel />}
        {me.activity && <ActivityPanel n a={me.activity} note={`Odin counts the minutes it is open, visible and in use (idle time never counts) and when you were last seen. ${viewersText(me.activity_viewers)}`} />}
        <section className="grid grid-cols-1 content-start gap-2 panel p-4">
          <PanelTitle className="mb-0">Sessions</PanelTitle>
          <p className="text-[13px] text-muted-foreground">Signed in on a shared or lost device? End every other session; this one stays signed in.</p>
          <div><Button type="button" size="sm" variant="outline" disabled={busy} onClick={async () => { if (await askConfirm("Sign out of every other device? Anyone signed in as you elsewhere has to sign in again.", "Sign out")) void send("/account/sign-out-others", {}) }}>Sign out of other devices</Button></div>
        </section>
      </div>
    </div>
  )
}
