// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AsksPanel } from "./AsksPanel"
import * as api from "@/lib/api"

const base = { done: false, done_at: null, due_date: null, assignee: "Ann Reyes", assignee_role: "Customer", category: null, questions: [], answers: [], answered_by: null, answered_at: null, file: null }
const data: api.AsksData = {
  ratings: [],
  asks: [
    { ...base, id: 1, title: "Confirm the change window", kind: "task", due_date: "2026-10-01" },
    { ...base, id: 2, title: "Upload the network diagram", kind: "upload", category: "Deliverable" },
    { ...base, id: 3, title: "Tell us about your environment", kind: "form",
      questions: [{ key: "q1", label: "Endpoints", kind: "number" }, { key: "q2", label: "SSO in place?", kind: "yesno" }, { key: "q3", label: "Notes", kind: "text", required: false }] },
  ],
}

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  asks: vi.fn(async () => data),
  toggleTask: vi.fn(async () => ({ ok: true, done: true })),
  answerAsk: vi.fn(async () => ({ ok: true })),
  uploadAsk: vi.fn(async () => ({ ok: true, messages: [], undo: null, location: null })),
}))

describe("What we need from you", () => {
  it("does each ask in place: a tick, a file, a form that waits for its required answers", async () => {
    const user = userEvent.setup()
    render(<AsksPanel projectId={7} staff={false} today="2026-10-16" />)
    expect(await screen.findByRole("region", { name: "What we need from you" })).toHaveTextContent("3 open")
    expect(screen.getByText(/overdue · due/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Mark done" }))
    expect(api.toggleTask).toHaveBeenCalledWith(7, 1, true)
    const file = new File(["%PDF-1.4"], "diagram.pdf", { type: "application/pdf" })
    await user.upload(screen.getByLabelText("File for Upload the network diagram"), file)
    await user.click(screen.getByRole("button", { name: "Upload" }))
    expect(api.uploadAsk).toHaveBeenCalledWith(7, 2, file)
    const send = screen.getByRole("button", { name: "Send answers" })
    expect(send).toHaveAttribute("aria-disabled", "true")   // the Button keeps focus while it waits
    expect(screen.getByText("Still to answer: Endpoints, SSO in place?")).toBeInTheDocument()
    await user.type(screen.getByRole("spinbutton", { name: "Endpoints" }), "1200")
    await user.selectOptions(screen.getByRole("combobox", { name: "SSO in place?" }), "yes")
    await user.click(send)
    await waitFor(() => expect(api.answerAsk).toHaveBeenCalledWith(7, 3, { q1: "1200", q2: "yes" }))
  })

  it("shows staff what came back and the rating at sign-off", async () => {
    vi.mocked(api.asks).mockResolvedValueOnce({
      ratings: [{ signoff_version: 1, rating: 4, comment: "Smooth cutover", by_name: "Ann Reyes", at: "2026-10-10T09:00:00" }],
      asks: [{ ...data.asks[2], done: true, answered_by: "Ann Reyes", answered_at: "2026-10-09T09:00:00", answers: [{ key: "q1", label: "Endpoints", value: "1200" }, { key: "q2", label: "SSO in place?", value: "yes" }] }],
    })
    render(<AsksPanel projectId={7} staff today="2026-10-16" />)
    const panel = await screen.findByRole("region", { name: "Asked of the customer and partners" })
    expect(panel).toHaveTextContent("by Ann Reyes")
    expect(panel).toHaveTextContent("SSO in place?Yes")
    expect(panel).toHaveTextContent("4 of 5")
    expect(panel).toHaveTextContent("Smooth cutover")
  })
})
