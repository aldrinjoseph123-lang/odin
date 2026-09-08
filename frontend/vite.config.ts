import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// Dev: Vite serves the React pages and proxies everything it doesn't own to
// Flask on 5050, so un-ported Jinja pages keep working during the strangler
// migration and the session cookie is shared (same host, cookies ignore port).
// Build: emits frontend/dist, which Flask serves for the ported routes.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    proxy: {
      "^/(?!@|src/|node_modules/|assets/|login$).*": { target: "http://127.0.0.1:5050", changeOrigin: false },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
})
