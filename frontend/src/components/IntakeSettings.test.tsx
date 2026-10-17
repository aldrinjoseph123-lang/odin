// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { IntakeSettings } from "./IntakeSettings"
import * as api from "@/lib/api"

const policies: api.Policy[] = [
  { key: "intake_template", area: "intake", kind: "choice", label: "Stage template for intakes", help: "", value: "", group: "Intake defaults", choices: ["1"] },
  { key: "intake_owner", area: "intake", kind: "choice", label: "Default project manager", help: "", value: "", group: "Intake defaults", choices: ["2"] },
  { key: "intake_sources", area: "intake", kind: "text", label: "Allowed sources", help: "", value: "", max: 300, group: "Intake defaults" },
  { key: "intake_rate_per_min", area: "intake", kind: "int", label: "Most intakes per token per minute", help: "Calls beyond this are refused.", value: 30, min: 1, max: 100, group: "Intake defaults" },
  { key: "intake_token_days", area: "intake", kind: "int", label: "Intake tokens last (days)", help: "", value: 365, min: 1, max: 1095, group: "Intake defaults" },
  { key: "intake_allowed_ips", area: "intake", kind: "text", label: "Allowed addresses", help: "", value: "", max: 500, group: "Intake defaults" },
]
const page = (): api.IntakeSettingsData => ({
  tokens: [{ id: 4, name: "crm-prod", created_by: "Admin", created_at: "2026-10-01T08:00:00", expires_at: "2099-01-01T00:00:00", last_used_at: null, revoked_at: null }],
  calls: [{ id: 2, token_name: "crm-prod", at: "2026-10-02T08:00:00", status: 200, result: "duplicate", deal_id: "D-1", project_id: 5, detail: null },
    { id: 1, token_name: "crm-prod", at: "2026-10-01T08:00:00", status: 400, result: "refused", deal_id: null, project_id: null, detail: "client is required" }],
  policies, keep: 200, templates: [{ id: 1, name: "Generic" }], owners: [{ id: 2, name: "Priya Menon" }], endpoint: "/api/v1/intake",
})

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  intakeSettings: vi.fn(async () => page()),
  postForm: vi.fn(async () => ({ ok: true as const, messages: [], undo: null, location: null, token: "odin_secret" })),
}))
afterEach(() => { cleanup(); vi.mocked(api.postForm).mockClear() })

describe("Settings › Integrations › Intake", () => {
  it("shows the tokens and the last calls with their results", async () => {
    render(<IntakeSettings />)
    const tokens = await screen.findByRole("table", { name: "Intake tokens" })
    expect(within(tokens).getByText("crm-prod")).toBeInTheDocument()
    const calls = screen.getByRole("table", { name: "Recent intake calls" })
    expect(within(calls).getByText("200 Already had it")).toBeInTheDocument()
    expect(within(calls).getByText("400 Refused")).toBeInTheDocument()
    expect(within(calls).getByText("client is required")).toBeInTheDocument()
  })

  it("makes a create-scope token and shows it once", async () => {
    const user = userEvent.setup()
    render(<IntakeSettings />)
    await user.type(await screen.findByLabelText(/Source \(the token's name\)/), "crm-test")
    await user.click(screen.getByRole("button", { name: "Create intake token" }))
    await waitFor(() => expect(api.postForm).toHaveBeenCalledWith("/settings/api-tokens", { name: "crm-test", scope: "create" }))
    expect(await screen.findByLabelText("New intake token")).toHaveValue("odin_secret")
    await user.click(screen.getByRole("button", { name: "I have saved it" }))
    expect(screen.queryByLabelText("New intake token")).toBeNull()
  })

  it("saves the defaults through the policy route", async () => {
    const user = userEvent.setup()
    render(<IntakeSettings />)
    await user.selectOptions(await screen.findByRole("combobox", { name: /Default project manager/ }), "2")
    await user.type(screen.getByRole("textbox", { name: /Allowed sources/ }), "crm-prod")
    await user.type(screen.getByRole("textbox", { name: /Allowed addresses/ }), "203.0.113.0/24")
    await user.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(api.postForm).toHaveBeenCalledWith("/settings/policies/intake",
      { intake_template: "", intake_owner: "2", intake_sources: "crm-prod", intake_rate_per_min: "30", intake_token_days: "365", intake_allowed_ips: "203.0.113.0/24" }))
  })

  it("renews a token, an expired one too, and says how long a token lives", async () => {
    vi.mocked(api.intakeSettings).mockResolvedValueOnce({ ...page(), tokens: [{ ...page().tokens[0], expires_at: "2020-01-01T00:00:00" }] })
    const user = userEvent.setup()
    render(<IntakeSettings />)
    const tokens = await screen.findByRole("table", { name: "Intake tokens" })
    expect(within(tokens).getByText("expired")).toBeInTheDocument()
    expect(within(tokens).queryByRole("button", { name: "Revoke crm-prod" })).toBeNull()
    expect(screen.getByText(/Works for 365 days; Renew extends it from today/)).toBeInTheDocument()
    await user.click(within(tokens).getByRole("button", { name: "Renew crm-prod" }))
    await waitFor(() => expect(api.postForm).toHaveBeenCalledWith("/settings/api-tokens/4/renew"))
  })
})
