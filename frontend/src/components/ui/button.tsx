import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import type * as React from "react"
import { Loader2 } from "lucide-react"
import { cn } from "cn"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 cursor-pointer active:not-aria-[haspopup]:not-disabled:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 aria-busy:cursor-wait aria-busy:opacity-100 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // a filled button lifts its focus ring off the fill (a ring in the fill colour vanished in dark)
        default: "bg-primary text-primary-foreground hover:not-disabled:bg-primary/80 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        outline:
          "border-input bg-background hover:not-disabled:bg-muted hover:not-disabled:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:not-disabled:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:not-disabled:bg-[color-mix(in_oklch,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:not-disabled:bg-muted hover:not-disabled:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:not-disabled:bg-muted/50",
        destructive:
          "bg-destructive/10 text-destructive hover:not-disabled:bg-destructive/20 focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary-text underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-2 px-3 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-3 text-[13px] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-2 px-3 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

// Five states: default, hover, pressed (a slight scale), disabled (40%,
// not-allowed) and loading: `loading` keeps the button's size, hides the
// label behind a spinner, sets aria-busy and blocks a second click.
function Button({
  className,
  variant = "default",
  size = "default",
  loading = false,
  disabled,
  children,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants> & { loading?: boolean }) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }), loading && "relative")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? (
        <>
          <span className="invisible inline-flex items-center gap-[inherit]">{children as React.ReactNode}</span>
          <Loader2 className="absolute animate-spin" aria-hidden />
        </>
      ) : children}
    </ButtonPrimitive>
  )
}

export { Button, buttonVariants }
