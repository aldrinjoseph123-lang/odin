import { execFileSync } from "node:child_process"
import { existsSync, rmSync } from "node:fs"
import path from "node:path"

// A fresh seeded data directory for every run: the seed refuses to touch one
// that already has a database, so the old one goes first.
export default function globalSetup() {
  const dir = process.env.E2E_DATA_DIR ?? "/tmp/odin-e2e"
  if (existsSync(dir)) rmSync(dir, { recursive: true, force: true })
  const root = path.resolve(import.meta.dirname, "../..")
  const python = process.env.E2E_PYTHON ?? path.join(root, "venv/bin/python")
  execFileSync(existsSync(python) ? python : "python3", [path.join(root, "scripts/seed_uat.py")], {
    cwd: root, env: { ...process.env, ODIN_DATA_DIR: dir, SECRET_KEY: "e2e-not-secret" }, stdio: "pipe",
  })
}
