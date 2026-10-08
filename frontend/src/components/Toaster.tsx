import { CircleAlert, CircleCheck, X } from "lucide-react"
import { dismissToast, useToasts } from "@/lib/toast"

// The toasts' one place: bottom centre, above everything, announced politely.
export function Toaster() {
  const items = useToasts()
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4">
      {items.map((t) => (
        <div key={t.id} className="pointer-events-auto flex max-w-md items-center gap-2 rounded-lg bg-foreground py-2 pl-3 pr-1 text-[13px] text-background shadow-pop animate-in fade-in slide-in-from-bottom-2 duration-200">
          {t.tone === "bad" ? <CircleAlert className="h-4 w-4 shrink-0 text-bad-line" aria-hidden /> : <CircleCheck className="h-4 w-4 shrink-0 text-ok-line" aria-hidden />}
          <span className="min-w-0">{t.text}</span>
          {t.action && <button type="button" className="ml-2 rounded-md px-2 py-1 font-medium underline-offset-2 hover:underline" onClick={() => { t.action!.run(); dismissToast(t.id) }}>{t.action.label}</button>}
          <button type="button" aria-label="Dismiss" className="rounded-md p-1 opacity-70 hover:opacity-100" onClick={() => dismissToast(t.id)}><X className="h-4 w-4" /></button>
        </div>
      ))}
    </div>
  )
}
