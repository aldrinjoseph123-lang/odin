import type { FlowState } from "@/lib/api"

// Pure formatting shared by the flow screen and the projects list; tested in
// src/lib/format.test.ts, which is why nothing here touches the DOM.
export const initials = (name: string | null | undefined) => (name ?? "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()
// The workspace date format (Settings → General), set once the session loads.
export type DateFormat = "d MMM yyyy" | "yyyy-MM-dd" | "dd/MM/yyyy" | "MM/dd/yyyy"
let dateFormat: DateFormat = "d MMM yyyy"
export const setDateFormat = (f: DateFormat | undefined) => { if (f) dateFormat = f }
// A stored UTC timestamp or a YYYY-MM-DD date, with the year, in the
// workspace format and the reader's zone; withTime adds the local hh:mm.
export function fmtWhen(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "—"
  const d = iso.length <= 10 ? new Date(`${iso}T00:00:00`) : new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  const y = String(d.getFullYear()), m = String(d.getMonth() + 1).padStart(2, "0"), day = String(d.getDate()).padStart(2, "0")
  const date = dateFormat === "yyyy-MM-dd" ? `${y}-${m}-${day}` : dateFormat === "dd/MM/yyyy" ? `${day}/${m}/${y}`
    : dateFormat === "MM/dd/yyyy" ? `${m}/${day}/${y}` : d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })
  return withTime ? `${date}, ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : date
}

// A calendar date (YYYY-MM-DD). The default reads "27 Sep" — compact, the
// year is obvious in context; the numeric formats always carry it.
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const [y, m, d] = iso.slice(0, 10).split("-")
  if (dateFormat === "yyyy-MM-dd") return `${y}-${m}-${d}`
  if (dateFormat === "dd/MM/yyyy") return `${d}/${m}/${y}`
  if (dateFormat === "MM/dd/yyyy") return `${m}/${d}/${y}`
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString([], { day: "numeric", month: "short" })
}
export const days = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n)} d`)

export const daysLate = (target: string | null) => (target ? Math.round((Date.now() - new Date(`${target}T00:00:00`).getTime()) / 864e5) : 0)
export function stateText(r: { state: FlowState; days_in_stage: number | null; over_by: number | null; target_end_date: string | null }) {
  if (r.state === "overdue") return `Overdue ${daysLate(r.target_end_date)} d`
  if (r.state === "over_sla") return `${days(r.days_in_stage)} · ${Math.round(r.over_by ?? 0)} over SLA`
  if (r.state === "due_soon") return `Due ${fmtDate(r.target_end_date)}`
  return days(r.days_in_stage)
}

// Stored timestamps are naive UTC ISO strings; render in the reader's zone.
export function localDateTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString([], { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })
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
  return new Date(t).toLocaleDateString([], { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) })
}

// Whole days a YYYY-MM-DD due date is past today (0 when not late).
export function lateBy(due: string, today: string): number {
  const d = Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${due}T00:00:00Z`)) / 864e5)
  return Number.isNaN(d) ? 0 : Math.max(0, d)
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
  const head: FlowItem[] = lastDone >= 1 ? [{ kind: "done", from: 0, to: lastDone }] : statuses.slice(0, lastDone + 1).map((_, index) => ({ kind: "stage", index }))
  const rest = all.slice(lastDone + 1)
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
