// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { WhatsNew } from "./WhatsNew"

const api = vi.hoisted(() => ({ whatsNew: vi.fn(), whatsNewSeen: vi.fn(async () => ({ ok: true })) }))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), whatsNew: api.whatsNew, whatsNewSeen: api.whatsNewSeen }))

describe("WhatsNew", () => {
  it("shows the release's changes once and remembers Got it", async () => {
    api.whatsNew.mockResolvedValue({ show: true, version: "2.0.0", title: "Odin 2.0", items: ["Daily summaries", "Calendar feed"] })
    const user = userEvent.setup()
    render(<WhatsNew staff />)
    const card = await screen.findByRole("region", { name: "What's new in Odin 2.0.0" })
    expect(card).toHaveTextContent("Daily summaries")
    await user.click(screen.getByRole("button", { name: "Got it" }))
    expect(api.whatsNewSeen).toHaveBeenCalled()
    expect(screen.queryByRole("region")).toBeNull()
  })

  it("says nothing when already seen, and never asks for partners", async () => {
    api.whatsNew.mockClear().mockResolvedValue({ show: false, version: "2.0.0", title: "", items: [] })
    const { rerender } = render(<WhatsNew staff />)
    await waitFor(() => expect(api.whatsNew).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole("region")).toBeNull()
    api.whatsNew.mockClear()
    rerender(<WhatsNew staff={false} key="x" />)
    expect(api.whatsNew).not.toHaveBeenCalled()
  })
})
