import type { FieldKind, FieldValue, FlowState } from "@/lib/api"

// Pure formatting shared by the flow screen and the projects list; tested in
// src/lib/format.test.ts, which is why nothing here touches the DOM.
export const initials = (name: string | null | undefined) => (name ?? "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()
// The workspace date format (Settings → General), set once the session loads.
export type DateFormat = "d MMM yyyy" | "yyyy-MM-dd" | "dd/MM/yyyy" | "MM/dd/yyyy"
let dateFormat: DateFormat = "d MMM yyyy"
export const setDateFormat = (f: DateFormat | undefined) => { if (f) dateFormat = f }
// English month names, so "d MMM yyyy" reads "1 Nov 2026" in every browser
// (a US-locale browser turned it into "Nov 1", sim L-23). Odin is English-only.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
// A stored UTC timestamp or a YYYY-MM-DD date, with the year, in the
// workspace format and the reader's zone; withTime adds the local hh:mm.
export function fmtWhen(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—"
  const d = iso.length <= 10 ? new Date(`${iso}T00:00:00`) : new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  const y = String(d.getFullYear()), m = String(d.getMonth() + 1).padStart(2, "0"), day = String(d.getDate()).padStart(2, "0")
  const date = dateFormat === "yyyy-MM-dd" ? `${y}-${m}-${day}` : dateFormat === "dd/MM/yyyy" ? `${day}/${m}/${y}`
    : dateFormat === "MM/dd/yyyy" ? `${m}/${day}/${y}` : `${d.getDate()} ${MONTHS[d.getMonth()]} ${y}`
  return withTime ? `${date}, ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : date
}

// A stored timestamp (naive UTC unless it says otherwise) as a Date.
export const parseStamp = (iso: string) => new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)

// A calendar date (YYYY-MM-DD). The default reads "27 Sep" — compact, the
// year is obvious in context; the numeric formats always carry it. A full
// timestamp is first moved to the reader's day: 00:30 in Dubai is not yesterday.
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const stamp = iso.length > 10 ? parseStamp(iso) : null
  const ymd = stamp && !Number.isNaN(stamp.getTime()) ? localToday(stamp) : iso.slice(0, 10)
  const [y, m, d] = ymd.split("-")
  if (dateFormat === "yyyy-MM-dd") return `${y}-${m}-${d}`
  if (dateFormat === "dd/MM/yyyy") return `${d}/${m}/${y}`
  if (dateFormat === "MM/dd/yyyy") return `${m}/${d}/${y}`
  return shortDay(ymd)
}
// "27 Sep" whatever the workspace format: for tiles too narrow for a numeric date.
export const shortDay = (iso: string) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`
// A date for something that lives longer than a season (a token's expiry): the year too when it is not this one,
// so "16 Oct" is never read as the coming October. The numeric formats always carry it.
export function fmtDateY(iso: string | null | undefined): string {
  const day = fmtDate(iso)
  return iso && dateFormat === "d MMM yyyy" && iso.slice(0, 4) !== localToday().slice(0, 4) ? `${day} ${iso.slice(0, 4)}` : day
}
// "Sep" from "2026-09" or "2026-09-27"
export const monthName = (iso: string) => MONTHS[Number(iso.slice(5, 7)) - 1]
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
// "Mon" for a YYYY-MM-DD date (the date itself, not shifted by the reader's zone)
export const weekday = (iso: string) => WEEKDAYS[new Date(`${iso.slice(0, 10)}T00:00:00Z`).getUTCDay()]
export const days = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n)} d`)

// whole calendar days past the target, as the timeline and dashboard count them (never rounded from the clock, sim L-9)
export const daysLate = (target: string | null) => (target ? lateBy(target, localToday()) : 0)
// The reason behind a rollout's health word (lib/state.ts): "overdue 4 d",
// "6 d over SLA", "due 30 Nov"; on track, its days in the stage.
export function stateText(r: { state: FlowState; days_in_stage: number | null; over_by: number | null; target_end_date: string | null }) {
  if (r.state === "overdue") return `overdue ${daysLate(r.target_end_date)} d`
  if (r.state === "over_sla") return r.over_by == null ? "over SLA" : `${Math.round(r.over_by)} d over SLA`
  if (r.state === "due_soon") return `due ${fmtDate(r.target_end_date)}`
  return days(r.days_in_stage)
}

// Stored timestamps are naive UTC ISO strings; render in the reader's zone.
export function localDateTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  // the workspace date format, day first, never the browser's locale ("Sep 24" beside "24 Sep": critique 10 Oct)
  const t = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
  const day = fmtDate(localToday(d))   // numeric formats already carry the year
  return `${dateFormat === "d MMM yyyy" ? `${day} ${d.getFullYear()}` : day}, ${t}`
}

// A saved report is plain text with "# " headings and "- " items; the server
// hands it over as [kind, text] pairs. Consecutive items become one list.
export type ReportBlock = ["h" | "li" | "p", string]
export type ReportGroup = { kind: "h" | "p"; text: string } | { kind: "ul"; items: string[] }
export function groupBlocks(blocks: ReportBlock[]): ReportGroup[] {
  const out: ReportGroup[] = []
  for (const [kind, text] of blocks) {
    const last = out[out.length - 1]
    if (kind === "li") {
      if (last?.kind === "ul") last.items.push(text); else out.push({ kind: "ul", items: [text] })
    } else out.push({ kind, text })
  }
  return out
}

// Which filter chip is lit on the projects list, from the URL's parameters.
export function activeProjectsView(get: (k: string) => string | null): string {
  if (get("view")) return get("view")!
  if (get("closed") === "1") return "closed"
  if (get("stage") || get("delivery_mode")) return ""
  return "active"
}

// "3 h ago" for recent moments, a date beyond a week. Stored times are naive UTC.
export function timeAgo(iso: string, now: number = Date.now()): string {
  const t = new Date(iso.endsWith("Z") ? iso : `${iso}Z`).getTime()
  if (Number.isNaN(t)) return iso
  const s = Math.round((now - t) / 1000)
  if (s < 45) return "just now"
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  const d = Math.round(h / 24)
  if (d === 1) return "yesterday"
  if (d < 7) return `${d} d ago`
  const sameYear = new Date(t).getFullYear() === new Date(now).getFullYear()
  const day = fmtDate(localToday(new Date(t)))   // the workspace format, day first
  return sameYear || dateFormat !== "d MMM yyyy" ? day : `${day} ${new Date(t).getFullYear()}`
}

// Whole days a YYYY-MM-DD due date is past today (0 when not late).
export function lateBy(due: string, today: string): number {
  const d = Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${due}T00:00:00Z`)) / 864e5)
  return Number.isNaN(d) ? 0 : Math.max(0, d)
}

