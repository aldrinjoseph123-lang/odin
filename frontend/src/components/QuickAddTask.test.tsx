// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QuickAddTask } from "./QuickAddTask"
import * as api from "@/lib/api"
import type { WorkProject } from "@/lib/api"

vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), addTask: vi.fn(async () => ({ ok: true, id: 9 })) }))

const p = (id: number, name: string, stage: string, can_add_task: boolean) => ({ id, name, stage, can_add_task }) as WorkProject & { can_add_task: boolean }

describe("Quick-add a task on My work", () => {
  beforeEach(() => vi.mocked(api.addTask).mockClear())

  it("adds to the picked rollout's current stage, assigned to me, then clears", async () => {
    const user = userEvent.setup(), added = vi.fn()
    render(<QuickAddTask projects={[p(1, "Alpha", "Survey", true), p(2, "Beta", "Install", true)]} me={7} onAdded={added} />)
    await user.selectOptions(screen.getByLabelText("Rollout for the new task"), "2")
    await user.type(screen.getByLabelText("New task title"), "  Book the crane ")
    await user.click(screen.getByRole("button", { name: /Add$/ }))
    expect(api.addTask).toHaveBeenCalledWith(2, { title: "Book the crane", stage: "Install", assignee_id: 7, due_date: null })
    expect(added).toHaveBeenCalled()
    expect(screen.getByLabelText("New task title")).toHaveValue("")
  })

  it("offers only rollouts the person may add tasks to, and nothing when there are none", () => {
    const { container, rerender } = render(<QuickAddTask projects={[p(1, "Alpha", "Survey", true), p(2, "Beta", "Install", false)]} me={7} onAdded={() => {}} />)
    expect(screen.queryByLabelText("Rollout for the new task")).toBeNull()   // one choice left: no picker
    rerender(<QuickAddTask projects={[p(2, "Beta", "Install", false)]} me={7} onAdded={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
})
