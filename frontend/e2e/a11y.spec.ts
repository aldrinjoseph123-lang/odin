import { expect, test, type Page } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { setTheme, signIn } from "./helpers"
import { ACCENTS } from "../src/lib/theme"

// @a11y: axe on every page, light and dark, against WCAG 2.1 AA. Serious and
// critical findings fail the run; moderate ones are listed so they don't hide.
const PAGES = ["/dashboard", "/board", "/board?rollout=1", "/board?view=calendar", "/board?view=calendar&cal=week", "/board?view=kanban", "/board?view=gantt", "/my-work", "/people", "/people/2", "/projects", "/projects/1", "/projects/new",
  "/projects/1/report", "/projects/1/signoff", "/projects/11/signoff", "/reports/all", "/analytics", "/alerts", "/account", "/settings/general", "/settings/integrations", "/settings/rbac", "/settings/contacts", "/users", "/audit-logs", "/login"]

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
// Serious and critical findings go in the list that fails the run; the rest are logged.
async function scan(page: Page, label: string, report: string[]) {
  const results = await new AxeBuilder({ page }).withTags(TAGS).exclude("iframe").analyze()
  for (const v of results.violations) {
    // axe's own measurement rides along for contrast findings: "#5b6270 on #eeeef6 = 4.3"
    const line = `${label} [${v.impact}] ${v.id}: ${v.help} — ${v.nodes.slice(0, 3).map((n) => {
      const d = n.any[0]?.data as { fgColor?: string; bgColor?: string; contrastRatio?: number } | undefined
      return `${n.target.join(" ")}${d?.contrastRatio ? ` (${d.fgColor} on ${d.bgColor} = ${d.contrastRatio.toFixed(2)})` : ""}`
    }).join(" | ")}`
    if (v.impact === "serious" || v.impact === "critical") report.push(line)
    else console.log(`note ${line}`)
  }
}
// The accent is a data attribute on the root (index.html sets it from localStorage `odin.accent`).
const setAccent = (page: Page, accent: string) => page.evaluate((a) => { document.documentElement.dataset.accent = a }, accent)

for (const theme of ["light", "dark"] as const) {
  test(`@a11y every page passes WCAG 2.1 AA in ${theme}`, async ({ page }) => {
    test.setTimeout(180_000)
    await signIn(page, "admin", "/dashboard")
    const report: string[] = []
    for (const path of PAGES) {
      await page.goto(path)
      await setTheme(page, theme)
      await page.locator("main, form").first().waitFor()
      await scan(page, path, report)
    }
    expect(report, report.join("\n")).toEqual([])
  })
}

// Every accent, light and dark (review P2-46: only blue was ever checked). The accent moves the
// ring, the selected nav pill, the primary button and the accent text, so the pages that use them
// most are scanned: the dashboard, the flow with a rollout open, a project, the account page (the
// swatches themselves) and, for the error colours, a form with its inline error showing.
const ACCENT_PAGES = ["/dashboard", "/board?rollout=1", "/projects/1", "/account"]
for (const accent of ACCENTS.map((a) => a.key)) {
  test(`@a11y accent ${accent} passes WCAG 2.1 AA in both themes, with an inline error showing`, async ({ page }) => {
    test.setTimeout(120_000)
    await signIn(page, "admin", "/dashboard")
    const report: string[] = []
    for (const theme of ["light", "dark"] as const) {
      for (const path of ACCENT_PAGES) {
        await page.goto(path)
        await setTheme(page, theme)
        await setAccent(page, accent)
        await page.locator("main, form").first().waitFor()
        await scan(page, `${path} (${accent}, ${theme})`, report)
      }
      // the error state: the required name left empty, the note under the field in --destructive
      await page.goto("/projects/new")
      await setTheme(page, theme)
      await setAccent(page, accent)
      await page.getByRole("button", { name: "Create project" }).click()
      await expect(page.getByRole("textbox", { name: "Project name" })).toHaveAttribute("aria-invalid", "true")
      await scan(page, `/projects/new with an error (${accent}, ${theme})`, report)
    }
    expect(report, report.join("\n")).toEqual([])
  })
}

test("@a11y a dashboard widget's menu is operable by assistive tech", async ({ page }) => {
  await signIn(page, "admin", "/dashboard")
  await page.getByRole("button", { name: "Customise Timeline" }).click()
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.help}`)).toEqual([])
})
