import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { whatsNew, whatsNewSeen, type WhatsNew as News } from "@/lib/api"

// "What's new in vX" (review B15): after a release, staff see what changed, once.
// A quiet card in the corner, not a dialog: it never takes the focus or blocks
// the page, and "Got it" is remembered on the server, so it does not follow the
// person to their next device.
export function WhatsNew({ staff }: { staff: boolean }) {
  const [news, setNews] = useState<News | null>(null)
  useEffect(() => {
    if (!staff) return
    whatsNew().then((n) => setNews(n.show ? n : null)).catch(() => setNews(null))   // a missing change log is nothing to say
  }, [staff])
  if (!news) return null
  return (
    <section aria-label={`What's new in Odin ${news.version}`} className="panel fixed bottom-4 left-4 z-40 grid w-80 max-w-[calc(100vw-2rem)] grid-cols-1 gap-2 p-4 shadow-pop print:hidden">
      <h2 className="flex items-center gap-2 text-[14px] font-semibold"><Sparkles className="h-4 w-4 text-primary-text" aria-hidden />What's new in v{news.version}</h2>
      {news.title && <p className="text-[13px] text-muted-foreground">{news.title}</p>}
      <ul className="grid max-h-60 list-disc grid-cols-1 gap-1 overflow-y-auto pl-4 text-[13px]">
        {news.items.map((i) => <li key={i}>{i}</li>)}
      </ul>
      <div><Button size="sm" onClick={() => { setNews(null); void whatsNewSeen().catch(() => undefined) }}>Got it</Button></div>
    </section>
  )
}
