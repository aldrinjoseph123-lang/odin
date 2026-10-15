// Copy text to the clipboard. The async API exists only on a secure page
// (https or localhost), so on a plain-http LAN address it is missing: fall back
// to selecting a hidden text area. False when neither works; the caller then
// says "select it and copy" (review P3-36).
export async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true } catch { /* missing or refused: try the old way */ }
  const box = Object.assign(document.createElement("textarea"), { value: text })
  box.setAttribute("readonly", "")
  box.style.cssText = "position:fixed;top:0;left:0;opacity:0"
  document.body.append(box)
  box.select()
  try { return document.execCommand("copy") } catch { return false } finally { box.remove() }
}
