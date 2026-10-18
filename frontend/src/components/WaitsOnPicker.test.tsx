// @vitest-environment jsdom
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { WaitsOnPicker, type WaitOption } from "./WaitsOnPicker"

const OPTIONS: WaitOption[] = [{ id: 1, title: "Order sensors" }, { id: 2, title: "Confirm window" }]

function Host({ start = [] as number[], options = OPTIONS }) {
  const [v, setV] = useState(start)
  return <><WaitsOnPicker options={options} value={v} onChange={setV} /><output>{v.join(",")}</output></>
}

describe("WaitsOnPicker", () => {
  it("adds a task, offers only the ones left, and removes a chip", async () => {
    const user = userEvent.setup()
    render(<Host />)
    await user.selectOptions(screen.getByRole("combobox", { name: "Waits on" }), "Order sensors")
    expect(screen.getByRole("status")).toHaveTextContent("1")
    expect(screen.getByText("Order sensors")).toBeInTheDocument()
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["And waits on…", "Confirm window"])
    await user.selectOptions(screen.getByRole("combobox", { name: "Waits on" }), "Confirm window")
    expect(screen.getByRole("status")).toHaveTextContent("1,2")
    expect(screen.queryByRole("combobox")).toBeNull()   // nothing left to pick
    await user.click(screen.getByRole("button", { name: "No longer waits on Order sensors" }))
    expect(screen.getByRole("status")).toHaveTextContent("2")
  })

  it("shows nothing when the rollout has no other task", () => {
    const { container } = render(<WaitsOnPicker options={[]} value={[]} onChange={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("drops an id that is no longer among the options (a deleted task)", () => {
    render(<Host start={[9, 2]} />)
    expect(screen.queryAllByRole("button", { name: /^No longer waits on/ }).map((b) => b.getAttribute("aria-label"))).toEqual(["No longer waits on Confirm window"])
  })
})
