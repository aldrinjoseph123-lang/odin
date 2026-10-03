import { useEffect, useId, useState, type ReactNode } from "react"
import { cn } from "@/lib/utils"

// Odin by Protect24x7 — the brand in one file. See docs/BRAND.md.
// Red lives here and on brand surfaces only; inside the app red means trouble.

const TAGLINE = "Every project. On watch."

// The raven, perched: Huginn and Muninn flew out each morning and told Odin
// what they saw. Heavy beak, flat crown, long wedge tail, red eye. 64-unit grid.
const RAVEN = {
  body: "M61 24 C56 19 52 16 47 15 C44 11.5 37 11.5 34.5 15.5 C30.5 22 24 28 19 36 L5 57 L13 58.5 L26 48.5 C31 49.5 37 47.5 41 43 C45 39 47 34.5 47.5 30.5 L50 29.5 L48.5 27.5 L50.5 25.5 Q55 25.5 61 24 Z",
  legs: "M31 48.5 L30 57.5 M36.5 46.5 L36.5 56.5",
  wing: "M37 21 C35 31 30 40 20 47",
  gape: "M50.5 25.5 L59 24.2",
  eye: "M43.5 15.5 L45.5 17.5 L43.5 19.5 L41.5 17.5 Z",
}

export function RavenMark({ className, label }: { className?: string; label?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={cn("h-7 w-7 shrink-0", className)} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <rect x="1" y="1" width="62" height="62" rx="10" fill="var(--brand-ink)" stroke="var(--brand-edge)" strokeWidth="1.5" />
      <path d={RAVEN.body} fill="var(--brand-paper)" />
      <path d={RAVEN.legs} stroke="var(--brand-paper)" strokeWidth="2.4" />
      <path d={RAVEN.wing} stroke="var(--brand-ink)" strokeWidth="2" fill="none" />
      <path d={RAVEN.gape} stroke="var(--brand-ink)" strokeWidth="1.2" />
      <path d={RAVEN.eye} fill="var(--brand-red)" />
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
        <mask id={mask}><rect x="-5" y="-5" width="90" height="40" fill="#fff" /><path d="M-0.2 26 L5.8 26 L17.8 -2 L11.8 -2 Z" fill="#000" /></mask>
      </defs>
      <path fill="currentColor" fillRule="evenodd" mask={`url(#${mask})`} d="M5 0 H13 L18 5 V19 L13 24 H5 L0 19 V5 Z M6.5 4.5 H11.5 L13.5 6.5 V17.5 L11.5 19.5 H6.5 L4.5 17.5 V6.5 Z" />
      <path fill="var(--brand-red)" d="M1.4 26 L4.4 26 L16.4 -2 L13.4 -2 Z" />
      <path fill="currentColor" fillRule="evenodd" d="M22 0 H35 L40 5 V19 L35 24 H22 Z M26.5 4.5 H33 L35.5 7 V17 L33 19.5 H26.5 Z M44 0 H48.5 V24 H44 Z M52.5 24 V0 H57 L66 15 V0 H70.5 V24 H66 L57 9 V24 Z" />
    </svg>
  )
}

export function Byline({ className }: { className?: string }) {
  return <span className={cn("font-display text-[10.5px] font-semibold uppercase tracking-[.16em]", className)}>by Protect<span className="text-brand-red-text">24x7</span></span>
}

export function Logo({ byline, className, markClass, wordClass }: { byline?: boolean; className?: string; markClass?: string; wordClass?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <RavenMark className={markClass} />
      <Wordmark className={wordClass} />
      {byline && <><span className="h-[1.1em] w-px bg-current opacity-30" aria-hidden /><Byline className="text-current/70" /></>}
    </span>
  )
}

// "01 / Section" — the numbered eyebrow borrowed from protect24x7.com.
export function Eyebrow({ n, children, className }: { n: number; children: ReactNode; className?: string }) {
  return <p className={cn("font-display text-[11px] font-semibold uppercase tracking-[.16em]", className)}><span className="text-brand-red-text">{String(n).padStart(2, "0")} /</span> {children}</p>
}

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 10_000); return () => clearInterval(t) }, [])
  return now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" })
}

// Sign-in, reset and email-link pages: the black brand panel beside the
// form from lg, a compact band above it on smaller screens (so on a phone
// the form, not the tagline, fills the first screen). The form side follows
// the user's theme and sits on the page itself, no card around it.
export function AuthLayout({ children }: { children: ReactNode }) {
  const clock = useClock()
  return (
    <main className="grid grid-cols-1 min-h-svh grid-rows-[auto_1fr] bg-background lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:grid-rows-1">
      <aside className="brand-panel flex flex-col gap-4 px-5 py-5 sm:px-8 lg:justify-between lg:gap-6 lg:px-12 lg:py-10">
        <Logo byline markClass="h-8 w-8 lg:h-9 lg:w-9" wordClass="h-[18px] lg:h-5" />
        <div>
          <Eyebrow n={1} className="hidden text-brand-muted lg:block">Project lifecycle</Eyebrow>
          <p className="font-display text-[22px] font-bold uppercase leading-[1.02] tracking-tight sm:text-[28px] lg:mt-3 lg:text-[52px]">
            Every project.<br className="hidden lg:block" /><span className="whitespace-nowrap text-brand-red"> On watch.</span>
          </p>
          <p className="mt-4 hidden max-w-sm text-[14px] leading-relaxed text-brand-muted lg:block">Every rollout, stage and deadline, from kickoff to handover. Nothing stalls unseen.</p>
        </div>
        <p className="hidden items-center gap-2 font-display text-[11.5px] font-semibold uppercase tracking-[.16em] text-brand-muted lg:flex">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-red" aria-hidden />
          <time>{clock}</time> · On watch
        </p>
      </aside>
      <div className="flex flex-col px-5 py-8 sm:px-10 lg:px-16">
        <div className="w-full max-w-[400px] sm:mx-auto lg:my-auto">{children}</div>
        <p className="mt-10 w-full max-w-[400px] text-[12.5px] text-muted-foreground sm:mx-auto lg:mt-0">Trouble signing in? Ask your Odin admin.</p>
      </div>
    </main>
  )
}

// The title block every sign-in page opens with: the page's one h1.
export function AuthHeading({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold leading-tight tracking-tight">{title}</h1>
      {children && <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">{children}</p>}
    </div>
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
