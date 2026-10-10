import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// The one section label on record and settings pages (whole-app critique, 10 Oct
// 2026: three sizes and two colours had grown up): 12 px semibold chrome text,
// numbered "01 /" by the page's CSS counter unless `n` is false, the hint beside
// it and outside the heading so a headings list reads the title alone.
// (Overview cards — dashboard widgets, My work, a person's page — keep their 14 px card titles.)
export function PanelTitle({ children, hint, n = true, icon, id, className }: { children: ReactNode; hint?: ReactNode; n?: boolean; icon?: ReactNode; id?: string; className?: string }) {
  return (
    <div className={cn("mb-3 flex flex-wrap items-baseline gap-x-2 text-[12px]", className)}>
      <h2 id={id} data-n={n ? "" : undefined} className="flex items-center gap-2 font-semibold text-nav-fg">{icon}{children}</h2>
      {hint && <span className="text-muted-foreground">{hint}</span>}
    </div>
  )
}
