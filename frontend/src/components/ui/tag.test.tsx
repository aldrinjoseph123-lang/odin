import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Tag } from "./tag"

describe("Tag", () => {
  it("colours a scope status or an impact by its level, and nothing else", () => {
    render(<>
      <Tag kind="scope" level="delivered">Delivered</Tag>
      <Tag kind="impact" level="high">high</Tag>
      <Tag kind="role">Admin</Tag>
      <Tag kind="scope" level="unheard-of">?</Tag>
    </>)
    expect(screen.getByText("Delivered").className).toContain("bg-ok-soft")
    expect(screen.getByText("high").className).toContain("bg-warn-soft")   // amber, never red: red means overdue
    expect(screen.getByText("Admin").className).not.toMatch(/-soft/)
    expect(screen.getByText("?").className).toContain("bg-muted")
  })

  it("renders as a link when asked (a source)", () => {
    render(<Tag kind="source" render={<a href="/x">Plan</a>} />)
    expect(screen.getByRole("link", { name: "Plan" }).className).toContain("border-border")
  })
})
