// Inline form errors for every form (UI/UX plan 5.2): when the browser finds a
// field invalid on submit, the field turns red (aria-invalid) and its own
// explanation ("Please fill out this field.") sits right under it until the
// value is fixed, instead of a bubble that fades. The note is inserted right
// after the field (in the flow, so it pushes the next label down rather than
// covering it) and removed once the field is valid; no component has to know.
type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement

let note: HTMLParagraphElement | null = null
let field: Field | null = null

function clear() {
  if (field) { field.removeAttribute("aria-invalid"); field.removeAttribute("aria-errormessage") }
  note?.remove(); note = null; field = null
}

export function installFieldErrors(doc: Document = document) {
  doc.addEventListener("invalid", (e) => {
    const el = e.target as Field
    e.preventDefault()                       // no fading bubble: the note below replaces it
    if (field && field !== el && field.form === el.form && !field.validity.valid) return   // one note per submit: the first field
    clear()
    field = el
    note = doc.createElement("p")
    note.id = "field-error"
    note.setAttribute("role", "alert")
    note.className = "field-error"
    note.textContent = el.validationMessage
    el.setAttribute("aria-invalid", "true")
    el.setAttribute("aria-errormessage", note.id)
    el.insertAdjacentElement("afterend", note)
    el.focus({ preventScroll: false })
  }, true)
  const recheck = (e: Event) => {
    if (!field) return
    if (!field.isConnected || (e.target === field && field.validity.valid)) clear()
    else if (e.target === field && note) note.textContent = field.validationMessage
  }
  doc.addEventListener("input", recheck, true)
  doc.addEventListener("change", recheck, true)
  window.addEventListener("popstate", clear)
}