// How a late forecast reads (review P2-51): nothing when it meets the target
// or there is no target, amber while the target date is still ahead, red only
// once the target itself has passed. One rule for the Plan panel and both reports.
export function forecastTone(vsTargetDays: number | null | undefined, target: string | null | undefined, today: string): "ok" | "warn" | "bad" {
  if (vsTargetDays == null || vsTargetDays <= 0) return "ok"
  return target && today > target ? "bad" : "warn"
}

// "Next up": the current stage's work first, then the earliest due date,
// undated last; ties keep the list's own order.
export function nextUp<T extends { stage: string; due_date: string | null }>(open: T[], stage: string): T | undefined {
  return open
    .map((t, i) => ({ t, i }))
    .sort((a, b) => Number(b.t.stage === stage) - Number(a.t.stage === stage)
      || (a.t.due_date ?? "9999").localeCompare(b.t.due_date ?? "9999") || a.i - b.i)[0]?.t
}

// One shared column order for many projects' stage lists, so the same stage
// sits in the same column on every row. Each list keeps its own order; a stage
// only one project has goes right after the stage it follows there. The first
// list seen wins a disagreement about order.
export function stageColumns(lists: string[][]): string[] {
  const cols: string[] = []
  for (const list of lists) {
    let at = -1
    for (const name of list) {
      const found = cols.indexOf(name)
      if (found > at) { at = found; continue }
      if (found === -1) { cols.splice(at + 1, 0, name); at += 1 }
    }
  }
  return cols
}

