import { describe, expect, it } from "vitest"
import { SIGNED_OUT, failureText } from "./api"

describe("failureText", () => {
  it("says what went wrong and what to do, never a bare status (test report UX-6)", () => {
    expect(failureText(0)).toMatch(/connection/)
    expect(failureText(401)).toBe(SIGNED_OUT)
    expect(failureText(404)).toMatch(/^Not found/)
    expect(failureText(500)).toMatch(/Try again/)
    expect(failureText(503)).toBe(failureText(500))
    expect(failureText(418)).toMatch(/error 418\)\. Reload/)
    for (const s of [0, 400, 401, 403, 404, 413, 429, 500]) expect(failureText(s)).not.toMatch(/Request failed/)
  })
})
