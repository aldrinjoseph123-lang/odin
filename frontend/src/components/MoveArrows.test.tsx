// @vitest-environment jsdom
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MoveArrows, type MoveDir } from "./MoveArrows"
import { StageListEditor, stageRowsKey, type StagePaths } from "./StageListEditor"

// One row of three, moved by its arrows; the "re-draw" drops focus the way a
// moved DOM node does in the browser.
function Row({ start, busy }: { start: number; busy?: boolean }) {
  const [i, setI] = useState(start)
  return <MoveArrows name="Design" first={i === 0} last={i === 2} busy={busy} onMove={(dir: MoveDir) => { (document.activeElement as HTMLElement | null)?.blur(); setI(i + (dir === "up" ? -1 : 1)) }} />
}

describe("MoveArrows", () => {
  it("gives focus back to the arrow that was pressed after the row moved", async () => {
    const user = userEvent.setup()
    render(<Row start={0} />)
    expect(screen.getByRole("button", { name: "Move Design up" })).toHaveAttribute("aria-disabled", "true")
    await user.click(screen.getByRole("button", { name: "Move Design down" }))
    await waitFor(() => expect(screen.getByRole("button", { name: "Move Design down" })).toHaveFocus())
  })

  it("moves focus to the other arrow when the row reaches an end", async () => {
    const user = userEvent.setup()
    render(<Row start={1} />)
    await user.click(screen.getByRole("button", { name: "Move Design down" }))   // now last: Down is disabled
    await waitFor(() => expect(screen.getByRole("button", { name: "Move Design up" })).toHaveFocus())
  })

  it("keeps focus while busy and ignores the press", async () => {
    const user = userEvent.setup()
    const onMove = vi.fn()
    render(<MoveArrows name="Design" first={false} last={false} busy onMove={onMove} />)
    const down = screen.getByRole("button", { name: "Move Design down" })
    down.focus()
    expect(down).toHaveFocus()
    expect(down).toHaveAttribute("aria-disabled", "true")
    await user.click(down)
    expect(onMove).not.toHaveBeenCalled()
  })
})

describe("StageListEditor", () => {
  const rows = [{ id: 1, name: "Scoping", sla_days: 3 }, { id: 2, name: "Build", sla_days: null }]
  const paths: StagePaths = { add: "/a", rename: (id) => `/r/${id}`, move: (id) => `/m/${id}`, remove: (id) => `/d/${id}`, sla: "/s" }

  it("keeps the same key when only the order changes, so a reorder does not remount the editor", () => {
    expect(stageRowsKey([...rows].reverse())).toBe(stageRowsKey(rows))
    expect(stageRowsKey([{ ...rows[0], name: "Scope" }, rows[1]])).not.toBe(stageRowsKey(rows))
  })

  it("posts the direction of the arrow pressed", async () => {
    const user = userEvent.setup()
    const send = vi.fn(async () => ({}))
    render(<StageListEditor rows={rows} busy={false} send={send} paths={paths} />)
    await user.click(screen.getByRole("button", { name: "Move Scoping down" }))
    expect(send).toHaveBeenCalledWith("/m/1", { direction: "down" })
  })
})
