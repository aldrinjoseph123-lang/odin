import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

// One look per job, imported, never copied (whole-app critique, 10 Oct 2026:
// six field styles, seven pills and nine toggle chips had drifted apart).

// A native select or textarea that matches <Input>: 32 px, 16 px corners, 12 px sides, 13 px text.
export const fieldAuto = "h-8 rounded-lg border border-input bg-background px-3 text-[13px] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-60"
export const field = cn(fieldAuto, "w-full")
// A list filter in a toolbar (Projects, Audit): quieter, 28 px.
export const filterSelect = "h-7 rounded-lg border border-border bg-background px-3 text-[13px] font-medium text-nav-fg hover:bg-muted"
// A small action link drawn as a pill (Open the flow, Report, PDF).
export const pill = cn(buttonVariants({ variant: "outline", size: "sm" }), "h-7 rounded-full px-3 text-[12px]")
// A toggle chip: one of a set, ink when on.
export const chip = (on: boolean) => cn("h-7 shrink-0 rounded-full border px-3 text-[12px] font-medium transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
  on ? "border-foreground bg-foreground text-background" : "border-border text-nav-fg hover:bg-muted")
