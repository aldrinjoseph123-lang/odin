// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { WatchButton } from "./WatchButton"

const api = vi.hoisted(() => ({ setWatch: vi.fn() }))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), setWatch: api.setWatch }))

describe("WatchButton", () => {
  it("a participant mutes and unmutes", async () => {
    api.setWatch.mockResolvedValueOnce({ can: "mute", on: true }).mockResolvedValueOnce({ can: "mute", on: false })
    const user = userEvent.setup()
    render(<WatchButton projectId={4} watch={{ can: "mute", on: false }} />)
    await user.click(screen.getByRole("button", { name: "Mute updates" }))
    expect(api.setWatch).toHaveBeenLastCalledWith(4, true)
    await user.click(await screen.findByRole("button", { name: "Unmute updates" }))
    expect(api.setWatch).toHaveBeenLastCalledWith(4, false)
  })

  it("staff not on it follow; nobody else sees a button", () => {
    const { rerender } = render(<WatchButton projectId={4} watch={{ can: "follow", on: true }} />)
    expect(screen.getByRole("button", { name: "Unfollow" })).toBeInTheDocument()
    rerender(<WatchButton key="n" projectId={4} watch={{ can: null, on: false }} />)
    expect(screen.queryByRole("button")).toBeNull()
  })
})