// Fitting a flowchart into `capacity` columns: stages stay one per column while
// they fit. Past that, the finished stages fold into one "done" node; if that
// is still too many, stages after the current one's next few fold into one
// "later" node, and the last stage always keeps its own column so the flow
// visibly ends. Indexes are into the stage list.
export type FlowItem = { kind: "stage"; index: number } | { kind: "done" | "later"; from: number; to: number }
export function fitStages(statuses: ("done" | "current" | "next")[], capacity: number): FlowItem[] {
  const n = statuses.length
  const all: FlowItem[] = statuses.map((_, index) => ({ kind: "stage", index }))
  if (n <= capacity) return all
  const current = Math.max(0, statuses.indexOf("current"))
  const lastDone = statuses.lastIndexOf("done")
  const rest = all.slice(lastDone + 1)
  // fold only the oldest finished stages, and only as many as needed: the chart fills its room
  if (lastDone >= 1 && rest.length + 1 <= capacity) {
    const foldTo = lastDone - (capacity - 1 - rest.length)   // ≥ 1, so a fold is never a node of one
    return [{ kind: "done", from: 0, to: foldTo }, ...all.slice(foldTo + 1)]
  }
  const head: FlowItem[] = lastDone >= 1 ? [{ kind: "done", from: 0, to: lastDone }] : statuses.slice(0, lastDone + 1).map((_, index) => ({ kind: "stage", index }))
  if (head.length + rest.length <= capacity) return [...head, ...rest]
  // keep: head, current, as many next stages as fit, a "later" node, the last stage
  const room = Math.max(0, capacity - head.length - 3)
  const keepTo = Math.min(n - 2, current + room)
  const kept: FlowItem[] = []
  for (let i = current; i <= keepTo; i++) kept.push({ kind: "stage", index: i })
  const later: FlowItem[] = keepTo + 1 <= n - 2 ? [{ kind: "later", from: keepTo + 1, to: n - 2 }] : []
  return [...head, ...kept, ...later, { kind: "stage", index: n - 1 }]
}

// ---- the dashboard's timeline and deltas ------------------------------------
export const dayOf = (iso: string) => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`)

// One axis for every rollout: the earliest to the latest of every start and
// target (an overdue target sits before its start), and at least a week either
// side of today so the marker never sits on an edge.
export function timelineDomain(rows: { start_date: string; target_end_date: string | null }[], today: string): { t0: number; t1: number } {
  const now = dayOf(today)
  const starts = rows.map((r) => dayOf(r.start_date)).filter((t) => !Number.isNaN(t))
  const ends = rows.map((r) => (r.target_end_date ? dayOf(r.target_end_date) : NaN)).filter((t) => !Number.isNaN(t))
  return { t0: Math.min(now - 7 * 864e5, ...starts, ...ends), t1: Math.max(now + 7 * 864e5, ...starts, ...ends) }
}

// The first of each month inside the domain, thinned to at most `max` ticks.
export function monthTicks(t0: number, t1: number, max = 8): { t: number; label: string }[] {
  const out: { t: number; label: string }[] = []
  const d = new Date(t0)
  d.setUTCHours(0, 0, 0, 0); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + 1)
  while (d.getTime() < t1) {
    out.push({ t: d.getTime(), label: d.toLocaleDateString([], { month: "short", timeZone: "UTC", ...(d.getUTCMonth() === 0 ? { year: "numeric" } : {}) }) })
    d.setUTCMonth(d.getUTCMonth() + 1)
  }
  const step = Math.ceil(out.length / Math.max(1, max))
  return out.filter((_, i) => i % step === 0)
}

// "+2", "−1" or "no change" against an older count; "" when there is no history.
export function deltaText(now: number, before: number | null | undefined): string {
  if (before == null) return ""
  const d = now - before
  return d === 0 ? "no change" : d > 0 ? `+${d}` : `−${-d}`
}

// The flow list, grouped by stage, client or owner. Rows arrive worst first,
// so a group's place is its worst row's place and each group keeps that order.
export type FlowGroupBy = "stage" | "client" | "owner"
export function groupRows<T extends { stage: string; client: string; owner_name: string; state: FlowState }>(rows: T[], by: FlowGroupBy): { key: string; rows: T[] }[] {
  const groups = new Map<string, T[]>()
  for (const r of rows) {
    const key = (by === "stage" ? r.stage : by === "client" ? r.client : r.owner_name) || "—"
    groups.set(key, [...(groups.get(key) ?? []), r])
  }
  return [...groups].map(([key, rows]) => ({ key, rows }))
}

// ---- the calendar view --------------------------------------------------------
// "YYYY-MM" shifted by n months.
export function addMonths(month: string, n: number): string {
  const [y, m] = month.split("-").map(Number)
  const d = new Date(Date.UTC(y, m - 1 + n, 1))
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`
}
export const monthTitle = (month: string) => new Date(`${month}-01T00:00:00Z`).toLocaleDateString([], { month: "long", year: "numeric", timeZone: "UTC" })

