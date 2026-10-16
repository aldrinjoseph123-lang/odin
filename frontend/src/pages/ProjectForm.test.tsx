// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import ProjectForm from "./ProjectForm"
import { admin } from "./fixtures"

const data = {
  mode: "edit", id: 7, me: 1, leads: [{ id: 1, name: "Ada" }], can_lead: true,
  project: { name: "Alpha", client: "Acme", customer_approval: false, owner_id: 1, stage_template_id: 1 },
  defaults: { stage_template_id: 1, customer_approval: false },
  via_options: ["Direct"], delivery_modes: ["On-site"], account_managers: [], partners: [], vendors: [], products: [], outsourcers: [],
  templates: [{ id: 1, name: "Standard" }], users: [{ id: 1, name: "Ada" }],
}
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), projectForm: vi.fn(async () => data) }))

describe("ProjectForm", () => {
  it("ticking only the customer-approval box enables Save", async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={["/projects/7/edit"]}><Routes><Route path="/projects/:id/edit" element={<ProjectForm user={admin} />} /></Routes></MemoryRouter>)
    const save = await screen.findByRole("button", { name: "Save changes" })
    await waitFor(() => expect(save).toHaveAttribute("aria-disabled", "true"))   // the snapshot is taken one render after load
    await user.click(screen.getByRole("checkbox", { name: /Ask the customer contact to approve/ }))
    expect(save).toHaveAttribute("aria-disabled", "false")
  })
})
