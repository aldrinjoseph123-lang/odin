import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Kbd } from "@/components/ui/kbd"

// The "?" sheet (advice B6): every keyboard shortcut in one place. Keep it true to
// AppShell (⌘K, /, ?), Flow (j/k/l/→, Esc, 1–4) and submitKey (Ctrl/⌘+Enter).
const mod = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl"
const GROUPS: { title: string; rows: { keys: string[]; what: string }[] }[] = [
  { title: "Anywhere", rows: [
    { keys: [`${mod} K`], what: "Search and jump to a rollout, person, setting or page" },
    { keys: ["/"], what: "The same search, when you are not typing" },
    { keys: ["?"], what: "This sheet" },
    { keys: ["Esc"], what: "Close the search, a dialog or the open rollout" },
    { keys: [`${mod} Enter`], what: "Send what you are writing: a note, a task, a RAID item, a message, a sign-off comment" },
  ] },
  { title: "Flow", rows: [
    { keys: ["j", "↓"], what: "Next rollout in the list" },
    { keys: ["k", "↑"], what: "Previous rollout" },
    { keys: ["l", "→"], what: "Open the rollout" },
    { keys: ["1", "2", "3", "4"], what: "List, Kanban, Gantt, Calendar" },
  ] },
]

export function ShortcutSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Single keys work when you are not typing in a field. Switch /, ? and 1–4 off on your Account page (Single-key shortcuts).</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 text-[13px]">
          {GROUPS.map((g) => (
            <section key={g.title} aria-label={g.title}>
              <h3 className="mb-1 text-[12px] font-medium text-muted-foreground">{g.title}</h3>
              <dl className="grid grid-cols-1 gap-1">
                {g.rows.map((r) => (
                  <div key={r.what} className="flex items-start justify-between gap-4">
                    <dt className="flex shrink-0 gap-1">{r.keys.map((k) => <Kbd key={k}>{k}</Kbd>)}</dt>
                    <dd className="text-right text-muted-foreground">{r.what}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
