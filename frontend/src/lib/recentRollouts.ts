// The rollouts a person opened last, newest first, for the palette's empty box (advice B7).
export type RecentRollout = { id: number; name: string }

export const pushRecent = (list: RecentRollout[], item: RecentRollout, max = 5): RecentRollout[] =>
  [item, ...list.filter((r) => r.id !== item.id)].slice(0, max)

// A rollout page titles itself "<name> · Odin"; its loading and missing states are not names.
export function rolloutName(title: string): string | null {
  const name = title.replace(/ · Odin$/, "").trim()
  return !name || name === "Rollout" || name === "Rollout not found" ? null : name
}
