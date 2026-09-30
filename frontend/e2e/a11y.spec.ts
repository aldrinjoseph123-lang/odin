import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { setTheme, signIn } from "./helpers"

// @a11y: axe on every page, light and dark, against WCAG 2.1 AA. Serious and
// critical findings fail the run; moderate ones are listed so they don't hide.
const PAGES = ["/dashboard", "/board", "/board?rollout=1", "/board?view=calendar", "/board?view=kibana", "/my-work", "/people", "/people/2", "/projects", "/projects/1", "/projects/new",
  "/projects/1/report", "/projects/1/signoff", "/projects/11/signoff", "/reports/all", "/analytics", "/alerts", "/account", "/settings/general", "/settings/integrations", "/settings/rbac", "/settings/contacts", "/users", "/audit-logs", "/login"]

for (const theme of ["light", "dark"] as const) {
  test(`@a11y every page passes WCAG 2.1 AA in ${theme}`, async ({ page }) => {
    test.setTimeout(180_000)
    await signIn(page, "admin", "/dashboard")
    const report: string[] = []
    for (const path of PAGES) {
      await page.goto(path)
      await setTheme(page, theme)
      await page.locator("main, form").first().waitFor()
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).exclude("iframe").analyze()
      for (const v of results.violations) {
        // axe's own measurement rides along for contrast findings: "#5b6270 on #eeeef6 = 4.3"
        const line = `${path} [${v.impact}] ${v.id}: ${v.help} — ${v.nodes.slice(0, 3).map((n) => {
          const d = n.any[0]?.data as { fgColor?: string; bgColor?: string; contrastRatio?: number } | undefined
          return `${n.target.join(" ")}${d?.contrastRatio ? ` (${d.fgColor} on ${d.bgColor} = ${d.contrastRatio.toFixed(2)})` : ""}`
        }).join(" | ")}`
        if (v.impact === "serious" || v.impact === "critical") report.push(line)
        else console.log(`note ${line}`)
      }
    }
    expect(report, report.join("\n")).toEqual([])
  })
}

test("@a11y the dashboard's customise mode is operable by assistive tech", async ({ page }) => {
  await signIn(page, "admin", "/dashboard")
  await page.getByRole("button", { name: "Customise" }).click()
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.help}`)).toEqual([])
})
