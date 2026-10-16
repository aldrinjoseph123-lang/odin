import { useState } from "react"
import { Bell, BellOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ApiError, setWatch, type Watch } from "@/lib/api"
import { toast } from "@/lib/toast"

// Mute or follow one rollout (review B3). Someone on the rollout may mute it: no
// mail or Teams from it, the bell still shows it, marked muted. Staff not on it
// may follow it to hear of its stage moves, notes and alerts.
export function WatchButton({ projectId, watch }: { projectId: number; watch: Watch }) {
  const [w, setW] = useState(watch)
  const [busy, setBusy] = useState(false)
  if (!w.can) return null
  const mute = w.can === "mute"
  const label = mute ? (w.on ? "Unmute" : "Mute") : w.on ? "Unfollow" : "Follow"
  async function flip() {
    setBusy(true)
    try {
      const next = await setWatch(projectId, !w.on)
      setW(next)
      toast(mute ? (next.on ? "Muted: no mail or Teams from this rollout; the bell still shows it" : "Unmuted") : next.on ? "Following: you hear of this rollout's events" : "No longer following")
    } catch (e) { toast(e instanceof ApiError ? e.message : "That did not save", { tone: "bad" }) } finally { setBusy(false) }
  }
  return (
    <Button variant="ghost" size="sm" loading={busy} onClick={() => void flip()}
      title={mute ? "Mail and Teams from this rollout; the bell always shows it" : "Hear of this rollout's stage moves, notes and alerts"}>
      {mute && w.on ? <BellOff className="h-3.5 w-3.5" aria-hidden /> : <Bell className="h-3.5 w-3.5" aria-hidden />}{label}
    </Button>
  )
}
