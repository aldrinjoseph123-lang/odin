// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { HandOverDialog } from "./HandOverDialog"
import type { AdminUser } from "@/lib/api"

const lee = { id: 5, name: "Lee Park", holds: { tasks: 2, rollouts: 1, raid: 3 } } as AdminUser
const hana = { id: 6, name: "Hana Ito", role: "Member" } as AdminUser

describe("Hand over on leave", () => {
  it("says what the person holds and hands it to the colleague in the same step", async () => {
    const user = userEvent.setup()
    const send = vi.fn(async () => true), onClose = vi.fn()
    render(<HandOverDialog u={lee} colleagues={[hana]} busy={false} send={send} onClose={onClose} />)
    expect(screen.getByText(/2 open tasks, 1 rollout they manage, 3 RAID items/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText("Hand over to"), "6")
    await user.click(screen.getByRole("button", { name: "Hand over and deactivate" }))
    expect(send).toHaveBeenCalledWith("/users/5/active", { active: "0", handover_to: "6" }, undefined, expect.any(Function))
    expect(onClose).toHaveBeenCalledWith(true)
  })

  it("deactivates without moving anything when nobody is picked, and stays open on a refusal", async () => {
    const user = userEvent.setup()
    const send = vi.fn(async (_p: string, _f: Record<string, string>, _c?: string, onError?: (m: string) => void) => { onError?.("Hana cannot manage rollouts"); return false }), onClose = vi.fn()
    render(<HandOverDialog u={lee} colleagues={[hana]} busy={false} send={send} onClose={onClose} />)
    await user.click(screen.getByRole("button", { name: "Deactivate" }))
    expect(send.mock.calls[0][1]).toEqual({ active: "0" })
    expect(await screen.findByText("Hana cannot manage rollouts")).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onClose).toHaveBeenCalledWith(false)
  })
})
