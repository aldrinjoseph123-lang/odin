export const CUT = ".truncate, [class*='line-clamp-']"
const isCut = (el: HTMLElement) => el.matches(CUT) && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)

// What a tooltip should say for an element, or null for none.
// A `title` moves to data-tip the first time (so the browser's own tooltip
// never doubles ours); if the element had no other accessible name, the title
// becomes its aria-label, and if it said more than the name it stays readable
// to assistive technology as aria-description (review P3-46). An icon-only
// control (no visible text) shows its aria-label; a control with visible text
// needs no tooltip.
export function tipText(el: HTMLElement): string | null {
  const title = el.getAttribute("title")
  if (title !== null) {
    el.removeAttribute("title")
    if (title) {
      el.dataset.tip = title
      const name = el.getAttribute("aria-label") ?? el.textContent?.trim() ?? ""
      if (!name) el.setAttribute("aria-label", title)
      else if (title !== name && !el.hasAttribute("aria-description")) el.setAttribute("aria-description", title)
    }
  }
  if (el.dataset.tip) return el.dataset.tip
  // text cut short by truncate / line-clamp shows in full (whole-app critique: 55 cut texts had no way to read them)
  if (isCut(el)) return el.textContent?.trim() || null
  // an icon control whose only text is a short count ("27") still counts as icon-only
  const label = el.getAttribute("aria-label"), text = el.textContent?.trim() ?? ""
  return label && (!text || (/^[\d+]{1,4}$/.test(text) && !!el.querySelector("svg"))) ? label : null
}
