import { settingsData } from "@/lib/api"
import type { PolicyRef } from "@/lib/settingsMenu"

// The names of every setting, fetched once for the palette and the Settings menu's
// filter (admins only: the server answers anyone else 403, and the list stays empty).
let cached: Promise<PolicyRef[]> | null = null
export function policyIndex(): Promise<PolicyRef[]> {
  cached ??= settingsData("general").then((d) => d.policies.map(({ key, area, label, group }) => ({ key, area, label, group }))).catch(() => { cached = null; return [] })
  return cached
}
