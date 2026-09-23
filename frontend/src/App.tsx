import { useEffect, useState } from "react"
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom"
import AppShell from "@/components/AppShell"
import Flow from "@/pages/Flow"
import Projects from "@/pages/Projects"
import Project from "@/pages/Project"
import Users from "@/pages/Users"
import Audit from "@/pages/Audit"
import Settings from "@/pages/Settings"
import Rbac from "@/pages/Rbac"
import Contacts from "@/pages/Contacts"
import ProjectForm from "@/pages/ProjectForm"
import Account from "@/pages/Account"
import MyWork from "@/pages/MyWork"
import Alerts from "@/pages/Alerts"
import Analytics from "@/pages/Analytics"
import ReportAll from "@/pages/ReportAll"
import Report from "@/pages/Report"
import Login from "@/pages/Login"
import { session, type User } from "@/lib/api"

// Strangler router: only ported pages are listed. Anything else is a Jinja
// page, so hand the URL back to Flask with a real navigation.
function HandOffToFlask() {
  window.location.replace(window.location.pathname + window.location.search)
  return null
}

// Signed-in pages. No session → the login page (Flask's own rule, mirrored);
// pending password change → the account page, exactly as the Flask gate does.
function Protected({ children }: { children: (user: User) => React.ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const { pathname, search } = useLocation()
  useEffect(() => {
    session().then((s) => {
      if (!s.user) window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`)
      else if (s.user.must_change_password && pathname !== "/account") window.location.assign("/account")
      else setUser(s.user)
    })
  }, [pathname, search])
  if (!user) return null
  return <AppShell user={user}>{children(user)}</AppShell>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/board" element={<Protected>{(user) => <Flow user={user} />}</Protected>} />
        <Route path="/projects" element={<Protected>{(user) => <Projects user={user} />}</Protected>} />
        <Route path="/projects/new" element={<Protected>{(user) => <ProjectForm user={user} />}</Protected>} />
        <Route path="/projects/:id/edit" element={<Protected>{(user) => <ProjectForm user={user} />}</Protected>} />
        <Route path="/projects/:id/report" element={<Protected>{(user) => <Report user={user} />}</Protected>} />
        <Route path="/reports/all" element={<Protected>{(user) => <ReportAll user={user} />}</Protected>} />
        <Route path="/projects/:id" element={<Protected>{(user) => <Project user={user} />}</Protected>} />
        <Route path="/users" element={<Protected>{(user) => <Users user={user} />}</Protected>} />
        <Route path="/audit-logs" element={<Protected>{(user) => <Audit user={user} />}</Protected>} />
        <Route path="/account" element={<Protected>{(user) => <Account user={user} />}</Protected>} />
        <Route path="/my-work" element={<Protected>{(user) => <MyWork user={user} />}</Protected>} />
        <Route path="/alerts" element={<Protected>{(user) => <Alerts user={user} />}</Protected>} />
        <Route path="/analytics" element={<Protected>{(user) => <Analytics user={user} />}</Protected>} />
        <Route path="/settings" element={<Protected>{(user) => <Settings user={user} />}</Protected>} />
        <Route path="/settings/rbac" element={<Protected>{(user) => <Rbac user={user} />}</Protected>} />
        <Route path="/settings/contacts" element={<Protected>{(user) => <Contacts user={user} />}</Protected>} />
        <Route path="*" element={<HandOffToFlask />} />
      </Routes>
    </BrowserRouter>
  )
}
