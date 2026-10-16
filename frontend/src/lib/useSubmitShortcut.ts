import type { KeyboardEvent } from "react"

// Ctrl/⌘ + Enter sends the form the cursor is in (advice B5). Put `submitKey`
// on a <form> (it catches the textarea inside) or on one field; pass
// `submit` where the action is a button outside any form.
export function submitKey(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "defaultPrevented" | "preventDefault"> & { currentTarget: EventTarget }, submit?: () => void) {
  if (e.key !== "Enter" || !(e.ctrlKey || e.metaKey) || e.defaultPrevented) return
  const form = e.currentTarget instanceof HTMLFormElement ? e.currentTarget : e.currentTarget instanceof Element ? e.currentTarget.closest("form") : null
  if (!submit && !form) return
  e.preventDefault()
  if (submit) submit(); else form!.requestSubmit()   // requestSubmit runs the form's own checks (required, onSubmit)
}
