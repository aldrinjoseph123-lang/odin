import { Fragment, useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react"
import { askConfirm } from "@/lib/confirm"
import { Link } from "react-router-dom"
import { ChevronRight, MoreHorizontal, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ApiError, contacts, postForm, type ContactItem, type ContactsData, type ProjectRef, type User } from "@/lib/api"
import { toast } from "@/lib/toast"
import { cn } from "@/lib/utils"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

// Contacts & partners (9 Oct 2026, the user's call): one tab per pick-list,
// one table per tab, each row saying where it is used. A rename carries over
// to the projects that name it (they keep names as text).
type TabKey = "account-managers" | "partners" | "vendors" | "products" | "outsourcers"
const TABS: { key: TabKey; label: string; noun: string; help: string; example: string }[] = [
  { key: "account-managers", label: "Account managers", noun: "account manager", help: "Your own colleagues who look after the customer. Picked on the project form; their email goes on the project.", example: "A colleague's name and work email" },
  { key: "partners", label: "Partners", noun: "partner", help: "Resellers or channel companies that bring a deal. Each partner has its own account managers, picked after the partner.", example: "A reseller, with the person you deal with there" },
  { key: "vendors", label: "Vendors", noun: "vendor", help: "The makers of what you deliver. Their products are listed on the Products tab.", example: "Fortinet, Microsoft" },
  { key: "products", label: "Products", noun: "product", help: "What you install or deliver. Link a product to its vendor and the project form offers it only with that vendor; products with no vendor show for every vendor.", example: "FortiGate under Fortinet" },
  { key: "outsourcers", label: "Outsourcers", noun: "outsourcer", help: "Outside firms that do the work when a project's delivery is outsourced. Their email goes on the project.", example: "A subcontractor's company name and email" },
]

// onError: show a refusal by the field (the edit dialog) instead of as a toast
type Send = (path: string, fields?: Record<string, string>, confirmText?: string, onError?: (m: string) => void) => Promise<boolean>
type Editing = { title: string; path: string; name: string; email?: string | null; vendor?: number | null; withEmail: boolean; withVendor: boolean; saveLabel: string }

const th = "px-3 py-2 text-left text-[12px] font-medium text-muted-foreground"
const td = "px-3 py-2 align-middle"

function tabFromUrl(): TabKey {
  const t = new URLSearchParams(window.location.search).get("tab")
  return TABS.some((x) => x.key === t) ? (t as TabKey) : "account-managers"
}

// "3 projects" opens the list of them; "Not used" when none name it
function UsedIn({ used, name }: { used: ProjectRef[]; name: string }) {
  if (!used.length) return <span className="text-muted-foreground">Not used</span>
  return (
    <Popover>
      <PopoverTrigger render={<button type="button" />} className="rounded-sm text-primary-text hover:underline" aria-label={`Projects that use ${name}`}>
        {used.length} project{used.length === 1 ? "" : "s"}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 gap-1 p-2">
        <p className="px-2 pb-1 text-[12px] text-muted-foreground">Projects that name {name}</p>
        <ul className="max-h-64 overflow-y-auto">
          {used.map((p) => <li key={p.id}><Link to={`/projects/${p.id}`} className="block truncate rounded-md px-2 py-1 text-[13px] hover:bg-muted">{p.name || `Project ${p.id}`}</Link></li>)}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

function RowMenu({ name, onEdit, onDelete, busy }: { name: string; onEdit: () => void; onDelete: () => void; busy: boolean }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<button type="button" />} disabled={busy} aria-label={`Actions for ${name}`}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
        <MoreHorizontal className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuItem onClick={onEdit}>Edit</DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onClick={onDelete}>Delete</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function deleteText(name: string, used: ProjectRef[], extra = "") {
  const where = used.length ? ` ${used.length} project${used.length === 1 ? "" : "s"} name it; they keep the name, but it leaves the project form's list.` : ""
  return `Delete ${name}?${where}${extra}`
}

function EditDialog({ editing, vendors, busy, send, onClose }: { editing: Editing | null; vendors: ContactItem[]; busy: boolean; send: Send; onClose: () => void }) {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [vendor, setVendor] = useState("")
  const [problem, setProblem] = useState<string | null>(null)
  useEffect(() => { if (editing) { setName(editing.name); setEmail(editing.email ?? ""); setVendor(editing.vendor ? String(editing.vendor) : ""); setProblem(null) } }, [editing])
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!editing || !name.trim()) return
    const fields: Record<string, string> = { name: name.trim() }
    if (editing.withEmail) fields.email = email.trim()
    if (editing.withVendor) fields.vendor_id = vendor
    setProblem(null)
    void send(editing.path, fields, undefined, setProblem).then((ok) => { if (ok) onClose() })
  }
  return (
    <Dialog open={!!editing} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{editing?.title}</DialogTitle>
          {editing?.name && <DialogDescription>A new name or email also changes it on every project that uses it.</DialogDescription>}
        </DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4">
          <label className="grid grid-cols-1 gap-1 text-[12px] font-medium">Name
            <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoFocus className="h-8 text-[13px]" />
          </label>
          {editing?.withEmail && (
            <label className="grid grid-cols-1 gap-1 text-[12px] font-medium">Email <span className="font-normal text-muted-foreground">optional</span>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} placeholder="name@company.com" className="h-8 text-[13px]" />
            </label>
          )}
          {editing?.withVendor && (
            <label className="grid grid-cols-1 gap-1 text-[12px] font-medium">Vendor
              <select value={vendor} onChange={(e) => setVendor(e.target.value)} className="h-8 rounded-md border border-input bg-background px-2 text-[13px]">
                <option value="">Any vendor</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
              <span className="font-normal text-muted-foreground">The project form offers this product only with this vendor.</span>
            </label>
          )}
          {problem && <p className="field-error" role="alert">{problem}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
            <Button type="submit" size="sm" loading={busy} disabled={!name.trim()}>{editing?.saveLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function Contacts(_props: { user: User }) {
  const [data, setData] = useState<ContactsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<TabKey>(tabFromUrl)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const load = useCallback(async () => {
    try { setData(await contacts()); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load contacts") }
  }, [])
  useEffect(() => { document.title = "Contacts & partners · Settings · Odin"; void load() }, [load])
  const pick = (t: TabKey) => { setTab(t); const u = new URL(window.location.href); u.searchParams.set("tab", t); window.history.replaceState(window.history.state, "", u) }

  const send: Send = async (path, fields = {}, confirmText, onError) => {
    if (confirmText && !(await askConfirm(confirmText))) return false
    setBusy(true)
    try {
      const r = await postForm(path, fields)
      if (r.messages.length) toast(r.messages.join(" "), r.undo ? { action: { label: "Undo", run: () => void send(r.undo!) } } : {})
      await load(); return true
    } catch (e) {
      const m = e instanceof ApiError ? e.message : "That did not save"
      if (onError) onError(m); else toast(m, { tone: "bad" })
      return false
    } finally { setBusy(false) }
  }
  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />

  const list = (key: string) => data.lists.find((l) => l.key === key)!
  const vendors = list("vendors").items
  const products = list("products").items
  const meta = TABS.find((t) => t.key === tab)!
  const count = (t: TabKey) => t === "partners" ? data.partners.length : list(t).items.length

  const addFor = (t: TabKey, extra: Partial<Editing> = {}): Editing => {
    const m = TABS.find((x) => x.key === t)!
    const path = t === "partners" ? "/settings/contacts/partners/add" : `/settings/contacts/${t}/add`
    return { title: `Add ${m.noun}`, path, name: "", withEmail: t === "account-managers" || t === "outsourcers", withVendor: t === "products", saveLabel: "Add", ...extra }
  }
  const editItem = (t: TabKey, it: ContactItem): Editing => ({
    ...addFor(t), title: `Edit ${it.name}`, path: `/settings/contacts/${t}/${it.id}/edit`, name: it.name, email: it.email, vendor: it.vendor_id ?? null, saveLabel: "Save",
  })
  const del = (t: TabKey, it: ContactItem) => send(`/settings/contacts/${t}/${it.id}/delete`, {}, deleteText(it.name, it.used))

  const simpleRows = (t: TabKey, items: ContactItem[], withEmail: boolean, extra?: (it: ContactItem) => ReactNode) => items.map((it) => (
    <tr key={it.id} className="border-t border-border">
      <td className={cn(td, "font-medium")}>{it.name}</td>
      {withEmail && <td className={cn(td, "text-muted-foreground")}>{it.email || "—"}</td>}
      {extra && <td className={td}>{extra(it)}</td>}
      <td className={td}><UsedIn used={it.used} name={it.name} /></td>
      <td className={cn(td, "w-10 text-right")}><RowMenu name={it.name} busy={busy} onEdit={() => setEditing(editItem(t, it))} onDelete={() => del(t, it)} /></td>
    </tr>
  ))

  const empty = (cols: number, text: string) => <tr className="border-t border-border"><td colSpan={cols} className={cn(td, "py-6 text-center text-muted-foreground")}>{text}</td></tr>

  let table
  if (tab === "account-managers" || tab === "outsourcers") {
    const items = list(tab).items
    table = (
      <table className="w-full text-[13px]">
        <thead><tr><th className={th}>Name</th><th className={th}>Email</th><th className={th}>Used in</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{items.length ? simpleRows(tab, items, true) : empty(4, `No ${meta.label.toLowerCase()} yet.`)}</tbody>
      </table>
    )
  } else if (tab === "vendors") {
    table = (
      <table className="w-full text-[13px]">
        <thead><tr><th className={th}>Vendor</th><th className={th}>Products</th><th className={th}>Used in</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{vendors.length ? simpleRows("vendors", vendors, false, (v) => {
          const n = products.filter((p) => p.vendor_id === v.id).length
          return <button type="button" className="rounded-sm text-primary-text hover:underline" onClick={() => pick("products")}>{n ? `${n} product${n === 1 ? "" : "s"}` : "None yet"}</button>
        }) : empty(4, "No vendors yet.")}</tbody>
      </table>
    )
  } else if (tab === "products") {
    const live = new Set(vendors.map((v) => v.id))
    const groups = [...vendors.map((v) => ({ id: v.id, name: v.name, items: products.filter((p) => p.vendor_id === v.id) })),
      { id: 0, name: "Any vendor", items: products.filter((p) => !p.vendor_id || !live.has(p.vendor_id)) }].filter((g) => g.items.length || g.id)
    table = (
      <table className="w-full text-[13px]">
        <thead><tr><th className={th}>Product</th><th className={th}>Used in</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>
          {groups.map((g) => (
            <Fragment key={g.id}>
              <tr className="border-t border-border bg-muted/60">
                <th scope="rowgroup" colSpan={2} className="px-3 py-1.5 text-left text-[12px] font-semibold">{g.name} <span className="font-normal text-muted-foreground">· {g.items.length || "no products yet"}</span></th>
                <td className="px-3 py-1 text-right">
                  <button type="button" disabled={busy} className="whitespace-nowrap rounded-sm text-[12px] font-medium text-primary-text hover:underline" aria-label={`Add a product under ${g.name}`}
                    onClick={() => setEditing(addFor("products", { title: g.id ? `Add a ${g.name} product` : "Add product", vendor: g.id || null }))}>+ Add</button>
                </td>
              </tr>
              {simpleRows("products", g.items, false)}
            </Fragment>
          ))}
        </tbody>
      </table>
    )
  } else {
    table = (
      <table className="w-full text-[13px]">
        <thead><tr><th className={th}>Partner</th><th className={th}>Account managers</th><th className={th}>Used in</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>
          {data.partners.length === 0 && empty(4, "No partners yet.")}
          {data.partners.map((p) => {
            const shown = !!open[p.id]
            return (
              <Fragment key={p.id}>
                <tr className="border-t border-border">
                  <td className={cn(td, "font-medium")}>
                    <button type="button" aria-expanded={shown} onClick={() => setOpen({ ...open, [p.id]: !shown })} className="inline-flex items-center gap-1 rounded-sm hover:underline">
                      <ChevronRight className={cn("h-4 w-4 text-muted-foreground transition-transform", shown && "rotate-90")} aria-hidden />{p.name}
                    </button>
                  </td>
                  <td className={cn(td, "text-muted-foreground")}>{p.managers.length || "None yet"}</td>
                  <td className={td}><UsedIn used={p.used} name={p.name} /></td>
                  <td className={cn(td, "w-10 text-right")}>
                    <RowMenu name={p.name} busy={busy}
                      onEdit={() => setEditing({ ...addFor("partners"), title: `Edit ${p.name}`, path: `/settings/contacts/partners/${p.id}/edit`, name: p.name, saveLabel: "Save" })}
                      onDelete={() => send(`/settings/contacts/partners/${p.id}/delete`, {}, deleteText(p.name, p.used, " Its account managers go too."))} />
                  </td>
                </tr>
                {shown && (
                  <tr className="bg-muted/60">
                    <td colSpan={4} className="px-3 pb-3 pt-1">
                      <ul className="grid grid-cols-1 pl-5">
                        {p.managers.map((m) => (
                          <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border py-1 last:border-0">
                            <span className="min-w-40 font-medium">{m.name}</span>
                            <span className="min-w-48 flex-1 text-muted-foreground">{m.email || "—"}</span>
                            <UsedIn used={m.used} name={m.name} />
                            <RowMenu name={m.name} busy={busy}
                              onEdit={() => setEditing({ title: `Edit ${m.name}`, path: `/settings/contacts/partner-managers/${m.id}/edit`, name: m.name, email: m.email, withEmail: true, withVendor: false, saveLabel: "Save" })}
                              onDelete={() => send(`/settings/contacts/partner-managers/${m.id}/delete`, {}, deleteText(m.name, m.used))} />
                          </li>
                        ))}
                        {p.managers.length === 0 && <li className="py-1 text-muted-foreground">No account managers yet.</li>}
                      </ul>
                      <button type="button" disabled={busy} className="ml-5 mt-2 rounded-sm text-[12px] font-medium text-primary-text hover:underline"
                        onClick={() => setEditing({ title: `Add an account manager at ${p.name}`, path: `/settings/contacts/partners/${p.id}/managers/add`, name: "", withEmail: true, withVendor: false, saveLabel: "Add" })}>
                        + Add account manager
                      </button>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    )
  }

  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Contacts & partners</h1>
        <p className="text-[13px] text-muted-foreground">the names the project form offers; a rename here updates every project that uses it</p>
      </div>
      <Tabs value={tab} onValueChange={(v) => pick(v as TabKey)} className="mt-4">
        <TabsList className="max-w-full justify-start overflow-x-auto [scrollbar-width:none]">
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key} className="h-8 flex-none px-3 text-[13px]">
              {t.label}<span className="text-[12px] tabular-nums text-muted-foreground">{count(t.key)}</span>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <section className="panel mt-4 overflow-hidden" aria-label={meta.label}>
        <div className="flex flex-wrap items-start justify-between gap-3 p-4">
          <div className="min-w-0 max-w-2xl">
            <h2 data-n className="text-[12px] font-semibold text-nav-fg">{meta.label}</h2>
            <p className="mt-1 text-[13px]">{meta.help}</p>
            <p className="mt-1 text-[12px] text-muted-foreground">For example: {meta.example}</p>
          </div>
          <Button size="sm" disabled={busy} onClick={() => setEditing(addFor(tab))}><Plus className="h-4 w-4" aria-hidden />Add {meta.noun}</Button>
        </div>
        <div className="overflow-x-auto">{table}</div>
      </section>
      <EditDialog editing={editing} vendors={vendors} busy={busy} send={send} onClose={() => setEditing(null)} />
    </div>
  )
}