// Six Monday-first weeks covering the month, as ISO days.
export function monthGrid(month: string): string[][] {
  const first = new Date(`${month}-01T00:00:00Z`)
  const start = new Date(first); start.setUTCDate(1 - ((first.getUTCDay() + 6) % 7))
  const weeks: string[][] = []
  for (let w = 0; w < 6; w++) {
    weeks.push(Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setUTCDate(start.getUTCDate() + w * 7 + i); return d.toISOString().slice(0, 10) }))
  }
  return weeks
}

// Rollout spans laid over one week: each span that touches the week becomes
// a segment with a column range and a lane (first free lane wins, longest
// spans first); past `lanes` the rest are counted per day in `overflow`.
export type Span = { id: number; name: string; client: string; stage: string; start_date: string; target_end_date: string | null; state: FlowState }
export type Segment = Span & { startCol: number; cols: number; lane: number; startsHere: boolean; endsHere: boolean }
export function laneSpans(spans: Span[], week: string[], lanes: number): { segments: Segment[]; overflow: Map<string, number> } {
  const first = week[0], last = week[6]
  const touching = spans
    .filter((s) => s.start_date <= last && (s.target_end_date ?? "9999") >= first)
    .map((s) => {
      const from = s.start_date < first ? first : s.start_date
      const end = s.target_end_date ?? last
      const to = end > last ? last : end
      const startCol = week.indexOf(from), endCol = week.indexOf(to)
      return { ...s, startCol, cols: endCol - startCol + 1, lane: -1, startsHere: s.start_date >= first, endsHere: s.target_end_date != null && end <= last }
    })
    .filter((s) => s.startCol >= 0 && s.cols > 0)
    .sort((a, b) => b.cols - a.cols || a.startCol - b.startCol || a.name.localeCompare(b.name))
  const taken: boolean[][] = []
  const segments: Segment[] = []
  const overflow = new Map<string, number>()
  for (const s of touching) {
    let lane = 0
    while (lane < lanes && week.slice(s.startCol, s.startCol + s.cols).some((_, i) => taken[lane]?.[s.startCol + i])) lane++
    if (lane >= lanes) {
      for (let c = s.startCol; c < s.startCol + s.cols; c++) overflow.set(week[c], (overflow.get(week[c]) ?? 0) + 1)
      continue
    }
    taken[lane] ??= []
    for (let c = s.startCol; c < s.startCol + s.cols; c++) taken[lane][c] = true
    segments.push({ ...s, lane })
  }
  return { segments, overflow }
}

// Where a sign-off stands, in words (services/signoff.py statuses).
export function signoffText(status: string | null | undefined): string {
  switch (status) {
    case "sent": return "Sent, waiting for the customer's signature"
    case "signed": return "Signed by the customer, waiting for our countersignature"
    case "countersigned": return "Signed by both sides"
    case "uploaded": return "Signed on paper; the copy is on file"
    case "waived": return "Waived by an admin"
    case "rejected": return "Not accepted; send a new version"
    case "withdrawn": return "Withdrawn; send a new version"
    default: return "Not sent yet"
  }
}

// A textarea's lines as a list: trimmed, blanks dropped.
export const toLines = (text: string): string[] => text.split("\n").map((x) => x.trim()).filter(Boolean)

