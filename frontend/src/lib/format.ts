import type { FlowState } from "@/lib/api"

// Pure formatting shared by the flow screen and the projects list; tested in
// src/lib/format.test.ts, which is why nothing here touches the DOM.
export const initials = (name: string | null | undefined) => (name ?? "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()
export const fmtDate = (iso: string | null | undefined) => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString([], { day: "numeric", month: "short" }) : "—")
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
