// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DeclineDialog } from "./Users"
import type { AdminUser } from "@/lib/api"

const stan = { id: 7, name: "Stan Ger", username: "stan", email: "stan@corp.example" } as AdminUser

describe("Decline a sign-up", () => {
  it("sends the reason on one line and closes once it is saved", async () => {
    const user = userEvent.setup()
    const send = vi.fn(async () => true), onClose = vi.fn()
    render(<DeclineDialog u={stan} busy={false} send={send} onClose={onClose} />)
    await user.type(screen.getByLabelText(/Reason/), "not on the team")
    await user.click(screen.getByRole("button", { name: "Decline" }))
    expect(send).toHaveBeenCalledWith("/users/7/decline", { reason: "not on the team" })
    expect(onClose).toHaveBeenCalled()
  })

  it("declines without a reason, and caps it at 300 characters", async () => {
    const user = userEvent.setup()
    const send = vi.fn(async () => false)
    render(<DeclineDialog u={stan} busy={false} send={send} onClose={() => {}} />)
    expect(screen.getByLabelText(/Reason/)).toHaveAttribute("maxlength", "300")
    await user.click(screen.getByRole("button", { name: "Decline" }))
    expect(send).toHaveBeenCalledWith("/users/7/decline", { reason: "" })
  })
})
