import { useEffect, useId, useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"

// Odin by Protect24x7 — the brand in one file. See docs/BRAND.md.
// Red lives here and on brand surfaces only; inside the app red means trouble.

export const TAGLINE = "Every project. On watch."

// The raven: Huginn and Muninn flew out each morning and told Odin what they saw.
export const RAVEN = "M3 29 L4.5 17 L8 10.5 L14 6.5 L20 6.5 L24 9 L31 16 L23 15.8 L20 18 L20.5 21 L18 20.6 L18.5 24 L16 23.4 L16.5 26.8 L14 26 L14 29 Z"
export const RAVEN_EYE = "M16.8 9.6 L20 9.6 L18.4 12.2 Z"

export function RavenMark({ className, label }: { className?: string; label?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("h-7 w-7 shrink-0", className)} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <rect x=".5" y=".5" width="31" height="31" rx="3" fill="var(--brand-ink)" stroke="var(--brand-edge)" />
      <path d={RAVEN} fill="var(--brand-paper)" />
      <path d={RAVEN_EYE} fill="var(--brand-red)" />
    </svg>
  )
}

// ODIN drawn as chamfered letters, the O struck through in red: Ø, a Norse
// letter and the parent's "24/7" slash at once. Letters take currentColor.
export function Wordmark({ className }: { className?: string }) {
  const mask = useId()
  return (
    <svg viewBox="0 -4 71 32" className={cn("h-4 w-auto", className)} role="img" aria-label="Odin">
      <defs>
        <mask id={mask}><rect x="-5" y="-5" width="90" height="40" fill="#fff" /><path d="M-0.8 27 L6.3 27 L18.8 -3 L11.7 -3 Z" fill="#000" /></mask>
      </defs>
      <path fill="currentColor" fillRule="evenodd" mask={`url(#${mask})`} d="M5 0 H13 L18 5 V19 L13 24 H5 L0 19 V5 Z M6.5 4.5 H11.5 L13.5 6.5 V17.5 L11.5 19.5 H6.5 L4.5 17.5 V6.5 Z" />
      <path fill="var(--brand-red)" d="M1 27 L4.5 27 L17 -3 L13.5 -3 Z" />
      <path fill="currentColor" fillRule="evenodd" d="M22 0 H35 L40 5 V19 L35 24 H22 Z M26.5 4.5 H33 L35.5 7 V17 L33 19.5 H26.5 Z M44 0 H48.5 V24 H44 Z M52.5 24 V0 H57 L66 15 V0 H70.5 V24 H66 L57 9 V24 Z" />
    </svg>
  )
}

export function Byline({ className }: { className?: string }) {
  return <span className={cn("font-display text-[10.5px] font-semibold uppercase tracking-[.16em]", className)}>by Protect<span className="text-brand-red">24x7</span></span>
}

export function Logo({ byline, className, markClass, wordClass }: { byline?: boolean; className?: string; markClass?: string; wordClass?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <RavenMark className={markClass} />
      <span className="grid gap-1">
        <Wordmark className={wordClass} />
        {byline && <Byline className="text-current/70" />}
      </span>
    </span>
  )
}

// "01 / Section" — the numbered eyebrow borrowed from protect24x7.com.
export function Eyebrow({ n, children, className }: { n: number; children: ReactNode; className?: string }) {
  return <p className={cn("font-display text-[11px] font-semibold uppercase tracking-[.16em]", className)}><span className="text-brand-red">{String(n).padStart(2, "0")} /</span> {children}</p>
}

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 10_000); return () => clearInterval(t) }, [])
  return now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" })
}

// Sign-in, reset and email-link pages: the black brand panel beside (or,
// on a phone, above) the form. The form side follows the user's theme.
export function AuthLayout({ children }: { children: ReactNode }) {
  const clock = useClock()
  return (
    <main className="grid min-h-svh bg-background lg:grid-cols-2">
      <aside className="brand-panel flex flex-col justify-between gap-6 px-5 py-5 sm:px-8 lg:px-12 lg:py-10">
        <Logo byline markClass="h-9 w-9" wordClass="h-5" />
        <div>
          <Eyebrow n={1} className="text-brand-muted">Project lifecycle</Eyebrow>
          <p className="mt-3 font-display text-[30px] font-bold uppercase leading-[1.02] tracking-tight sm:text-[40px] lg:text-[52px]">
            Every project.<br /><span className="text-brand-red">On watch.</span>
          </p>
          <p className="mt-4 hidden max-w-sm text-[14px] leading-relaxed text-brand-muted lg:block">Every rollout, stage and deadline, from kickoff to handover. Nothing stalls unseen.</p>
        </div>
        <p className="flex items-center gap-2 font-display text-[11.5px] font-semibold uppercase tracking-[.16em] text-brand-muted">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-red" aria-hidden />
          <time>{clock}</time> · On watch
        </p>
      </aside>
      <div className="flex items-center justify-center px-4 py-10">{children}</div>
    </main>
  )
}

// Printed reports: the brand across the top of page one.
export function PrintBrand() {
  return (
    <div className="mb-6 hidden items-end justify-between border-b-2 border-foreground pb-3 print:flex">
      <Logo byline markClass="h-8 w-8" wordClass="h-[18px]" />
      <span className="font-display text-[11px] font-semibold uppercase tracking-[.16em]">{TAGLINE}</span>
    </div>
  )
}
