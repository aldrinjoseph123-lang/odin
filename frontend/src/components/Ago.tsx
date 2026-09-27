import { localDateTime, timeAgo } from "@/lib/format"

// A relative time with the exact moment on hover, as a real <time> element.
export function Ago({ iso, className }: { iso: string; className?: string }) {
  return <time dateTime={iso.endsWith("Z") ? iso : `${iso}Z`} title={localDateTime(iso)} className={className}>{timeAgo(iso)}</time>
}
