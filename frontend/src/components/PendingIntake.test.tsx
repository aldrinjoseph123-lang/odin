// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { IntakeBanner, PendingIntake } from "./PendingIntake"
import * as api from "@/lib/api"

const row: api.PendingIntakeRow = {
  id: 7, name: "Branch SD-WAN", client: "Hooli", source: "crm-prod", deal_id: "CRM-9", delivery_mode: "Outsourced", vendor_name: "Fortinet",
  product_name: "FortiGate", po_number: "PO-1", target_end_date: "2026-12-01", contacts: ["it@hooli.example"], owner_name: "Admin User", created_at: "2026-10-01T08:00:00",
}
const meta = (over: Partial<api.PendingIntake> = {}): api.PendingIntake => ({ rows: [row], can_confirm: true, can_lead: true, leads: [{ id: 3, name: "Priya" }], po_category: "Client PO", ...over })

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  pendingIntake: vi.fn(async () => meta()),
  confirmIntake: vi.fn(async () => ({ ok: true as const, messages: ["confirmed"], undo: null, location: "/projects/7" })),
  editIntake: vi.fn(async () => ({ ok: true as const, messages: ["Intake details saved"], undo: null, location: null })),
  projectForm: vi.fn(async () => ({ delivery_modes: ["Distribution/MSSP", "Outsourced"], vendors: ["Fortinet", "Palo Alto"], products: [{ name: "PA-440", vendor: "Palo Alto" }] })),
  projectFields: vi.fn(async () => ({ can_edit: true, fields: [{ id: 3, name: "Region", kind: "choice", choices: ["UAE", "KSA"], required: false, customer_visible: false, show_in_list: false, value: null }] })),
}))
afterEach(() => { cleanup(); vi.mocked(api.pendingIntake).mockImplementation(async () => meta()) })

const mount = (rows = [row]) => render(
  <MemoryRouter initialEntries={["/board"]}>
    <Routes><Route path="/board" element={<PendingIntake rows={rows} />} /><Route path="/projects/:id" element={<p>The new rollout</p>} /></Routes>
  </MemoryRouter>)

// jsdom does not count a file chosen with user.upload as filling a required file input, so the form is submitted directly
const submit = () => fireEvent.submit(screen.getByRole("dialog").querySelector("form")!)

