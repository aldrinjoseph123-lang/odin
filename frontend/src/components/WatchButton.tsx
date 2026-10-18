import { useState } from "react"
import { Bell, BellOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { setWatch, type Watch } from "@/lib/api"
import { toast } from "@/lib/toast"
import { useAction } from "@/lib/useAction"

// Mute or follow one rollout (review B3). Someone on the rollout may mute it: no
// mail or Teams from it, the bell still shows it, marked muted. Staff not on it
// may follow it to hear of its stage moves, notes and alerts.
export function WatchButton({ projectId, watch }: { projectId: number; watch: Watch }) {
  const [w, setW] = useState(watch)
  const { busy, act } = useAction(undefined, { quiet: true })
  if (!w.can) return null
  const mute = w.can === "mute"
  const label = mute ? (w.on ? "Unmute updates" : "Mute updates") : w.on ? "Unfollow" : "Follow"
  const flip = () => act(async () => {
    const next = await setWatch(projectId, !w.on)
    setW(next)
    toast(mute ? (next.on ? "Muted: no mail or Teams from this rollout; the bell still shows it" : "Unmuted") : next.on ? "Following: you hear of this rollout's events" : "No longer following")
  })
  return (
    <Button variant="ghost" size="sm" loading={busy} onClick={() => void flip()}
      title={mute ? "Mail and Teams from this rollout; the bell always shows it" : "Hear of this rollout's stage moves, notes and alerts"}>
      {mute && w.on ? <BellOff className="h-3.5 w-3.5" aria-hidden /> : <Bell className="h-3.5 w-3.5" aria-hidden />}{label}
    </Button>
  )
}
