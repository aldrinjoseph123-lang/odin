// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { FieldInput, FieldValues } from "./FieldValues"
import { FieldsEditor } from "./FieldsEditor"
import { fieldInput, fieldText, fillPlaceholders } from "@/lib/format"
import type { CustomField, ProjectField } from "@/lib/api"

const def = (id: number, name: string, kind: CustomField["kind"], extra: Partial<CustomField> = {}): CustomField =>
  ({ id, name, kind, choices: kind === "choice" ? ["UAE", "KSA"] : [], required: false, customer_visible: false, show_in_list: false, position: id, ...extra })
const values: ProjectField[] = [
  { ...def(1, "Region", "choice"), value: "UAE" }, { ...def(2, "Seats", "number"), value: 1200 }, { ...def(3, "Live", "yesno"), value: true },
  { ...def(4, "Go-live", "date"), value: null }, { ...def(5, "Ticket", "text"), value: "CHG-1" },
]
const api = vi.hoisted(() => ({
  projectFields: vi.fn(), saveProjectFields: vi.fn(async () => ({ ok: true, changed: 1 })),
  customFields: vi.fn(), deleteField: vi.fn(async () => ({ ok: true })), createField: vi.fn(async () => ({ ok: true, id: 9 })),
}))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }))

describe("custom field values", () => {
  it("reads and holds each kind", () => {
    expect([fieldText("yesno", true), fieldText("yesno", false), fieldText("number", 1200), fieldText("text", null), fieldText("choice", "KSA")])
      .toEqual(["Yes", "No", "1,200", "—", "KSA"])
    expect([fieldInput("yesno", false), fieldInput("number", 4.5), fieldInput("date", null)]).toEqual(["no", "4.5", ""])
    expect(fillPlaceholders("In {field:Region} for {client}; {field:Nope}", { "field:Region": "UAE", client: "Globex" })).toBe("In UAE for Globex; {field:Nope}")
  })

  it("draws one control per kind", () => {
    for (const f of values) render(<FieldInput field={f} value={fieldInput(f.kind, f.value)} onChange={() => {}} />)
    expect(screen.getByRole("combobox", { name: "Region" })).toHaveValue("UAE")
    expect(screen.getByRole("spinbutton", { name: "Seats" })).toHaveValue(1200)
    expect(screen.getByRole("combobox", { name: "Live" })).toHaveValue("yes")
    expect(screen.getByRole("button", { name: "Go-live: not set" })).toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "Ticket" })).toHaveValue("CHG-1")
  })

  it("shows the filled values and saves an edit", async () => {
    api.projectFields.mockResolvedValue({ fields: values, can_edit: true })
    const user = userEvent.setup()
    render(<FieldValues projectId={7} />)
    expect(await screen.findByText("1,200")).toBeInTheDocument()
    expect(screen.queryByText("Go-live")).toBeNull()   // empty fields say nothing
    await user.click(screen.getByRole("button", { name: "Edit fields" }))
    await user.selectOptions(screen.getByRole("combobox", { name: "Region" }), "KSA")
    await user.click(screen.getByRole("button", { name: "Save fields" }))
    await waitFor(() => expect(api.saveProjectFields).toHaveBeenCalledWith(7, { 1: "KSA", 2: "1200", 3: "yes", 4: "", 5: "CHG-1" }))
  })

  it("offers no edit to whoever may not edit the rollout", async () => {
    api.projectFields.mockResolvedValue({ fields: values, can_edit: false })
    render(<FieldValues projectId={7} />)
    expect(await screen.findByText("UAE")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Edit fields" })).toBeNull()
  })
})

describe("FieldsEditor", () => {
  const kinds = { text: "Text", number: "Number", date: "Date", choice: "Choice", yesno: "Yes / no" }

  it("lists each field with its kind and flags, and deletes only on the typed name", async () => {
    api.customFields.mockResolvedValue({ fields: [def(1, "Region", "choice", { customer_visible: true, show_in_list: true }), def(2, "Seats", "number", { required: true })], kinds, max: 20 })
    const user = userEvent.setup()
    render(<FieldsEditor />)
    expect(await screen.findByText("Choice: UAE, KSA")).toBeInTheDocument()
    expect(screen.getByText("customers see it")).toBeInTheDocument()
    expect(screen.getByText("required")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Delete Seats" }))
    const go = screen.getByRole("button", { name: "Delete field" })
    expect(go).toHaveAttribute("aria-disabled", "true")
    await user.type(screen.getByRole("textbox", { name: /Type Seats to delete/ }), "Seats")
    expect(go).toHaveAttribute("aria-disabled", "false")
    await user.click(go)
    await waitFor(() => expect(api.deleteField).toHaveBeenCalledWith(2, "Seats"))
  })

  it("adds a choice field with its choices, and stops at the cap", async () => {
    api.customFields.mockResolvedValue({ fields: [], kinds, max: 1 })
    const user = userEvent.setup()
    const { unmount } = render(<FieldsEditor />)
    await user.click(await screen.findByRole("button", { name: "Add field" }))
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Region")
    await user.selectOptions(screen.getByRole("combobox", { name: "Kind" }), "choice")
    await user.type(screen.getByRole("textbox", { name: /Choices/ }), "UAE{Enter}KSA")
    await user.click(screen.getByRole("checkbox", { name: /Partners and customers see it/ }))
    await user.click(screen.getByRole("button", { name: "Save field" }))
    await waitFor(() => expect(api.createField).toHaveBeenCalledWith({ name: "Region", kind: "choice", choices: ["UAE", "KSA"], required: false, customer_visible: true, show_in_list: false }))
    unmount()
    api.customFields.mockResolvedValue({ fields: [def(1, "Region", "text")], kinds, max: 1 })
    render(<FieldsEditor />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Add field" })).toHaveAttribute("aria-disabled", "true"))
  })
})
