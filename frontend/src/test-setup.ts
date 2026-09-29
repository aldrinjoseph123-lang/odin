import "@testing-library/jest-dom/vitest"
import { afterEach, vi } from "vitest"
import { cleanup } from "@testing-library/react"

// jsdom has no layout: the pieces the pages measure with get quiet stand-ins.
class RO { observe() {} unobserve() {} disconnect() {} }
Object.defineProperty(globalThis, "ResizeObserver", { value: RO, writable: true })
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({ matches: query.includes("min-width"), media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false }),
})
Element.prototype.scrollIntoView = () => {}
Element.prototype.getAnimations = () => []
afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.clear() })
