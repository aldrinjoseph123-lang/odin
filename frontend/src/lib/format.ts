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
