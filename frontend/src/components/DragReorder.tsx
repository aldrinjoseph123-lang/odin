import type { ElementType, ReactNode } from "react"
import { closestCenter, DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core"
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { GripVertical } from "lucide-react"
import { dragSteps, type Step } from "@/lib/reorder"
import { cn } from "@/lib/utils"

// Drag to reorder (advice B17). Pointer only, like the Calendar: the grip is
// out of the tab order and hidden from screen readers, because the up / down
// arrows (MoveArrows) are the keyboard way and dnd-kit's own keyboard sensor
// took Enter for a silent drag (P2-43). A drop calls onReorder with the
// one-step moves; the caller saves them through its existing move route.
export function DragReorder({ ids, onReorder, children }: { ids: number[]; onReorder: (id: number, steps: Step[]) => unknown; children: ReactNode }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))
  function end(e: DragEndEvent) {
    if (!e.over) return
    const steps = dragSteps(ids, Number(e.active.id), Number(e.over.id))
    if (steps.length) void onReorder(Number(e.active.id), steps)
  }
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={end}>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>{children}</SortableContext>
    </DndContext>
  )
}

export function DragRow({ id, as: Tag = "div", className, disabled, children }: { id: number; as?: ElementType; className?: string; disabled?: boolean; children: ReactNode }) {
  const { setNodeRef, setActivatorNodeRef, listeners, transform, transition, isDragging } = useSortable({ id, disabled })
  return (
    <Tag ref={setNodeRef} style={{ transform: CSS.Translate.toString(transform), transition }} className={cn(className, isDragging && "relative z-10 rounded-lg bg-card shadow-card")}>
      {!disabled && <span ref={setActivatorNodeRef} {...listeners} aria-hidden data-drag-handle title="Drag to reorder" className="flex h-6 w-4 shrink-0 cursor-grab touch-none items-center text-muted-foreground/60 hover:text-foreground active:cursor-grabbing"><GripVertical className="size-3.5" /></span>}
      {children}
    </Tag>
  )
}
