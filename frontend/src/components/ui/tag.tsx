import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva } from "class-variance-authority"
import { cn } from "cn"

// The small label next to a name: one component for nine kinds, so the same
// word reads the same everywhere (DESIGN.md: colour is a state, never
// decoration). Only a scope status and an impact carry colour, by `level`;
// the rest are neutral. A rollout's own state keeps StateChip.
const tagVariants = cva(
  "inline-flex h-5 w-fit shrink-0 items-center gap-1 rounded-4xl px-2 text-[11px] font-medium whitespace-nowrap [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      kind: {
        plain: "bg-muted text-foreground",
        role: "bg-muted text-muted-foreground",
        kind: "w-16 justify-center bg-secondary text-secondary-foreground",
        default: "bg-accent text-accent-foreground",
        bad: "bg-bad-soft text-bad",   // an open blocker: the one red here besides overdue (DESIGN.md)
        warn: "bg-warn-soft text-warn",   // a count that needs a look: amber, never red
        source: "border border-border text-foreground [a]:hover:bg-muted",
        scope: "",
        impact: "",
      },
    },
    defaultVariants: { kind: "plain" },
  },
)

// the word carries the level; red is for overdue only (test report UX-20), so a high impact is amber
const LEVEL_TONE = {
  scope: { agreed: "bg-muted text-muted-foreground", delivered: "bg-ok-soft text-ok", partial: "bg-warn-soft text-warn", descoped: "bg-muted text-muted-foreground" },
  impact: { high: "bg-warn-soft text-warn", medium: "bg-muted text-foreground", low: "bg-muted text-muted-foreground" },
} as const

type TagProps = useRender.ComponentProps<"span"> & (
  | { kind?: "plain" | "role" | "kind" | "default" | "source" | "warn" | "bad"; level?: undefined }
  | { kind: "scope" | "impact"; level: string }
)

function Tag({ className, kind = "plain", level, render, ...props }: TagProps) {
  const tone = kind === "scope" || kind === "impact" ? (LEVEL_TONE[kind] as Record<string, string>)[level ?? ""] ?? "bg-muted text-muted-foreground" : ""
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">({ className: cn(tagVariants({ kind }), tone, className) }, props),
    render,
    state: { slot: "tag", kind },
  })
}

export { Tag }
