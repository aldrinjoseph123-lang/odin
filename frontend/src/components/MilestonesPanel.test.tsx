// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MilestonesPanel } from "./MilestonesPanel"
import { Toaster } from "./Toaster"
import type { Milestone, MilestonesData } from "@/lib/api"

const m = (id: number, name: string, date: string, extra: Partial<Milestone> = {}): Milestone =>
  ({ id, project_id: 4, name, date, stage: null, customer_visible: false, done: false, done_at: null, missed: false, created_by: "Priya", created_at: "2026-10-01T08:00:00", ...extra })
const data = (extra: Partial<MilestonesData> = {}): MilestonesData => ({
  items: [
    m(1, "Pilot go-live", "2026-10-20", { customer_visible: true, stage: "Deployment" }),
    m(2, "Security review", "2026-10-10", { missed: true }),
    m(3, "Kick-off held", "2026-10-02", { done: true, done_at: "2026-10-02T09:00:00" }),
  ],
  stages: ["Scoping", "Deployment"], can_edit: true, can_delete: true, ...extra,
})
const api = vi.hoisted(() => ({ milestones: vi.fn(), saveMilestone: vi.fn(async () => ({ ok: true, id: 9 })), deleteMilestone: vi.fn(async () => ({ ok: true })) }))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }))
const ask = vi.hoisted(() => ({ askConfirm: vi.fn(async () => true) }))
vi.mock("@/lib/confirm", () => ask)

const mount = () => render(<><MilestonesPanel projectId={4} /><Toaster /></>)

// the clock is frozen: 14 Oct 2026, local noon (the page reads the device's calendar)
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date(2026, 9, 14, 12)); vi.clearAllMocks(); api.milestones.mockResolvedValue(data()) })
afterEach(() => { cleanup(); vi.useRealTimers() })

describe("MilestonesPanel", () => {
  it("lists what is open with the missed one in words, and the reached ones under All", async () => {
    const user = userEvent.setup()
    mount()
    expect(await screen.findByText("Pilot go-live")).toBeInTheDocument()
    expect(screen.getByText("1 missed")).toBeInTheDocument()
    expect(screen.getByText("1 of 3 reached")).toBeInTheDocument()
    expect(screen.getByText("4 d late · 10 Oct")).toBeInTheDocument()
    expect(screen.getByText(/^Missed/)).toBeInTheDocument()
    expect(screen.getByLabelText("Shown to the customer")).toBeInTheDocument()   // only the go-live
    expect(screen.queryByText("Kick-off held")).toBeNull()
    await user.click(screen.getByRole("radio", { name: "All" }))
    expect(screen.getByText("Kick-off held")).toBeInTheDocument()
    expect(screen.getByText(/Reached 2 Oct/)).toBeInTheDocument()
  })

  it("marks one reached from the row, and reopens a reached one", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Mark Pilot go-live reached" }))
    await waitFor(() => expect(api.saveMilestone).toHaveBeenCalledWith(4, { name: "Pilot go-live", date: "2026-10-20", stage: "Deployment", customer_visible: true, done: true }, 1))
    expect(await screen.findByText("Pilot go-live: reached")).toBeInTheDocument()   // the toast
    await user.click(screen.getByRole("radio", { name: "All" }))
    await user.click(screen.getByRole("button", { name: "Reopen Kick-off held" }))
    await waitFor(() => expect(api.saveMilestone).toHaveBeenLastCalledWith(4, { name: "Kick-off held", date: "2026-10-02", stage: null, customer_visible: false, done: false }, 3))
  })

  it("adds a milestone: name, a day from the calendar, a stage, and whether the customer sees it", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole("button", { name: "Add" }))
    const save = screen.getByRole("button", { name: "Save" })
    expect(save).toHaveAttribute("aria-disabled", "true")
    await user.type(screen.getByRole("textbox", { name: "Name" }), "UAT sign-off")
    await user.click(screen.getByRole("button", { name: "Date: not set" }))
    await user.click((await screen.findAllByRole("button", { name: /October 28th, 2026/ })).at(-1)!)
    await user.selectOptions(screen.getByRole("combobox", { name: "Stage" }), "Deployment")
    await user.click(screen.getByRole("checkbox", { name: /Show to the customer/ }))
    await user.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(api.saveMilestone).toHaveBeenCalledWith(4, { name: "UAT sign-off", date: "2026-10-28", stage: "Deployment", customer_visible: true }, undefined))
    expect(await screen.findByText("Milestone added")).toBeInTheDocument()
  })

  it("edits and deletes; the server's refusal stays in the dialog", async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText("Security review"))
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-disabled", "true")   // nothing changed yet
    await user.type(screen.getByRole("textbox", { name: "Name" }), " v2")
    const { ApiError } = await import("@/lib/api")
    api.saveMilestone.mockRejectedValueOnce(new ApiError(400, "Pick one of this rollout's stages, or none"))
    await user.click(screen.getByRole("button", { name: "Save" }))
    expect(await screen.findByText("Pick one of this rollout's stages, or none")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Delete" }))
    await waitFor(() => expect(api.deleteMilestone).toHaveBeenCalledWith(4, 2))
    expect(ask.askConfirm).toHaveBeenCalled()
  })

  it("a reader who may not edit sees the list and no controls; a coordinator cannot delete", async () => {
    api.milestones.mockResolvedValue(data({ can_edit: false, can_delete: false }))
    mount()
    expect(await screen.findByText("Pilot go-live")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull()
    expect(screen.queryByRole("button", { name: /reached$/ })).toBeNull()
    cleanup()
    api.milestones.mockResolvedValue(data({ can_delete: false }))
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByText("Pilot go-live"))
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull()
  })
})
