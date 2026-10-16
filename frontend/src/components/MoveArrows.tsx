import { useEffect, useRef } from "react"
import { ArrowDown, ArrowUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { focusSoon } from "@/lib/ui"

// The up / down pair that reorders a row. Keyboard focus stays on the arrow
// that was pressed through the move (review P2-41): a busy arrow keeps focus
// (aria-disabled, not disabled), and when the move re-draws the rows and drops
// focus, it returns to the same arrow, or to the other one when this row has
// reached the end of the list. Rows must be keyed by id, never by content.
export type MoveDir = "up" | "down"
export function MoveArrows({ name, first, last, busy, onMove }: { name: string; first: boolean; last: boolean; busy?: boolean; onMove: (dir: MoveDir) => unknown }) {
  const box = useRef<HTMLSpanElement>(null)
  const edge = useRef({ first, last })
  useEffect(() => { edge.current = { first, last } })
  async function go(dir: MoveDir) {
    try { await onMove(dir) } finally {
      focusSoon(() => {
        const at = document.activeElement
        if (at && at !== document.body && !box.current?.contains(at)) return null   // the person moved on: leave them there
        const e = edge.current
        const to: MoveDir = dir === "up" ? (e.first ? "down" : "up") : (e.last ? "up" : "down")
        return box.current?.querySelector<HTMLElement>(`[data-move=${to}]`)
      })
    }
  }
  return (
    <span ref={box} className="flex shrink-0">
      <Button type="button" variant="ghost" size="icon-sm" data-move="up" aria-label={`Move ${name} up`} className="text-muted-foreground" disabled={busy || first} onClick={() => void go("up")}><ArrowUp className="size-3.5" /></Button>
      <Button type="button" variant="ghost" size="icon-sm" data-move="down" aria-label={`Move ${name} down`} className="text-muted-foreground" disabled={busy || last} onClick={() => void go("down")}><ArrowDown className="size-3.5" /></Button>
    </span>
  )
}
