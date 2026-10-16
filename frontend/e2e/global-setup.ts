import { execFileSync } from "node:child_process"
import { existsSync, realpathSync, rmSync } from "node:fs"
import os from "node:os"
import path from "node:path"

// The data directory is deleted below, so it may only be a directory of its own
// inside a temp directory: an E2E_DATA_DIR pointing at a project, a home or the
// temp directory itself is refused rather than wiped.
export function safeDataDir(dir: string): string {
  const real = (p: string) => (existsSync(p) ? realpathSync(p) : path.resolve(p))
  const abs = path.resolve(dir)
  const target = path.join(real(path.dirname(abs)), path.basename(abs))   // /tmp is a link on macOS: compare real paths
  const temps = [os.tmpdir(), "/tmp"].map(real)
  const inside = temps.some((t) => target.startsWith(t + path.sep) && target !== t)
  if (!inside || !path.basename(target).startsWith("odin-e2e")) {
    throw new Error(`E2E_DATA_DIR ${dir} is not a temp directory named odin-e2e*: refusing to delete it`)
  }
  return target
}

// A fresh seeded data directory for every run: the seed refuses to touch one
// that already has a database, so the old one goes first.
export default function globalSetup() {
  const dir = safeDataDir(process.env.E2E_DATA_DIR ?? "/tmp/odin-e2e")
  if (existsSync(dir)) rmSync(dir, { recursive: true, force: true })
  const root = path.resolve(import.meta.dirname, "../..")
  const python = process.env.E2E_PYTHON ?? path.join(root, "venv/bin/python")
  execFileSync(existsSync(python) ? python : "python3", [path.join(root, "scripts/seed_uat.py")], {
    cwd: root, env: { ...process.env, ODIN_DATA_DIR: dir, SECRET_KEY: "e2e-not-secret" }, stdio: "pipe",
  })
}
