// A panel's first load: one quiet line in place of the panel (LoadFailed is its
// failure twin). The page around it carries on.
export function PanelLoading() {
  return <p className="text-[13px] text-muted-foreground" role="status">Loading…</p>
}
