import type { Recurrence } from "@/lib/api"

// A task's "Repeats" choice (services/milestones.py) as the form holds it:
// `repeat` never / weekly / fortnightly / monthly, `until` "" (no end), "stage"
// (until the stage the task is in is done) or a last day.
export type Repeat = { repeat?: Recurrence | ""; until?: string }

// the fields the task routes take; a task that does not repeat clears both
export const repeatFields = (v: Repeat) => ({ recurrence: v.repeat || null, recur_until: v.repeat ? v.until || null : null })

// "repeats every week", for a task's row
export const EVERY: Record<Recurrence, string> = { weekly: "every week", fortnightly: "every two weeks", monthly: "every month" }
