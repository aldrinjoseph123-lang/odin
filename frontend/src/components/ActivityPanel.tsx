import { Clock } from "lucide-react"
import { PanelTitle } from "@/components/PanelTitle"
import { Ago } from "@/components/Ago"
import type { Activity } from "@/lib/api"
import { fmtDate, minutesText } from "@/lib/format"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

// Time on Odin: active minutes (open, visible and in use; idle time never
// counts), as three totals and a 30-day strip, with last seen and last sign-in.
export function ActivityPanel({ a, note, n = false }: { a: Activity; note?: string; n?: boolean }) {
  const max = Math.max(1, ...a.days.map((d) => d.minutes))
  const tiles = [{ label: "Today", value: a.today }, { label: "Last 7 days", value: a.week }, { label: "Last 30 days", value: a.month }]
  return (
    <section className="panel p-4" aria-label="Time on Odin">
      {/* numbered only where its page numbers its panels (Account), not on a person's page */}
      <PanelTitle n={n} icon={<Clock className="h-3.5 w-3.5" aria-hidden />} hint="active minutes only">Time on Odin</PanelTitle>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl bg-muted/50 p-3">
            <div className="text-[12px] text-muted-foreground">{t.label}</div>
            <div className="mt-1 whitespace-nowrap text-[17px] font-semibold sm:text-[24px] leading-none tracking-tight tabular-nums">{minutesText(t.value)}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex h-20 items-end gap-1" role="img" aria-label={`Active minutes per day, last 30 days: ${minutesText(a.month)} in total`}>
        {a.days.map((d) => (
          <Tooltip key={d.day}>
            <TooltipTrigger render={<span />} className="relative flex h-full min-w-0 flex-1 items-end">
              <span className="w-full rounded-t-[3px] bg-nav-fg/60" style={{ height: d.minutes ? `max(3px, ${(d.minutes / max) * 100}%)` : 1, opacity: d.minutes ? 1 : 0.25 }} />
            </TooltipTrigger>
            <TooltipContent>{fmtDate(d.day)}: {minutesText(d.minutes)}</TooltipContent>
          </Tooltip>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground"><span>{fmtDate(a.days[0]?.day)}</span><span>today</span></div>
      <p className="mt-3 text-[13px] text-muted-foreground">
        Last seen {a.last_seen_at ? <Ago iso={a.last_seen_at} /> : "never"} · last sign-in {a.last_login_at ? <Ago iso={a.last_login_at} /> : "never"}
      </p>
      {note && <p className="mt-1 text-[12px] text-muted-foreground">{note}</p>}
    </section>
  )
}
