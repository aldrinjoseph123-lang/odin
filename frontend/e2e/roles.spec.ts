import { expect, test, type Page } from "@playwright/test"
import { api, expectClean, inviteExternal, signIn, signInWithLink, watch } from "./helpers"

// @roles (P2-56): the accounts the other specs never sign in as. A Contributor is staff
// who creates and comments but moves and plans nothing; an external (Customer,
// Contractor, Reseller) sees only the rollouts they were invited to, through a
// one-time emailed link. smoke.spec covers admin, member and viewer.
// The server's side of the same boundaries is tests/golden_routes.json (every route x role).

type FlowRows = { rows: { id: number; name: string; can_move: boolean }[] }
type PlanRows = { rows: { id: number; name: string; can_edit: boolean }[] }

test("@smoke @roles a contributor reaches the staff pages, and nothing on them moves or plans a rollout", async ({ page }) => {
  const errors = watch(page)
  await signIn(page, "contributor")
  for (const [path, h1] of [
    ["/dashboard", /Good (morning|afternoon|evening)/], ["/board", /Active rollouts/], ["/my-work", /My work/], ["/people", /People/],
    ["/projects", /Rollouts/], ["/projects/1", /EDR Rollout - Globex/], ["/projects/new", /New project/], ["/projects/1/report", /EDR Rollout - Globex/],
    ["/analytics", /Cycle time/], ["/alerts", /Alerts/], ["/account", /Account/],
  ] as [string, RegExp][]) {
    await page.goto(path)
    await expect(page.locator("h1").first(), path).toHaveText(h1)
  }
  // the admin pages refuse, they do not render broken
  for (const path of ["/settings/general", "/users", "/audit-logs"]) expect((await page.request.get(path)).status(), path).toBe(403)
  await page.goto("/dashboard")
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /^Settings/ })).toHaveCount(0)
  // the Flow tells the board nothing may be dragged, and the server agrees
  const flow = await api<FlowRows>(page, "GET", "/api/flow")
  expect(flow.body.rows.length).toBeGreaterThan(5)
  expect(flow.body.rows.filter((r) => r.can_move).map((r) => r.name), "no card may move").toEqual([])
  const plan = await api<PlanRows>(page, "GET", "/api/flow/plan")
  expect(plan.body.rows.filter((r) => r.can_edit).map((r) => r.name), "no plan may be redated").toEqual([])
  await page.goto("/board?view=kanban")
  await expect(page.locator('[data-slot="kanban-column"]').first()).toBeVisible()
  await expect(page.getByRole("button", { name: /^Move .* to / })).toHaveCount(0)
  await page.goto("/board?view=gantt")
  await page.getByRole("button", { name: "Open every rollout" }).click()
  await expect(page.getByRole("button", { name: /Drag to move/ })).toHaveCount(0)
  // and the server refuses what the page does not offer
  const stage = await api<{ error?: string }>(page, "POST", "/api/projects/1/stage", { stage: "Scoping" })
  expect(stage.status).toBe(403)
  const dates = await api(page, "PUT", "/api/projects/1/plan", { stages: [], reason: "x" })
  expect(dates.status).toBe(403)
  expectClean(errors.filter((e) => !/\b403\b/.test(e)))   // the refusals above are the point
})

// One rollout other than the ones the journeys edit: the last of the seeded portfolio.
async function lastRollout(page: Page) {
  const list = await api<{ rows: { id: number; name: string }[] }>(page, "GET", "/api/projects")
  const rows = [...list.body.rows].sort((a, b) => b.id - a.id)
  return rows[0]
}

for (const role of ["Customer", "Contractor", "Reseller"] as const) {
  test(`@flow @roles a ${role.toLowerCase()} signs in from the emailed link and sees only their rollout`, async ({ page }) => {
    const errors = watch(page)
    await signIn(page, "admin")
    const mine = await lastRollout(page)
    const { link } = await inviteExternal(page, mine.id, role)
    await signInWithLink(page, link)
    // they land on the rollout they were invited to, with the access badge and a short header
    await expect(page).toHaveURL(new RegExp(`/projects/${mine.id}`))
    await expect(page.locator("h1").first()).toHaveText(mine.name)
    await expect(page.getByText(role === "Customer" ? "Customer access" : "Partner access")).toBeVisible()
    const nav = page.getByRole("navigation", { name: "Main" })
    await expect(nav.getByRole("link")).toHaveCount(2)
    await expect(nav.getByRole("link", { name: /^Flow/ })).toBeVisible()
    await expect(nav.getByRole("link", { name: /^Rollouts/ })).toBeVisible()
    // none of the staff controls on the page
    for (const name of ["Add people", "Edit stages", "More actions", "Edit dates"]) await expect(page.getByRole("button", { name }), name).toHaveCount(0)
    // the lists hold only what they were invited to
    const projects = await api<{ rows: { id: number }[]; can_create: boolean }>(page, "GET", "/api/projects")
    expect(projects.body.rows.map((r) => r.id)).toEqual([mine.id])
    expect(projects.body.can_create).toBe(false)
    await page.goto("/board")
    await expect(page.locator("h1").first()).toHaveText(/Active rollouts/)
    const flow = await api<FlowRows>(page, "GET", "/api/flow")
    expect(flow.body.rows.map((r) => r.id)).toEqual([mine.id])
    expect(flow.body.rows.some((r) => r.can_move)).toBe(false)
    // another rollout is not theirs to read; the staff views refuse
    const other = await api(page, "GET", `/api/projects/${mine.id === 1 ? 2 : 1}`)
    expect(other.status).toBe(404)
    for (const path of ["/api/flow/plan", "/api/people", "/api/alerts", "/api/analytics", "/api/users"]) expect((await api(page, "GET", path)).status, path).toBe(403)
    for (const path of ["/settings/general", "/people", "/analytics", "/projects/new", "/users"]) expect((await page.request.get(path)).status(), path).toBe(403)
    // they cannot move the rollout or plan it
    expect((await api(page, "POST", `/api/projects/${mine.id}/stage`, { stage: "Scoping" })).status).toBe(403)
    expect((await api(page, "PUT", `/api/projects/${mine.id}/plan`, { stages: [], reason: "x" })).status).toBe(403)
    expectClean(errors.filter((e) => !/\b(403|404)\b/.test(e)))
  })
}
