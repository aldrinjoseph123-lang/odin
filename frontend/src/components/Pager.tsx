import type { MouseEvent } from "react"
import { Pagination, PaginationContent, PaginationItem, PaginationNext, PaginationPrevious } from "@/components/ui/pagination"
import { cn } from "@/lib/utils"

// Previous · Page n of m · Next, on shadcn's Pagination. The links carry a
// real href (open in a new tab works); a plain click stays in the page.
export function Pager({ page, pages, href, onPage }: { page: number; pages: number; href: (n: number) => string; onPage: (n: number) => void }) {
  if (pages <= 1) return null
  const go = (n: number) => (e: MouseEvent) => { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); if (n >= 1 && n <= pages) onPage(n) }
  const off = "pointer-events-none opacity-40"
  return (
    <Pagination className="mx-0 w-auto justify-start">
      <PaginationContent>
        <PaginationItem><PaginationPrevious href={href(Math.max(1, page - 1))} onClick={go(page - 1)} aria-disabled={page <= 1} className={cn("h-8", page <= 1 && off)} /></PaginationItem>
        <PaginationItem><span className="px-2 text-[13px] tabular-nums text-muted-foreground">Page {page} of {pages}</span></PaginationItem>
        <PaginationItem><PaginationNext href={href(Math.min(pages, page + 1))} onClick={go(page + 1)} aria-disabled={page >= pages} className={cn("h-8", page >= pages && off)} /></PaginationItem>
      </PaginationContent>
    </Pagination>
  )
}
