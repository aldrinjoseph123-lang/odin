import { useEffect, useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { account, ApiError, postForm, type User } from "@/lib/api"
import { UserAvatar } from "@/components/UserAvatar"
import { ACCENTS, THEMES, applyTheme, type Accent, type Theme } from "@/lib/theme"
import { cn } from "@/lib/utils"
import { PageSkeleton } from "@/components/PageSkeleton"

export default function Account(_props: { user: User }) {
  const [me, setMe] = useState<Awaited<ReturnType<typeof account>> | null>(null)
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [pw, setPw] = useState({ current_password: "", new_password: "" })
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function load() { const m = await account(); setMe(m); setEmail(m.email ?? ""); setName(m.name) }
  useEffect(() => { document.title = "Account · Odin"; void load() }, [])
  async function send(path: string, fields: Record<string, string> | FormData, after?: () => void) {
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      setNotice(r.messages.join(" ") || null)
      await load(); after?.()
      // a forced password change done: the shell's gate lets the rest of the app open again
      if (r.messages.includes("Password updated") && me?.must_change_password) window.location.assign("/board")
    } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  if (!me) return <PageSkeleton />
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">My account</h1>
        <p className="text-[13px] text-muted-foreground">{me.name} · {me.username}{me.kind === "external" ? " · partner access" : ""}</p>
      </div>
      {me.must_change_password && <Alert className="mt-3"><AlertDescription>Set a new password before continuing. The one you were given is a shared secret.</AlertDescription></Alert>}
      {notice && <div className="mt-3 flex items-center justify-between rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status"><span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}
      <div className="mt-3 grid max-w-3xl gap-4 lg:grid-cols-2">
        <section className="grid content-start gap-3 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Appearance <span className="font-normal text-muted-foreground">yours, on every device you sign in on</span></h3>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Theme">
            {THEMES.map((t) => (
              <button key={t} type="button" role="radio" aria-checked={me.theme === t} disabled={busy}
                onClick={() => { applyTheme(t, me.accent as Accent); void send("/account/appearance", { theme: t, accent: me.accent }) }}
                className={cn("h-7 rounded-full border px-3 text-[12.5px] font-medium capitalize transition-colors", me.theme === t ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")}>{t}</button>
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
          <p className="text-[11.5px] text-muted-foreground">The accent is the one colour the app spends on selection and the primary action. Green, amber and red stay reserved for state.</p>
        </section>
        <form onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); if ((fd.get("avatar") as File | null)?.name) void send("/account/avatar", fd, () => e.currentTarget?.reset?.()) }} className="grid content-start gap-3 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Picture <span className="font-normal text-muted-foreground">shown wherever your name is</span></h3>
          <div className="flex items-center gap-3">
            <UserAvatar name={me.name} url={me.avatar_url} className="h-14 w-14" textClass="text-[18px]" />
            <div className="grid gap-2">
              <input type="file" name="avatar" accept="image/png,image/jpeg,image/gif,image/webp" aria-label="Choose a picture" className="text-[12.5px] file:mr-2 file:rounded-md file:border file:border-border file:bg-background file:px-2 file:py-1 file:text-[12.5px] file:font-medium" />
              <div className="flex gap-2">
                <Button type="submit" size="sm" variant="outline" disabled={busy}>Upload</Button>
                {me.avatar_url && <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => send("/account/avatar/remove", {})}>Remove</Button>}
              </div>
              <p className="text-[11.5px] text-muted-foreground">PNG, JPG, GIF or WebP, up to 2 MB. Square images look best.</p>
            </div>
          </div>
        </form>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); if (name.trim()) void send("/account/name", { name: name.trim() }, () => window.setTimeout(() => window.location.reload(), 400)) }} className="grid content-start gap-2 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Name <span className="font-normal text-muted-foreground">as others see it</span></h3>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label="Your name" className="h-8 text-[13px]" />
          <div><Button type="submit" size="sm" variant="outline" disabled={busy || !name.trim() || name.trim() === me.name}>Save name</Button></div>
          <p className="text-[11.5px] text-muted-foreground">Notes you already wrote keep the name they were written under.</p>
        </form>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send("/account/email", { email }) }} className="grid content-start gap-2 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Email <span className="font-normal text-muted-foreground">for notifications</span></h3>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" aria-label="Email address" className="h-8 text-[13px]" />
          <div><Button type="submit" size="sm" variant="outline" disabled={busy || email === (me.email ?? "")}>Save email</Button></div>
        </form>
        {me.kind === "internal" ? (
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); void send("/account", pw, () => setPw({ current_password: "", new_password: "" })) }} className="grid content-start gap-2 rounded-lg border border-border p-4">
            <h3 className="text-[12px] font-semibold text-nav-fg">Change password</h3>
            <label className="grid gap-1 text-[12px] text-muted-foreground">Current password<Input type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required autoComplete="current-password" aria-label="Current password" className="h-8 text-[13px]" /></label>
            <label className="grid gap-1 text-[12px] text-muted-foreground">New password<Input type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required minLength={8} autoComplete="new-password" aria-label="New password" className="h-8 text-[13px]" /></label>
            <div><Button type="submit" size="sm" disabled={busy || !pw.current_password || pw.new_password.length < 8}>Update password</Button></div>
          </form>
        ) : (
          <p className="rounded-lg border border-border p-4 text-[13px] text-muted-foreground">Partner accounts sign in with an email link and have no password.</p>
        )}
        <form key={me.email_kinds.map((k) => `${k.key}:${k.on}`).join("|")}
          onSubmit={(e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const fd = new FormData(e.currentTarget); void send("/account/notifications", Object.fromEntries(me.email_kinds.filter((k) => fd.get(k.key)).map((k) => [k.key, "on"]))) }}
          className="grid content-start gap-2 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Email me about <span className="font-normal text-muted-foreground">the bell shows everything either way</span></h3>
          {me.email_kinds.map((k) => (
            <label key={k.key} className="flex items-start gap-2 text-[13px]">
              <input type="checkbox" name={k.key} defaultChecked={k.on} className="mt-1 h-3.5 w-3.5 accent-primary" />
              <span>{k.label}</span>
            </label>
          ))}
          {!me.mail_enabled && <p className="text-[11.5px] text-muted-foreground">Email is not connected on this installation yet, so for now only the bell is used.</p>}
          <div><Button type="submit" size="sm" variant="outline" disabled={busy}>Save</Button></div>
        </form>
        <section className="grid content-start gap-2 rounded-lg border border-border p-4">
          <h3 className="text-[12px] font-semibold text-nav-fg">Sessions</h3>
          <p className="text-[12.5px] text-muted-foreground">Signed in on a shared or lost device? End every other session; this one stays signed in.</p>
          <div><Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => { if (window.confirm("Sign out of every other device?")) void send("/account/sign-out-others", {}) }}>Sign out of other devices</Button></div>
        </section>
      </div>
    </div>
  )
}
