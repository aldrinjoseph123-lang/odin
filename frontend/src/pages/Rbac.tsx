import { useEffect, useState, type FormEvent } from "react"
import { PageHeader } from "@/components/PageHeader"
import { toast } from "@/lib/toast"
import { Button, buttonVariants } from "@/components/ui/button"
import { checkbox, th } from "@/lib/ui"
import { cn } from "@/lib/utils"
import { ApiError, postForm, rbac, type RbacData, type User } from "@/lib/api"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"
import { askConfirm } from "@/lib/confirm"

// "edit_project_stage" → "Edit project stage": the page speaks words, not code keys (test report UX-22)
const words = (key: string) => key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " ")

export default function Rbac(_props: { user: User }) {
  const [data, setData] = useState<RbacData | null>(null)
  const [matrix, setMatrix] = useState<RbacData["matrix"]>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function load() {
    try { const d = await rbac(); setData(d); setMatrix(d.matrix); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load permissions") }
  }
  useEffect(() => { document.title = "Role permissions · Settings · Odin"; void load() }, [])
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!data) return
    // the route reads "<permission>::<role>" = "on" and saves only a whole matrix (matrix=full);
    // locked cells are forced on server-side anyway
    const fields: Record<string, string> = { matrix: "full" }
    for (const p of data.permissions) for (const r of data.roles) if ((matrix[p]?.[r] || data.locked[p]?.includes(r)) && !data.forbidden?.[p]?.includes(r)) fields[`${p}::${r}`] = "on"
    // switching off more than half of what is on is refused unless confirmed (the server counts the same way)
    const on = data.permissions.flatMap((p) => data.roles.filter((r) => data.matrix[p]?.[r] && !data.locked[p]?.includes(r)).map((r) => `${p}::${r}`))
    const going = on.filter((k) => !fields[k]).length
    if (going * 2 > on.length) {
      if (!(await askConfirm(`Switch off ${going} of the ${on.length} permissions that are on? Those roles lose them at once.`))) return
      fields.confirm = "1"
    }
    setBusy(true)
    try {
      const reply = await postForm("/settings/rbac", fields)
      { const said = reply.messages.join(" "); if (said) toast(said) }
      await load()
    } catch (err) { toast(err instanceof ApiError ? err.message : "That did not save", { tone: "bad" }) } finally { setBusy(false) }
  }
  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />
  const dirty = JSON.stringify(matrix) !== JSON.stringify(data.matrix)
  return (
    <div className="px-5 pb-6 pt-4">
      <PageHeader title="Role permissions" lede="Which global role may do what; rollout roles narrow it further."
        actions={<a href="/users" className={buttonVariants({ variant: "ghost", size: "sm" })}>Users</a>} />
      <form onSubmit={submit} className="mt-3">
        <div className="overflow-auto panel">
          <table className="w-full border-collapse text-[13px]">
            <thead className="bg-card">
              <tr className="border-b border-border">
                <th className={th}>Permission</th>
                {data.roles.map((r) => <th key={r} className={cn(th, "text-center")}>{r}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.permissions.map((p) => (
                <tr key={p} className="border-b border-border last:border-0 hover:bg-muted">
                  <td className="px-3 py-2 text-[13px]">{words(p)}</td>
                  {data.roles.map((r) => {
                    const locked = data.locked[p]?.includes(r)
                    const forbidden = !!data.forbidden?.[p]?.includes(r)   // the server never grants it to this role
                    return (
                      <td key={r} className="px-3 py-2 text-center" title={forbidden ? `${r} accounts can never have this` : undefined}>
                        <input type="checkbox" checked={!forbidden && (locked || !!matrix[p]?.[r])} disabled={locked || forbidden} aria-disabled={busy || undefined} aria-label={`${words(p)}, ${forbidden ? "never" : "allowed"} for ${r}`} className={cn(checkbox, "disabled:opacity-50")}
                          onChange={(e) => { if (!busy) setMatrix({ ...matrix, [p]: { ...matrix[p], [r]: e.target.checked } }) }} />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Button type="submit" size="sm" loading={busy} disabled={!dirty}>Save permissions</Button>
          <span className="text-[12px] text-muted-foreground">Admin always keeps Manage settings, Manage users and every view right, so this page cannot lock everyone out.</span>
        </div>
      </form>
    </div>
  )
}
