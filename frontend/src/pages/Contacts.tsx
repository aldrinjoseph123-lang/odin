import { useCallback, useEffect, useState, type ReactNode } from "react"
import { Trash2 } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError, contacts, postForm, type ContactsData, type User } from "@/lib/api"
import { PageSkeleton } from "@/components/PageSkeleton"

type Send = (path: string, fields?: Record<string, string>, confirmText?: string) => Promise<unknown>

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-lg border border-border p-4"><h3 className="mb-3 text-[12px] font-semibold text-nav-fg">{title}</h3>{children}</section>
}

function AddRow({ withEmail, placeholder, button, busy, onSubmit }: { withEmail: boolean; placeholder: string; button: string; busy: boolean; onSubmit: (f: Record<string, string>) => Promise<unknown> }) {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (name.trim()) void onSubmit(withEmail ? { name: name.trim(), email } : { name: name.trim() }).then(() => { setName(""); setEmail("") }) }} className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
      <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={placeholder} aria-label={placeholder} required className="h-8 w-52 text-[13px]" />
      {withEmail && <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" aria-label={`Email for new ${placeholder.toLowerCase()}`} className="h-8 w-52 text-[13px]" />}
      <Button type="submit" size="sm" variant="outline" disabled={busy || !name.trim()}>{button}</Button>
    </form>
  )
}

function Line({ name, email, onDelete, busy }: { name: string; email?: string | null; onDelete: () => void; busy: boolean }) {
  return (
    <li className="flex items-center gap-2 text-[13px]">
      <span className="min-w-0 flex-1 truncate">{name}{email && <span className="text-muted-foreground"> · {email}</span>}</span>
      <button type="button" disabled={busy} onClick={onDelete} aria-label={`Delete ${name}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>
    </li>
  )
}

export default function Contacts(_props: { user: User }) {
  const [data, setData] = useState<ContactsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ text: string; undo?: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try { setData(await contacts()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load contacts") }
  }, [])
  useEffect(() => { document.title = "Contacts & partners · Odin"; void load() }, [load])
  const send: Send = async (path, fields = {}, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return null
    setBusy(true)
    try { const r = await postForm(path, fields); setNotice(r.messages.length ? { text: r.messages.join(" "), undo: r.undo } : null); await load(); return r }
    catch (e) { setNotice({ text: e instanceof ApiError ? e.message : "That did not save" }); return null } finally { setBusy(false) }
  }
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!data) return <PageSkeleton />
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <a href="/settings" className="text-[12.5px] text-muted-foreground hover:text-foreground">Settings</a><span className="text-[12.5px] text-muted-foreground">/</span>
        <h1 className="text-[17px] font-semibold tracking-tight">Contacts & partners</h1>
        <p className="text-[13px] text-muted-foreground">the pick-lists the project form offers</p>
      </div>
      {notice && (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status">
          <span>{notice.text}{notice.undo && <button type="button" onClick={() => notice.undo && send(notice.undo)} className="ml-2 font-medium text-primary-text hover:underline">Undo</button>}</span>
          <button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button>
        </div>
      )}
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {data.lists.map((l) => (
          <Panel key={l.key} title={l.label}>
            <ul className="grid gap-1.5">
              {l.items.map((it) => <Line key={it.id} name={it.name} email={it.email} busy={busy} onDelete={() => send(`/settings/contacts/${l.key}/${it.id}/delete`, {}, `Delete ${it.name}?`)} />)}
              {l.items.length === 0 && <li className="text-[13px] text-muted-foreground">None yet.</li>}
            </ul>
            <AddRow withEmail={l.has_email} placeholder="Name" button="Add" busy={busy} onSubmit={(f) => send(`/settings/contacts/${l.key}/add`, f)} />
          </Panel>
        ))}
        <Panel title="Partners">
          <div className="grid gap-4">
            {data.partners.map((p) => (
              <div key={p.id} className="border-b border-border pb-3 last:border-0 last:pb-0">
                <div className="flex items-center gap-2 text-[13px]">
                  <span className="flex-1 font-medium">{p.name}</span>
                  <button type="button" disabled={busy} onClick={() => send(`/settings/contacts/partners/${p.id}/delete`, {}, `Delete partner ${p.name}? Its account managers go too.`)} aria-label={`Delete partner ${p.name}`} className="text-muted-foreground hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
                <ul className="mt-1.5 grid gap-1.5 pl-3">
                  {p.managers.map((m) => <Line key={m.id} name={m.name} email={m.email} busy={busy} onDelete={() => send(`/settings/contacts/partner-managers/${m.id}/delete`, {}, `Delete ${m.name}?`)} />)}
                  {p.managers.length === 0 && <li className="text-[12.5px] text-muted-foreground">No account managers yet.</li>}
                </ul>
                <div className="pl-3"><AddRow withEmail placeholder="Account manager name" button="Add account manager" busy={busy} onSubmit={(f) => send(`/settings/contacts/partners/${p.id}/managers/add`, f)} /></div>
              </div>
            ))}
            {data.partners.length === 0 && <p className="text-[13px] text-muted-foreground">No partners yet.</p>}
          </div>
          <AddRow withEmail={false} placeholder="Partner name" button="Add partner" busy={busy} onSubmit={(f) => send("/settings/contacts/partners/add", f)} />
        </Panel>
      </div>
    </div>
  )
}
