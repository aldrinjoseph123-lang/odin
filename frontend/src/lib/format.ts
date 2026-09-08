// Stored timestamps are naive UTC ISO strings; render in the reader's zone.
export function localDateTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString([], { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}
