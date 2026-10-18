// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { PendingDoc } from "./DocReview"

afterEach(cleanup)
const doc = { filename: "diagram.pdf", uploaded_by: "Ann Reyes" }

describe("A file held for review", () => {
  it("warns, offers no link, and sends the decision with a confirm only for a reject", async () => {
    const decide = vi.fn(async () => null)
    render(<ul><li><PendingDoc doc={doc} canReview onDecide={decide} /></li></ul>)
    expect(screen.getByText("Uploaded by Ann Reyes · not reviewed yet")).toBeInTheDocument()
    expect(screen.queryByRole("link")).toBeNull()
    await userEvent.click(screen.getByRole("button", { name: "Accept diagram.pdf" }))
    expect(decide).toHaveBeenLastCalledWith("accept", undefined)
    await userEvent.click(screen.getByRole("button", { name: "Reject diagram.pdf" }))
    expect(decide).toHaveBeenLastCalledWith("reject", expect.stringContaining("Ann Reyes is asked to upload it again"))
  })

  it("shows no buttons to someone who does not manage the documents", () => {
    render(<ul><li><PendingDoc doc={doc} canReview={false} onDecide={async () => null} /></li></ul>)
    expect(screen.queryByRole("button")).toBeNull()
  })
})
