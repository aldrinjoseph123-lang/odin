// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Account from "./Account"
import { ConfirmHost } from "@/components/ConfirmHost"
import { admin } from "./fixtures"
import { applyTheme } from "@/lib/theme"

const me = {
  username: "admin", name: "Admin User", email: "a@x.com", kind: "internal", must_change_password: false, has_password: true, theme: "light", accent: "blue",
  avatar_url: "/avatar/1", email_kinds: [{ key: "stage", label: "Stage changes", on: true, mode: "instant" }, { key: "task", label: "Tasks", on: false, mode: "off" }], mail_enabled: true, home: "dashboard",
  calendar: { created_at: null as string | null, last_read_at: null as string | null, idle_days: 30 },
  activity: null, activity_viewers: [],
}
const api = vi.hoisted(() => ({ postForm: vi.fn(), makeCalendarFeed: vi.fn() }))
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  account: vi.fn(async () => me), accountEmail: vi.fn(async () => ({ verified: true, checkable: false })), accountMicrosoft: vi.fn(async () => ({ available: false, linked: false })),
  twoStep: vi.fn(async () => ({ password: false })), postForm: api.postForm, makeCalendarFeed: api.makeCalendarFeed,
}))

const page = (prefs = { date_format: "dmy", undo_minutes: 5, password_min_length: 16 }) => {
  applyTheme("light", "blue")   // what the shell paints from the session before this page opens
  return render(<MemoryRouter><Account user={{ ...admin, prefs } as typeof admin} /><ConfirmHost /></MemoryRouter>)
}

describe("Account", () => {
  it("Save for the notifications wakes only when a choice differs from what is saved, and sends each kind's choice", async () => {
    api.postForm.mockResolvedValue({ messages: ["Notification settings saved"] })
    const user = userEvent.setup()
    page()
    const save = (await screen.findByText("Tell me about")).closest("form")!.querySelector("button[type=submit]") as HTMLButtonElement
    expect(save).toHaveAttribute("aria-disabled", "true")
    const tasks = screen.getByRole("radiogroup", { name: "Tasks" })
    await user.click(within(tasks).getByRole("radio", { name: "Daily summary" }))
    expect(save).toHaveAttribute("aria-disabled", "false")
    await user.click(within(tasks).getByRole("radio", { name: "Off" }))
    expect(save).toHaveAttribute("aria-disabled", "true")
    await user.click(within(tasks).getByRole("radio", { name: "Daily summary" }))
    await user.click(save)
    expect(api.postForm).toHaveBeenCalledWith("/account/notifications", { stage: "instant", task: "summary" })
  })

  it("makes a calendar feed and shows its address once", async () => {
    api.makeCalendarFeed.mockResolvedValue({ ok: true, url: "https://odin.example/feeds/calendar/abc.ics" })
    const user = userEvent.setup()
    page()
    await user.click(await screen.findByRole("button", { name: "Make a feed" }))
    expect(await screen.findByLabelText("Calendar feed address")).toHaveValue("https://odin.example/feeds/calendar/abc.ics")
  })

  it("says when the feed was last read and that an unused one switches off", async () => {
    const { account } = await import("@/lib/api")
    vi.mocked(account).mockResolvedValue({ ...me, calendar: { created_at: "2026-10-01T08:00:00", last_read_at: "2026-10-16T08:00:00", idle_days: 30 } } as never)
    page()
    expect(await screen.findByText(/Last read .+\. Switches off if unused for 30 days\./)).toBeInTheDocument()
    vi.mocked(account).mockResolvedValue({ ...me, calendar: { created_at: "2026-10-01T08:00:00", last_read_at: null, idle_days: 0 } } as never)
    cleanup()
    page()
    expect(await screen.findByText(/Not read yet\./)).toBeInTheDocument()
    expect(screen.queryByText(/Switches off/)).toBeNull()   // 0 = never
    vi.mocked(account).mockImplementation(async () => me as never)
  })

  it("takes the password length from the session and shows a refusal beside the form", async () => {
    api.postForm.mockRejectedValue(new Error("x"))
    const user = userEvent.setup()
    page()
    const field = await screen.findByLabelText("New password")
    expect(field).toHaveAttribute("minlength", "16")
    expect(screen.getByText(/At least 16 characters/)).toBeInTheDocument()
    expect(screen.queryByText("That did not save")).toBeNull()
    await user.type(screen.getByLabelText("Current password"), "old")
    await user.type(field, "sixteen-chars-long-1")
    await user.click(screen.getByRole("button", { name: "Update password" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("That did not save")
  })

  it("re-picking the current theme sends nothing, and Remove asks first", async () => {
    api.postForm.mockClear()
    const user = userEvent.setup()
    page()
    await user.click(await screen.findByRole("radio", { name: "Light" }))
    expect(api.postForm).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "Remove" }))
    expect(await screen.findByText(/Remove your picture\?/)).toBeInTheDocument()
    expect(api.postForm).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: "Cancel" }))
    expect(api.postForm).not.toHaveBeenCalled()
  })

  it("Upload with no file says to choose one", async () => {
    const user = userEvent.setup()
    page()
    await user.click(await screen.findByRole("button", { name: "Upload" }))
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a picture first")
  })
})
