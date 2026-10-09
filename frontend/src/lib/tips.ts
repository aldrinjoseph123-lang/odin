// What a tooltip should say for an element, or null for none.
// A `title` moves to data-tip the first time (so the browser's own tooltip
// never doubles ours); if the element had no other accessible name, the title
// becomes its aria-label. An icon-only control (no visible text) shows its
// aria-label; a control with visible text needs no tooltip.
export function tipText(el: HTMLElement): string | null {
  const title = el.getAttribute("title")
  if (title !== null) {
    el.removeAttribute("title")
    if (title) {
      el.dataset.tip = title
      if (!el.getAttribute("aria-label") && !el.textContent?.trim()) el.setAttribute("aria-label", title)
    }
  }
  if (el.dataset.tip) return el.dataset.tip
  // an icon control whose only text is a short count ("27") still counts as icon-only
  const label = el.getAttribute("aria-label"), text = el.textContent?.trim() ?? ""
  return label && (!text || (/^[\d+]{1,4}$/.test(text) && !!el.querySelector("svg"))) ? label : null
}
