import type { ReactNode } from "react"

// The settings and admin pages' one header (whole-app critique, 10 Oct 2026:
// three patterns): the title with its actions on the right, the lede under it.
export function PageHeader({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-[17px] font-semibold tracking-tight">{title}</h1>
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </div>
      {lede && <p className="mt-1 max-w-prose text-[13px] text-muted-foreground">{lede}</p>}
    </div>
  )
}
