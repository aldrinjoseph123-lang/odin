// Placeholder while a page's data loads: the page's rough shape in muted
// bars, so the layout does not jump when content arrives.
export function PageSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="px-5 pt-4" role="status" aria-label="Loading">
      <div className="h-5 w-40 animate-pulse rounded-md bg-muted" />
      <div className="mt-4 grid gap-2">
        {Array.from({ length: rows }, (_, i) => <div key={i} className="h-9 animate-pulse rounded-lg bg-muted" style={{ opacity: 1 - i * 0.12 }} />)}
      </div>
    </div>
  )
}
