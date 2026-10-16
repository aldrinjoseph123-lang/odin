import type { AdminUser } from "./api"

export type UserFilter = { q: string; role: string; status: "all" | "active" | "inactive"; review: boolean }
export const noFilter: UserFilter = { q: "", role: "", status: "all", review: false }

// The Users list narrowed by the box (name, username, email, role words), the
// role and status pickers, and the access review (accounts the server flagged).
export function filterUsers(people: AdminUser[], f: UserFilter): AdminUser[] {
  const words = f.q.toLowerCase().split(/\s+/).filter(Boolean)
  return people.filter((u) => {
    if (f.review && !u.review.length) return false
    if (f.status !== "all" && u.active !== (f.status === "active")) return false
    if (f.role && (u.kind === "external" ? "External" : u.role) !== f.role) return false
    const hay = [u.name, u.username, u.email ?? "", u.kind === "external" ? "external" : u.role, u.active ? "active" : "deactivated"].join(" ").toLowerCase()
    return words.every((w) => hay.includes(w))
  })
}
