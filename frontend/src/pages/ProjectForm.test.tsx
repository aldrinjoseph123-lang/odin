// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import ProjectForm from "./ProjectForm"
import { admin } from "./fixtures"
import * as api from "@/lib/api"

const data = {
  mode: "edit", id: 7, me: 1, leads: [{ id: 1, name: "Ada" }], can_lead: true,
  project: { name: "Alpha", client: "Acme", customer_approval: false, owner_id: 1, stage_template_id: 1 },
  defaults: { stage_template_id: 1, customer_approval: false },
  via_options: ["Direct"], delivery_modes: ["On-site"], account_managers: [], partners: [], vendors: [], products: [], outsourcers: [],
  templates: [{ id: 1, name: "Standard" }], users: [{ id: 1, name: "Ada" }], custom_fields: [],
}
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), projectForm: vi.fn(async () => data),
  postForm: vi.fn(async () => ({ ok: true, messages: [], undo: null, location: null })) }))

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

describe("ProjectForm approver", () => {
  const edit = () => render(<MemoryRouter initialEntries={["/projects/7/edit"]}><Routes><Route path="/projects/:id/edit" element={<ProjectForm user={admin} />} /></Routes></MemoryRouter>)

  it("offers the Customer contacts as the approver while approval is on, and posts the pick", async () => {
    const user = userEvent.setup()
    vi.mocked(api.projectForm).mockResolvedValueOnce({ ...data, project: { ...data.project, customer_approval: true, approver_id: null },
      customers: [{ id: 5, name: "Ann" }, { id: 6, name: "Bob" }] } as unknown as api.ProjectFormData)
    edit()
    const pick = await screen.findByRole("combobox", { name: "Approver" })
    expect(pick).toHaveValue("")
    expect(screen.getByRole("option", { name: "First Customer contact (Ann)" })).toBeInTheDocument()
    await user.selectOptions(pick, "6")
    await user.click(screen.getByRole("button", { name: "Save changes" }))
    await waitFor(() => expect(api.postForm).toHaveBeenCalled())
    expect((vi.mocked(api.postForm).mock.calls[0][1] as FormData).get("approver_id")).toBe("6")
  })

  it("has no approver pick when the team has no Customer contact, or approval is off", async () => {
    edit()
    await screen.findByRole("button", { name: "Save changes" })
    expect(screen.queryByRole("combobox", { name: "Approver" })).toBeNull()
  })
})
