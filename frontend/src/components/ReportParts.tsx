import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// The building blocks the rollout and portfolio reports share: a titled card
// that does not split across printed pages, and a plain hairline table.
export function Section({ n, title, sub, children, className }: { n?: boolean; title: string; sub?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("panel min-w-0 p-5 break-inside-avoid print:shadow-none", className)} aria-label={title}>
      <h2 data-n={n ? "" : undefined} className="mb-3 text-[14px] font-semibold">{title}{sub && <span className="sr-only">, </span>}{sub && <span className="ml-2 text-[13px] font-normal text-muted-foreground">{sub}</span>}</h2>
      {children}
    </section>
  )
}
export function Table({ head, rows, tone }: { head: string[]; rows: ReactNode[][]; tone?: (r: number, c: number) => string | undefined }) {
  return (
    // Focusable so a keyboard can scroll it when it is wider than a phone.
    <div className="overflow-x-auto" tabIndex={0}>
      <table className="w-full border-collapse text-[13px]">
        <thead><tr className="border-b border-border text-left text-[12px] text-muted-foreground">{head.map((h) => <th key={h} className="px-2 py-2 font-normal">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-border last:border-0">{r.map((c, j) => <td key={j} className={cn("px-2 py-2 align-top", tone?.(i, j))}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}