// Today as YYYY-MM-DD on this device's calendar (toISOString is UTC: 01:30 in Dubai would still be yesterday).
export function localToday(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0")
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`
}

// Activity: ping only while the page is visible and was used in the last five minutes.
// idleMinutes comes from the workspace policy; 0 means time tracking is off
export const shouldPing = (now: number, lastInput: number, visible: boolean, idleMinutes = 5) => idleMinutes > 0 && visible && now - lastInput < idleMinutes * 60_000

// Minutes as "3 h 20 min", "45 min", "0 min".
export function minutesText(m: number): string {
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60), r = m % 60
  return r ? `${h} h ${r} min` : `${h} h`
}

// A document template's {placeholders} (services/doc_templates.fill): known ones filled, others left as typed.
// {client}, {project}… and {field:Name} (a custom field), as services/doc_templates.fill reads them
export const fillPlaceholders = (text: string, values: Record<string, string>) => text.replace(/\{(\w+|field:[^{}\n]{1,60})\}/g, (m, k: string) => (k in values ? values[k] : m))

// Who besides the person can see their time on Odin (policy activity_roles)
export function viewersText(roles: string[]) {
  if (!roles.length) return "Only you can see these figures."
  const names = roles.map((r) => `${r}s`)
  const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names[0]
  return `${list} can also see them on your People page.`
}

// A long, newest-first list read in chunks (UI/UX plan 3.1). A stored naive-UTC
// timestamp's local calendar day: "Today", "Yesterday", or the date.
export function dayBucket(iso: string, now: Date = new Date()): string {
  const d = new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10)
  const day = localToday(d), today = localToday(now)
  if (day === today) return "Today"
  if (day === localToday(new Date(now.getTime() - 864e5))) return "Yesterday"
  return fmtWhen(iso)
}

// A plain reminder about what waits on the customer, for when no AI draft is
// at hand: the person copies it into their own mail. Odin sends nothing.
export type Waiting = { what: string; since?: string; days_waiting?: number; due?: string; days_overdue?: number }
export function reminderText(waiting: Waiting[], name?: string | null): string {
  const line = (w: Waiting) => `- ${w.what}${w.days_waiting != null ? ` (asked ${w.since}, ${w.days_waiting} d waiting)` : w.due ? ` (due ${w.due}, ${w.days_overdue ?? 0} d overdue)` : ""}`
  return [`Hello${name ? ` ${name}` : ""},`, "", "A short reminder: to keep the rollout moving we are waiting on the following from your side:",
    ...waiting.map(line), "", "Could you let us know when we can expect them? Thank you."].join("\n")
}


// An audit log code read as words: "login_success" → "Login success",
// "AI_force" → "AI force". Words already in capitals (AI, MFA, API) stay so.
export function actionText(code: string | null | undefined): string {
  const words = (code ?? "").split(/[_\s]+/).filter(Boolean).map((w) => (w.length > 1 && w === w.toUpperCase() ? w : w.toLowerCase()))
  if (!words.length) return ""
  return [words[0][0].toUpperCase() + words[0].slice(1), ...words.slice(1)].join(" ")
}

// Settings → AI: a status nobody has checked lately is not a status. Stale when
// the scheduler is not running, the server says so, or the last heartbeat is
// over 15 minutes old (three missed beats at the default 5).
export function aiStale(s: { state: string; checked_at?: string; stale?: boolean }, schedulerAlive: boolean, now = Date.now()): boolean {
  if (s.state === "off" || s.state === "unknown") return false
  return !schedulerAlive || !!s.stale || !s.checked_at || now - parseStamp(s.checked_at).getTime() > 15 * 60_000
}

// An AI draft's progress (the model does not stream): how far through its
// usual time it is, as a percentage that never reaches 100 before the answer,
// and the words under the bar. Queued: no percentage (the bar is indeterminate).
export function aiProgress(job: { status: string; progress?: { ahead: number; started_at: string | null; expected_s: number } | null }, now: number = Date.now()):
  { pct: number | null; text: string } {
  const p = job.progress
  if (job.status === "queued" || !p?.started_at) {
    const ahead = p?.ahead ?? 0
    return { pct: null, text: ahead > 0 ? `Waiting for the AI server · ${ahead} ahead` : "Starting…" }
  }
  const started = Date.parse(/Z$|[+-]\d\d:\d\d$/.test(p.started_at) ? p.started_at : `${p.started_at}Z`)
  const elapsed = Math.max(0, (now - started) / 1000), expected = Math.max(p.expected_s, 1)
  if (elapsed <= expected) {
    const left = Math.ceil(expected - elapsed)
    return { pct: Math.min(95, (elapsed / expected) * 95), text: left > 60 ? `Writing… about ${Math.round(left / 60)} min left` : `Writing… about ${left} s left` }
  }
  // past the usual time: creep towards 99, and say so honestly
  return { pct: 95 + 4 * (1 - Math.exp(-(elapsed - expected) / expected)), text: `Taking longer than usual · ${Math.round(elapsed)} s so far` }
}

// The project form's product list: the chosen vendor's products plus those
// with no vendor (all of them when no vendor is chosen). A project's current
// product stays listed even if it now belongs elsewhere, so an edit never drops it.
export function productsFor(products: { name: string; vendor: string }[], vendor: string, current = ""): string[] {
  const names = products.filter((p) => !vendor || !p.vendor || p.vendor === vendor).map((p) => p.name)
  return current && !names.includes(current) ? [current, ...names] : names
}

// "1 task", "3 tasks": the count and its noun (pass `many` for an irregular one)
export const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`

// The project timeline's one line in words: "Started 9 Oct · day 1 · no target
// date" / "… · target 30 Oct, 21 days left" / "… · target 2 Oct, 7 days late".
// A start still ahead reads "Starts 1 Nov, in 22 days"; a closed rollout has
// no days left to count (sim L-13). Calendar days (gaps between dates stay calendar days).
export function timelineSummary(start: string, today: string, target?: string | null, closed = false): string {
  const n = (k: number) => plural(k, "day")
  const ahead = lateBy(today, start)
  const head = ahead ? `Starts ${fmtDate(start)}, in ${n(ahead)}` : `Started ${start === today ? "today" : fmtDate(start)} · day ${lateBy(start, today) + 1}`
  if (closed) return `${head.replace(/ · day \d+$/, "")} · closed`
  if (!target) return `${head} · no target date`
  const left = lateBy(today, target), late = lateBy(target, today)
  const when = late ? `${n(late)} late` : left ? `${n(left)} left` : "due today"
  return `${head} · target ${fmtDate(target)}, ${when}`
}

// A "YYYY-MM-DD" that is a real day (31 Feb is not) / a "YYYY-MM" month: the calendar's address bar
// is the person's to edit, so what it carries is checked before it is used.
export const isDay = (v: string | null): v is string => {
  if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false
  const t = Date.parse(`${v}T00:00:00Z`)
  return !Number.isNaN(t) && new Date(t).toISOString().slice(0, 10) === v
}
export const isMonth = (v: string | null): v is string => !!v && /^\d{4}-(0[1-9]|1[0-2])$/.test(v)

// what holds a move out of a stage (services/gates.py): "2 open tasks · Client PO missing"
export const gateText = (reasons: { text: string }[]) => reasons.map((r) => r.text).join(" · ")

// ---- custom fields (components/FieldValues) ----
// A value as a person reads it
export function fieldText(kind: FieldKind, value: FieldValue): string {
  if (value === null || value === "") return "—"
  if (kind === "yesno") return value ? "Yes" : "No"
  if (kind === "date") return fmtDate(String(value))
  if (kind === "number") return Number(value).toLocaleString("en-GB", { maximumFractionDigits: 6 })
  return String(value)
}

// A value as an input holds it: "" for none, yes / no for a yes-no
export function fieldInput(kind: FieldKind, value: FieldValue): string {
  if (value === null) return ""
  if (kind === "yesno") return value ? "yes" : "no"
  return String(value)
}

// One line of "Since you last looked" (services/dashboard._since): what happened, in words.
const RAID_WORD: Record<string, string> = { blocker: "New blocker", risk: "New risk", issue: "New issue", decision: "Decision proposed" }
export function sinceLine(a: { kind: string; who: string | null; text: string }): string {
  if (a.kind === "move") return `Moved ${a.text}${a.who ? ` by ${a.who}` : ""}`
  if (a.kind.startsWith("raid_")) return `${RAID_WORD[a.kind.slice(5)] ?? "New RAID item"}: ${a.text}`
  if (a.kind === "decided") return `Decided: ${a.text}`
  if (a.kind === "approval") return `Customer ${a.text.endsWith(" declined") ? "declined" : "approved"} ${a.text.replace(/ (approved|declined)$/, "")}${a.who ? ` (${a.who})` : ""}`
  if (a.kind === "ask") return `${a.who ?? "The customer"} finished: ${a.text}`
  return a.text
}
