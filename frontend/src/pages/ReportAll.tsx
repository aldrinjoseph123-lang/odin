import { useEffect, useState } from "react"
import { Printer } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { PrintBrand } from "@/components/Brand"
import { Button } from "@/components/ui/button"
import { ApiError, reportAll, type ReportAllData, type User } from "@/lib/api"
import { PageSkeleton } from "@/components/PageSkeleton"
import { fmtWhen } from "@/lib/format"

const fmt = (iso: string) => fmtWhen(iso, true)

export default function ReportAll(_props: { user: User }) {
  const [d, setD] = useState<ReportAllData | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { document.title = "All projects report · Odin"; reportAll().then(setD).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load")) }, [])
  if (error) return <div className="p-5"><Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert></div>
  if (!d) return <PageSkeleton />
  return (
    <div className="mx-auto w-full max-w-5xl px-5 pb-8 pt-4">
      <PrintBrand />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">All projects report</h1>
        <p className="text-[13px] text-muted-foreground">active projects · generated {fmt(d.generated_at)}</p>
        <Button size="sm" variant="outline" className="ml-auto print:hidden" onClick={() => window.print()}><Printer className="h-3.5 w-3.5" /> Print / save as PDF</Button>
      </div>
      <table className="mt-4 w-full border-collapse text-[13px]">
        <thead><tr className="border-b border-border text-left text-[11.5px] font-normal text-muted-foreground">{["Project", "Client", "Stage", "Owner", "Delivery mode", "Vendor", "Product", "Target end"].map((h) => <th key={h} className="px-2 py-2 font-normal">{h}</th>)}</tr></thead>
        <tbody>
          {d.rows.map((p) => (
            <tr key={p.id} className="border-b border-border last:border-0">
              <td className="px-2 py-1.5 font-medium">{p.name}</td><td className="px-2 py-1.5">{p.client}</td><td className="px-2 py-1.5">{p.stage}</td><td className="px-2 py-1.5">{p.owner_name}</td>
              <td className="px-2 py-1.5 text-muted-foreground">{p.delivery_mode}</td><td className="px-2 py-1.5 text-muted-foreground">{p.vendor_name ?? "—"}</td><td className="px-2 py-1.5 text-muted-foreground">{p.product_name ?? "—"}</td><td className="whitespace-nowrap px-2 py-1.5">{p.target_end_date ?? "—"}</td>
            </tr>
          ))}
          {d.rows.length === 0 && <tr><td colSpan={8} className="px-2 py-6 text-center text-muted-foreground">No active projects.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
