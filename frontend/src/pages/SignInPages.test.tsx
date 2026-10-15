// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import ForgotPassword from "./ForgotPassword"
import LinkContinue from "./LinkContinue"
import { ApiError } from "@/lib/api"

const api = vi.hoisted(() => ({ session: vi.fn(), postForm: vi.fn() }))
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), session: api.session, postForm: api.postForm }))

describe("ForgotPassword", () => {
  it("reads the password length from the session, and a refused reset is an alert with a way to a new link", async () => {
    api.session.mockResolvedValue({ csrf: "t", user: null, signin: { microsoft: false, microsoft_only: false, link_minutes: 30, password_min_length: 16 } })
    api.postForm.mockRejectedValue(new ApiError(400, "That reset link is invalid or has expired"))
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={["/auth/reset/abc"]}><Routes><Route path="/auth/reset/:token" element={<ForgotPassword />} /></Routes></MemoryRouter>)
    expect(await screen.findByText(/At least 16 characters/)).toBeInTheDocument()
    expect(screen.getByLabelText("New password")).toHaveAttribute("minlength", "16")
    await user.type(screen.getByLabelText("New password"), "a-long-enough-password-1")
    await user.click(screen.getByRole("button", { name: "Set password" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired")
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/auth/reset")
  })
})

describe("LinkContinue", () => {
  it("a failed session check says so and the retry enables Continue", async () => {
    api.session.mockRejectedValueOnce(new ApiError(502, "down")).mockResolvedValue({ csrf: "tok", user: null })
    const user = userEvent.setup()
    render(<LinkContinue />)
    expect(await screen.findByRole("alert")).toHaveTextContent("has not been used")
    expect(screen.getByRole("button", { name: "Continue to Odin" })).toBeDisabled()
    await user.click(screen.getByRole("button", { name: "Try again" }))
    expect(await screen.findByRole("button", { name: "Continue to Odin" })).toBeEnabled()
  })
})
