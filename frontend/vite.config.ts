import path from "node:path"

import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// Dev: Vite serves the React pages (a browser navigation gets index.html) and
// proxies everything else to Flask on 5050: the API, form posts, downloads and
// the few server pages (guest links, Microsoft sign-in, the system map). The
// session cookie is shared (same host, cookies ignore port).
// Build: emits frontend/dist, which Flask serves for every page route.
const SERVER_PAGES = /^\/(guest|auth\/microsoft|integrations|settings\/map\/page|logout|healthz|robots\.txt)|\/(download|avatar)\b|\.(csv|pdf|svg|png)(\?|$)/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    proxy: {
      "^/(?!@|src/|node_modules/).*": {
        target: "http://127.0.0.1:5050", changeOrigin: false,
        bypass: (req) => req.method === "GET" && req.headers.accept?.includes("text/html") && !SERVER_PAGES.test(req.url ?? "") ? "/index.html" : undefined,
      },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
  // vitest: pure helpers run in node; page tests (*.test.tsx) render in jsdom
  test: {
    projects: [
      { extends: true, test: { name: "unit", include: ["src/**/*.test.ts"], environment: "node" } },
      { extends: true, test: { name: "ui", include: ["src/**/*.test.tsx"], environment: "jsdom", setupFiles: ["./src/test-setup.ts"], css: false } },
    ],
  },
})
