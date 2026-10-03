import { useEffect, useState, type FormEvent } from "react"
import { Button, buttonVariants } from "@/components/ui/button"
import { ApiError, postForm, rbac, type RbacData, type User } from "@/lib/api"
import { PageSkeleton, LoadError } from "@/components/PageSkeleton"

// "edit_project_stage" → "Edit project stage": the page speaks words, not code keys (test report UX-22)
const words = (key: string) => key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " ")

export default function Rbac(_props: { user: User }) {
  const [data, setData] = useState<RbacData | null>(null)
  const [matrix, setMatrix] = useState<RbacData["matrix"]>({})
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function load() {
    try { const d = await rbac(); setData(d); setMatrix(d.matrix); setError(null) } catch (e) { setError(e instanceof ApiError ? e.message : "Could not load permissions") }
  }
  useEffect(() => { document.title = "Role permissions · Settings · Odin"; void load() }, [])
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!data) return
    setBusy(true)
    try {
      // the route reads "<permission>::<role>" = "on"; locked cells are forced on server-side anyway
      const fields: Record<string, string> = {}
      for (const p of data.permissions) for (const r of data.roles) if (matrix[p]?.[r] || data.locked[p]?.includes(r)) fields[`${p}::${r}`] = "on"
      const reply = await postForm("/settings/rbac", fields)
      setNotice(reply.messages.join(" ") || null)
      await load()
    } catch (err) { setNotice(err instanceof ApiError ? err.message : "That did not save") } finally { setBusy(false) }
  }
  if (error) return <LoadError message={error} />
  if (!data) return <PageSkeleton />
  const dirty = JSON.stringify(matrix) !== JSON.stringify(data.matrix)
  return (
    <div className="px-5 pb-6 pt-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">Role permissions</h1>
        <p className="text-[13px] text-muted-foreground">which global role may do what; project roles narrow it further</p>
        <a href="/users" className={`ml-auto ${buttonVariants({ variant: "ghost", size: "sm" })}`}>Users</a>
      </div>
      {notice && <div className="mt-3 flex items-center justify-between rounded-md bg-muted px-3 py-1.5 text-[12.5px]" role="status"><span>{notice}</span><button type="button" className="font-medium" onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}
      <form onSubmit={submit} className="mt-3">
        <div className="overflow-auto panel">
          <table className="w-full border-collapse text-[13px]">
            <thead className="bg-card">
              <tr className="border-b border-border text-[11.5px] font-normal text-muted-foreground">
                <th className="px-3 py-2 text-left font-normal">Permission</th>
                {data.roles.map((r) => <th key={r} className="px-3 py-2 text-center font-normal">{r}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.permissions.map((p) => (
                <tr key={p} className="border-b border-border last:border-0 hover:bg-muted">
                  <td className="px-3 py-1.5 text-[13px]">{words(p)}</td>
                  {data.roles.map((r) => {
                    const locked = data.locked[p]?.includes(r)
                    return (
                      <td key={r} className="px-3 py-1.5 text-center">
                        <input type="checkbox" checked={locked || !!matrix[p]?.[r]} disabled={locked || busy} aria-label={`${words(p)}, allowed for ${r}`} className="h-3.5 w-3.5 accent-primary disabled:opacity-50"
                          onChange={(e) => setMatrix({ ...matrix, [p]: { ...matrix[p], [r]: e.target.checked } })} />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Button type="submit" size="sm" disabled={busy || !dirty}>Save permissions</Button>
          <span className="text-[11.5px] text-muted-foreground">Admin always keeps Manage settings, Manage users and every view right, so this page cannot lock everyone out.</span>
        </div>
      </form>
    </div>
  )
}
