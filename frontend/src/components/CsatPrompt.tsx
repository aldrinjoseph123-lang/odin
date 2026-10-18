import { fieldArea } from "@/lib/ui"
import { cn } from "@/lib/utils"

// One question as the customer signs the sign-off (services/asks.py): how was
// the rollout, 1 to 5, and an optional comment. Optional, once per version,
// read by our team only; it never holds up the signature.

export type Csat = { rating: number | null; comment: string }

export function CsatPrompt({ value, onChange }: { value: Csat; onChange: (v: Csat) => void }) {
  return (
    <fieldset className="grid grid-cols-1 gap-2">
      <legend className="mb-1 text-[13px] font-medium">How did the rollout go? <span className="font-normal text-muted-foreground">(optional, seen by our team only)</span></legend>
      <div className="flex flex-wrap items-center gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n} className="relative">
            <input type="radio" name="csat" value={n} checked={value.rating === n} onChange={() => onChange({ ...value, rating: n })} aria-label={`${n} of 5`} className="peer sr-only" />
            <span aria-hidden className={cn("flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border text-[13px] font-medium peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring/50",
              value.rating === n ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background hover:bg-muted")}>{n}</span>
          </label>
        ))}
        <span className="ml-2 text-[12px] text-muted-foreground">1 poor · 5 excellent</span>
      </div>
      {value.rating !== null && (
        <textarea rows={2} maxLength={1000} value={value.comment} onChange={(e) => onChange({ ...value, comment: e.target.value })}
          aria-label="A comment on the rollout (optional)" placeholder="Anything you would like us to know" className={cn(fieldArea, "text-[13px]")} />
      )}
    </fieldset>
  )
}