describe("Pending intake", () => {
  it("draws nothing when no deal waits, and asks nothing of the server", () => {
    vi.mocked(api.pendingIntake).mockClear()
    mount([])
    expect(screen.queryByRole("region", { name: "Pending intake" })).toBeNull()
    expect(api.pendingIntake).not.toHaveBeenCalled()
  })

  it("lists the deal with where it came from", async () => {
    mount()
    expect(await screen.findByRole("region", { name: "Pending intake" })).toBeInTheDocument()
    expect(screen.getByText("Branch SD-WAN")).toBeInTheDocument()
    expect(screen.getByText(/Hooli · Fortinet FortiGate/)).toBeInTheDocument()
    expect(screen.getByText("crm-prod")).toBeInTheDocument()
  })

  it("confirms with the PO file and goes to the new rollout", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Confirm Branch SD-WAN" }))
    expect(screen.getByText("it@hooli.example")).toBeInTheDocument()
    expect(screen.queryByRole("combobox")).toBeNull()   // someone who can move stages needs to name no one
    await user.upload(screen.getByLabelText("Client PO document"), new File(["%PDF-1.4"], "po.pdf", { type: "application/pdf" }))
    submit()
    await waitFor(() => expect(api.confirmIntake).toHaveBeenCalled())
    const [id, form] = vi.mocked(api.confirmIntake).mock.calls[0]
    expect(id).toBe(7)
    expect(form.has("po_document")).toBe(true)
    expect(form.get("po_number")).toBe("PO-1")
    expect(await screen.findByText("The new rollout")).toBeInTheDocument()
  })

  it("asks someone who cannot move stages to name a project manager, and shows a refusal in place", async () => {
    const user = userEvent.setup()
    vi.mocked(api.pendingIntake).mockImplementation(async () => meta({ can_lead: false }))
    vi.mocked(api.confirmIntake).mockRejectedValueOnce(new api.ApiError(400, "Attach the Client PO document to confirm the rollout"))
    mount()
    await user.click(await screen.findByRole("button", { name: "Confirm Branch SD-WAN" }))
    expect(await screen.findByRole("combobox", { name: /Project manager/ })).toBeInTheDocument()
    await user.upload(screen.getByLabelText("Client PO document"), new File(["%PDF-1.4"], "po.pdf", { type: "application/pdf" }))
    await user.selectOptions(screen.getByRole("combobox", { name: /Project manager/ }), "3")
    submit()
    expect(await screen.findByRole("alert")).toHaveTextContent("Attach the Client PO document")
    expect(screen.queryByText("The new rollout")).toBeNull()
  })

  it("will not confirm for a role that may not", async () => {
    const user = userEvent.setup()
    vi.mocked(api.pendingIntake).mockImplementation(async () => meta({ can_confirm: false }))
    mount()
    await user.click(await screen.findByRole("button", { name: "Confirm Branch SD-WAN" }))
    expect(await screen.findByText(/Your role cannot confirm/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Confirm and take ownership" })).toHaveAttribute("aria-disabled", "true")
  })

  it("on the rollout's own page: says it waits, confirms in place, and offers Discard only to who may delete", async () => {
    const user = userEvent.setup()
    const confirmed = vi.fn()
    render(<MemoryRouter><IntakeBanner projectId={7} canDiscard={false} onConfirmed={confirmed} /></MemoryRouter>)
    expect(await screen.findByText(/A deal from crm-prod \(CRM-9\), waiting for a project manager/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Confirm…" }))
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull()
    submit()
    await waitFor(() => expect(confirmed).toHaveBeenCalledWith(["confirmed"]))
  })

  it("corrects the details before confirming, in the lane and on the rollout's page", async () => {
    const user = userEvent.setup()
    const changed = vi.fn()
    render(<MemoryRouter><PendingIntake rows={[row]} onChanged={changed} /></MemoryRouter>)
    await user.click(await screen.findByRole("button", { name: "Edit details of Branch SD-WAN" }))
    const dialog = await screen.findByRole("dialog")
    const name = await within(dialog).findByRole("textbox", { name: "Name *" })
    expect(name).toHaveValue("Branch SD-WAN")
    await user.clear(name); await user.type(name, "Branch SD-WAN phase 1")
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Region" }), "KSA")
    await user.click(within(dialog).getByRole("button", { name: "Save details" }))
    await waitFor(() => expect(api.editIntake).toHaveBeenCalledWith(7, {
      name: "Branch SD-WAN phase 1", client: "Hooli", vendor_name: "Fortinet", product_name: "FortiGate", delivery_mode: "Outsourced",
      target_end_date: "2026-12-01", po_number: "PO-1", field_3: "KSA" }))
    await waitFor(() => expect(changed).toHaveBeenCalled())
    cleanup()
    const edited = vi.fn()
    render(<MemoryRouter><IntakeBanner projectId={7} canDiscard={false} onConfirmed={() => {}} onEdited={edited} /></MemoryRouter>)
    await user.click(await screen.findByRole("button", { name: "Edit details…" }))
    await user.click(await within(await screen.findByRole("dialog")).findByRole("button", { name: "Save details" }))
    await waitFor(() => expect(edited).toHaveBeenCalled())
  })

  it("offers no edit to a role that may not confirm", async () => {
    vi.mocked(api.pendingIntake).mockImplementation(async () => meta({ can_confirm: false }))
    mount()
    expect(await screen.findByRole("button", { name: "Confirm Branch SD-WAN" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Edit details/ })).toBeNull()
  })

  it("draws nothing on a rollout that is not pending", async () => {
    render(<MemoryRouter><IntakeBanner projectId={99} canDiscard onConfirmed={() => {}} /></MemoryRouter>)
    await waitFor(() => expect(api.pendingIntake).toHaveBeenCalled())
    expect(screen.queryByRole("status")).toBeNull()
  })
})
