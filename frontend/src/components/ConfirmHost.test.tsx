// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ConfirmHost } from "./ConfirmHost"
import { askConfirm, askReason } from "@/lib/confirm"

afterEach(cleanup)

describe("askReason", () => {
  it("keeps the destructive button shut under the minimum and answers with the trimmed text", async () => {
    render(<ConfirmHost />)
    const answer = askReason("Delete this signed-off project? The admins are told.", "Delete project", { min: 10, max: 1000 })
    const go = await screen.findByRole("button", { name: "Delete project" })
    expect(go).toHaveAttribute("aria-disabled", "true")
    await userEvent.click(go)   // refused: still open
    expect(screen.getByRole("textbox", { name: "Reason" })).toBeInTheDocument()
    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "  Duplicate of rollout 7 ")
    expect(go).not.toHaveAttribute("aria-disabled", "true")
    await userEvent.click(go)
    expect(await answer).toBe("Duplicate of rollout 7")
  })

  it("answers null on cancel", async () => {
    render(<ConfirmHost />)
    const answer = askReason("Delete this signed-off project? Told.", "Delete project", { min: 10, max: 1000 })
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }))
    expect(await answer).toBeNull()
  })

  it("leaves the plain confirm without a text box", async () => {
    render(<ConfirmHost />)
    const answer = askConfirm("Delete this note? It leaves the history.")
    expect(await screen.findByRole("button", { name: "Delete" })).not.toHaveAttribute("aria-disabled", "true")
    expect(screen.queryByRole("textbox")).toBeNull()
    await userEvent.click(screen.getByRole("button", { name: "Delete" }))
    expect(await answer).toBe(true)
  })
})
