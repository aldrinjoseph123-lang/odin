import { useEffect, useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { account, ApiError, postForm, type User } from "@/lib/api"

export default function Account(_props: { user: User }) {
  const [me, setMe] = useState<Awaited<ReturnType<typeof account>> | null>(null)
  const [email, setEmail] = useState("")
  const [pw, setPw] = useState({ current_password: "", new_password: "" })
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function load() { const m = await account(); setMe(m); setEmail(m.email ?? "") }
  useEffect(() => { document.title = "Account · Odin"; void load() }, [])
  async function send(path: string, fields: Record<string, string>, after?: () => void) {
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      setNotice(r.messages.join(" ") || null)
      await load(); after?.()
      // a forced password change done: the shell's gate lets the rest of the app open again
      if (r.messages.includes("Password updated") && me?.must_change_password) window.location.assign("/board")
    } catch (e) { setNotice(e instanceof ApiError ? e.message : "That did not save") } finally { setBusy(false) }
  }
  if (!me) return <div className="p-5 text-[13px] text-muted-foreground">Loading…</div>
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">My account</h1>
        <p className="text-[13px] text-muted-foreground">{me.name} · {me.username}{me.kind === "external" ? " · partner access" : ""}</p>
      </div>
      {me.must_change_password && <Alert className="mt-3"><AlertDescription>Set a new password before continuing. The one you were given is a shared secret.</AlertDescription></Alert>}
      {notice && <div className="mt-3 flex items-center justify-between rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status"><span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}
      <div className="mt-3 grid max-w-3xl gap-4 lg:grid-cols-2">
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
      </div>
    </div>
  )
}
