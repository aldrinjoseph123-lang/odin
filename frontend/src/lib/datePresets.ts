import { localToday } from "@/lib/format"

// The date picker's quick picks (advice B4): Tomorrow, Next Monday and a week
// on, counted from today on this device's calendar. Plain calendar days: the
// workspace's working-day calendar is not part of the session, so a weekend
// is not skipped here.
export function datePresets(now: Date = new Date()): { label: string; value: string }[] {
  const at = (days: number) => localToday(new Date(now.getFullYear(), now.getMonth(), now.getDate() + days))
  const untilMonday = ((8 - now.getDay()) % 7) || 7   // the Monday after today, a full week when today is one
  return [{ label: "Tomorrow", value: at(1) }, { label: "Next Monday", value: at(untilMonday) }, { label: "+1 week", value: at(7) }]
}
