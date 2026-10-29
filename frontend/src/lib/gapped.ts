// A reload that asks nothing while the last one is still out, nor sooner than
// `gapMs` after it started: a window that regains focus every few seconds (a
// person flicking between apps) reloads at most once a gap (sim B2).
export function gapped(fn: () => Promise<unknown>, gapMs: number, now: () => number = Date.now) {
  let busy = false
  let last = -Infinity
  return async () => {
    if (busy || now() - last < gapMs) return
    busy = true
    last = now()
    try { await fn() } finally { busy = false }
  }
}
