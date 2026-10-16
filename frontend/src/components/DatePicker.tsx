import { useState } from "react"
import { CalendarDays } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { datePresets } from "@/lib/datePresets"
import { fmtDate, localToday } from "@/lib/format"
import { cn } from "@/lib/utils"

// Odin's one date field (9 Oct 2026, the user's call): a button that shows the
// date in the workspace format and opens the shadcn Calendar, weeks starting on
// Monday. Values stay "YYYY-MM-DD" strings ("" for none), as the API expects.
// `name` adds a hidden input so a plain form post (FormData) still carries it.
const parse = (v: string) => { const [y, m, d] = v.split("-").map(Number); return y ? new Date(y, m - 1, d) : undefined }

export function DatePicker({ value, onChange, label, placeholder = "Pick a date", disabled, clearable = true, min, max, name, className, autoOpen, onClose }: {
  value: string; onChange: (v: string) => void; label: string; placeholder?: string; disabled?: boolean; clearable?: boolean
  min?: string; max?: string; name?: string; className?: string; autoOpen?: boolean; onClose?: () => void
}) {
  const [open, setOpen] = useState(!!autoOpen)
  const selected = value ? parse(value) : undefined
  const pick = (v: string) => { onChange(v); setOpen(false); onClose?.() }
  return (
    <Popover open={open && !disabled} onOpenChange={(o) => { if (disabled) return; setOpen(o); if (!o) onClose?.() }}>
      <PopoverTrigger render={<Button type="button" variant="outline" disabled={disabled} />} aria-label={`${label}: ${value ? fmtDate(value) : "not set"}`} data-value={value}
        className={cn("min-w-0 justify-start gap-2 text-left text-[13px] font-normal", className)}>
        <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className={cn("truncate", !value && "text-muted-foreground")}>{value ? fmtDate(value) : placeholder}</span>
      </PopoverTrigger>
      {name && <input type="hidden" name={name} value={value} />}
      <PopoverContent align="start" className="w-auto gap-0 p-0">
        <Calendar mode="single" selected={selected} defaultMonth={selected} captionLayout="dropdown"
          startMonth={new Date(2000, 0)} endMonth={new Date(2100, 11)}
          disabled={[...(min ? [{ before: parse(min)! }] : []), ...(max ? [{ after: parse(max)! }] : [])]}
          onSelect={(d) => d && pick(localToday(d))} autoFocus />
        <div className="flex items-center justify-between gap-2 border-t border-border p-2">
          <span className="flex flex-wrap gap-1">
            <button type="button" className="rounded-md px-2 py-1 text-[13px] hover:bg-muted" onClick={() => pick(localToday())}>Today</button>
            {/* quick picks from today (advice B4); one outside min/max is left out */}
            {datePresets().filter((p) => (!min || p.value >= min) && (!max || p.value <= max)).map((p) => (
              <button key={p.label} type="button" className="rounded-md px-2 py-1 text-[13px] hover:bg-muted" onClick={() => pick(p.value)}>{p.label}</button>
            ))}
          </span>
          {clearable && value && <button type="button" className="rounded-md px-2 py-1 text-[13px] text-muted-foreground hover:bg-muted hover:text-foreground" onClick={() => pick("")}>Clear</button>}
        </div>
      </PopoverContent>
    </Popover>
  )
}
