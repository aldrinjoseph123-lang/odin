import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// The building blocks the rollout and portfolio reports share: a titled card
// that does not split across printed pages, and a plain hairline table.
export function Section({ n, title, sub, children, className }: { n?: boolean; title: string; sub?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("panel p-5 break-inside-avoid print:shadow-none", className)} aria-label={title}>
      <h2 data-n={n ? "" : undefined} className="mb-3 text-[14px] font-semibold">{title}{sub && <span className="ml-2 text-[12.5px] font-normal text-muted-foreground">{sub}</span>}</h2>
      {children}
    </section>
  )
}
export function Table({ head, rows, tone }: { head: string[]; rows: ReactNode[][]; tone?: (r: number, c: number) => string | undefined }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead><tr className="border-b border-border text-left text-[11.5px] text-muted-foreground">{head.map((h) => <th key={h} className="px-2 py-1.5 font-normal">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-border last:border-0">{r.map((c, j) => <td key={j} className={cn("px-2 py-1.5 align-top", tone?.(i, j))}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}
