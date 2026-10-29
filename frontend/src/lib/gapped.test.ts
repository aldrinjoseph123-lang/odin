import { describe, expect, it } from "vitest"
import { gapped } from "./gapped"

describe("gapped", () => {
  it("skips while a load is in flight and within the gap, then runs again", async () => {
    let t = 0, calls = 0
    let finish: () => void = () => {}
    const run = gapped(() => { calls++; return new Promise<void>((r) => { finish = r }) }, 10_000, () => t)
    const first = run()
    t = 20_000
    await run()                  // still in flight: nothing
    expect(calls).toBe(1)
    finish(); await first
    t = 25_000
    const second = run()         // done, and the gap since its start has passed
    expect(calls).toBe(2)
    finish(); await second
    t = 30_000
    await run()                  // 5 s after the last start: inside the gap
    expect(calls).toBe(2)
  })
})
