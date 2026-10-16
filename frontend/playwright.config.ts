import { existsSync } from "node:fs"
import path from "node:path"
import { defineConfig, devices } from "@playwright/test"

// The UI suite: a real Chromium against Flask serving the built bundle on a
// throw-away data directory that global-setup seeds (scripts/seed_uat.py).
//   npm run e2e            build, seed, run everything
//   npm run e2e -- --ui    the same, in Playwright's inspector
// Tiers by tag: @smoke (every page and header control), @flow (journeys),
// @a11y (axe), @keys (keyboard-only), @visual (screenshots, Linux only),
// @perf (budgets). CI runs them all and blocks on any failure.
const port = Number(process.env.E2E_PORT ?? 5099)
const root = path.resolve(import.meta.dirname, "..")
// the repo's venv when there is one (a developer's machine), else whatever python CI set up
const python = process.env.E2E_PYTHON ?? (existsSync(path.join(root, "venv/bin/python")) ? path.join(root, "venv/bin/python") : "python3")
const dataDir = process.env.E2E_DATA_DIR ?? "/tmp/odin-e2e"

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 30_000,
  expect: { timeout: 7_000, toHaveScreenshot: { maxDiffPixelRatio: 0.03, animations: "disabled" } },
  fullyParallel: false,          // one seeded database; journeys write to it
  workers: 1,
  retries: 0,                    // a journey edits the shared database: a retry would run on mutated data and hide the first failure
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    colorScheme: "light",
    locale: "en-GB",
    timezoneId: "Asia/Dubai",
  },
  projects: [
    // @phone runs on both; @phoneonly (the folded header) only on the phone
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, grepInvert: /@phoneonly/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, grep: /@phone/ },
  ],
  webServer: {
    command: `"${python}" -c "from app import app; app.run(host='127.0.0.1', port=${port})"`,
    cwd: root,
    port,
    reuseExistingServer: !process.env.CI,   // locally only: CI always starts its own, on the freshly seeded directory
    timeout: 60_000,
    env: { PYTHONUNBUFFERED: "1", ODIN_DATA_DIR: dataDir, SECRET_KEY: "e2e-not-secret", PORT: String(port) },
  },
})
