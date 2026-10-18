// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { submitKey } from "./useSubmitShortcut"

function Form({ onSend, required }: { onSend: () => void; required?: boolean }) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSend() }} onKeyDown={submitKey}>
      <textarea aria-label="Message" required={required} />
      <button type="submit">Send</button>
    </form>
  )
}

describe("Ctrl/⌘ Enter sends the form (B5)", () => {
  it("submits from a textarea with Ctrl or Meta, once", async () => {
    const user = userEvent.setup(), send = vi.fn()
    render(<Form onSend={send} />)
    await user.type(screen.getByLabelText("Message"), "hello")
    await user.keyboard("{Control>}{Enter}{/Control}")
    await user.keyboard("{Meta>}{Enter}{/Meta}")
    expect(send).toHaveBeenCalledTimes(2)
  })
  it("leaves a plain Enter to the textarea", async () => {
    const user = userEvent.setup(), send = vi.fn()
    render(<Form onSend={send} />)
    await user.type(screen.getByLabelText("Message"), "a{Enter}b")
    expect(send).not.toHaveBeenCalled()
  })
  it("still runs the form's own checks", async () => {
    const user = userEvent.setup(), send = vi.fn()
    render(<Form onSend={send} required />)
    await user.click(screen.getByLabelText("Message"))
    await user.keyboard("{Control>}{Enter}{/Control}")
    expect(send).not.toHaveBeenCalled()
  })
})
