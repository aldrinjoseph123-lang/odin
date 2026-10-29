// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { NotificationBell } from "./NotificationBell"

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  notifications: vi.fn(async () => ({ unread: 0, rows: [] })),
}))
import { notifications } from "@/lib/api"

describe("NotificationBell", () => {
  it("asks once when the tab comes back, not again for the window's focus (sim B2)", async () => {
    render(<MemoryRouter><NotificationBell initialUnread={0} /></MemoryRouter>)
    window.dispatchEvent(new Event("focus"))
    expect(notifications).not.toHaveBeenCalled()
    document.dispatchEvent(new Event("visibilitychange"))
    await waitFor(() => expect(notifications).toHaveBeenCalledTimes(1))
  })
})
