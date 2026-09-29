// @perf: Lighthouse on the dashboard and the flow, signed in, plus a ceiling
// on the main bundle. Run after `playwright test` against the same server:
//   node e2e/perf.mjs            (E2E_PORT, default 5099)
// Thresholds are deliberately modest: Flask's dev server sends no
// compression, and the pages are data-heavy by design.
import { readdirSync } from "node:fs"
import { gzipSync } from "node:zlib"
import { readFileSync } from "node:fs"
import lighthouse from "lighthouse"
import desktopConfig from "lighthouse/core/config/desktop-config.js"
import { chromium } from "@playwright/test"

const base = `http://127.0.0.1:${process.env.E2E_PORT ?? 5099}`
const BUDGET = { performance: 75, accessibility: 90, "best-practices": 85, mainBundleGzipKB: 260 }

// the main bundle, gzipped, must stay under the ceiling
const assets = readdirSync("dist/assets").filter((f) => f.endsWith(".js")).map((f) => ({ f, gz: gzipSync(readFileSync(`dist/assets/${f}`)).length }))
const main = assets.sort((a, b) => b.gz - a.gz)[0]
console.log(`main bundle ${main.f}: ${(main.gz / 1024).toFixed(0)} KB gzipped (ceiling ${BUDGET.mainBundleGzipKB})`)
if (main.gz / 1024 > BUDGET.mainBundleGzipKB) { console.error("bundle over budget"); process.exit(1) }

// a signed-in cookie, through the same door the app uses
const first = await fetch(`${base}/api/session`)   // one session: its token and its cookie together
const s = await first.json()
const setCookie = first.headers.get("set-cookie") ?? ""
const r = await fetch(`${base}/api/login`, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": s.csrf, Cookie: setCookie.split(";")[0] }, body: JSON.stringify({ username: "admin", password: "Glacier-Harbour-4471" }) })
const cookie = (r.headers.get("set-cookie") ?? setCookie).split(";")[0]
if (!r.ok) { console.error("sign-in failed", r.status); process.exit(1) }

// Lighthouse drives Playwright's Chromium over the debugging port
const browser = await chromium.launch({ args: ["--remote-debugging-port=9222"] })
let failed = false
try {
  for (const path of ["/dashboard", "/board"]) {
    // the desktop config: a desktop screen and desktop network/CPU throttling, not the phone-on-4G default
    const result = await lighthouse(`${base}${path}`, { port: 9222, output: "json", logLevel: "error", onlyCategories: ["performance", "accessibility", "best-practices"], extraHeaders: { Cookie: cookie } }, desktopConfig)
    const scores = Object.fromEntries(Object.entries(result.lhr.categories).map(([k, v]) => [k, Math.round((v.score ?? 0) * 100)]))
    const lcp = result.lhr.audits["largest-contentful-paint"]?.displayValue
    console.log(`${path}: ${Object.entries(scores).map(([k, v]) => `${k} ${v}`).join(" · ")} · LCP ${lcp}`)
    for (const [k, min] of Object.entries(BUDGET)) if (k in scores && scores[k] < min) { console.error(`  ${path} ${k} ${scores[k]} < ${min}`); failed = true }
  }
} finally {
  await browser.close()
}
process.exit(failed ? 1 : 0)
