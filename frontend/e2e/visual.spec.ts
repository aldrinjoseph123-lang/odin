import { existsSync } from "node:fs"
import { expect, test } from "@playwright/test"
import { setTheme, signIn } from "./helpers"

// @visual: golden screenshots, light and dark, desktop and phone. Fonts and
// anti-aliasing differ across operating systems, so the goldens are Linux
// (CI) only; run `npm run e2e:update -- visual` in CI (workflow_dispatch) to
// refresh them after a deliberate change of look.
test.skip(process.platform !== "linux", "goldens are rendered on Linux")

// Rollout 2, not 1: the journeys (flows.spec) edit rollout 1 — its plan, scope,
// sign-off and activity — so its page would differ with the order tests ran in.
// No calendar: the seed dates everything from today, so a month grid changes
// every day (smoke.spec and the calendar journey in flows.spec cover it).
const PAGES: [string, string][] = [
  ["dashboard", "/dashboard"], ["flow", "/board"], ["flow-open", "/board?rollout=2"],
  ["projects", "/projects"], ["project", "/projects/2"], ["settings", "/settings/general"], ["login", "/login"],
]

for (const theme of ["light", "dark"] as const) {
  for (const [name, path] of PAGES) {
    test(`@visual @phone ${name} ${theme}`, async ({ page }, info) => {
      const golden = info.snapshotPath(`${name}-${theme}-${info.project.name}.png`)
      // a bare --update-snapshots means "changed"; without either, a missing golden is skipped rather than failed
      test.skip(!existsSync(golden) && !["all", "changed"].includes(info.config.updateSnapshots), "no golden yet — run the CI workflow with update_snapshots and commit the artifact")
      if (path !== "/login") await signIn(page, "admin", path); else await page.goto(path)
      await setTheme(page, theme)
      await page.locator("main, form").first().waitFor()
      await page.waitForTimeout(400)   // charts and fonts settle
      // relative times and the clock change every minute: mask them
      const mask = [page.locator("time"), page.locator("text=/just now|\\d+ min ago|\\d+ h ago/")]
      // the project page's plan, timeline and tasks are dated from the seed's today, so they reflow
      // daily: compare its first screen only (the plan is covered by flows.spec)
      await expect(page).toHaveScreenshot(`${name}-${theme}-${info.project.name}.png`, { fullPage: name !== "project", mask, maxDiffPixelRatio: 0.03 })
    })
  }
}
