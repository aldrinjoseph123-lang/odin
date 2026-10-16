import type { ComponentProps } from "react"
import { submitKey } from "@/lib/useSubmitShortcut"

// A form that Ctrl/⌘ + Enter sends from any of its fields, a textarea's included
// (advice B5). The key listener sits on the form only to catch what its own
// fields bubble up; the fields are the interactive elements.
export function SubmitForm(props: ComponentProps<"form">) {
  // oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
  return <form onKeyDown={submitKey} {...props} />
}
