import { Suspense, lazy, useEffect, useState } from "react"
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom"
import AppShell from "@/components/AppShell"
import { SettingsLayout } from "@/components/SettingsLayout"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import Flow from "@/pages/Flow"
// the dashboard carries the chart library: its own chunk, fetched on first visit
const Dashboard = lazy(() => import("@/pages/Dashboard"))
import { PageSkeleton } from "@/components/PageSkeleton"
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
import People from "@/pages/People"
import Person from "@/pages/Person"
import Alerts from "@/pages/Alerts"
import Analytics from "@/pages/Analytics"
import ReportAll from "@/pages/ReportAll"
import Report from "@/pages/Report"
import Login from "@/pages/Login"
import LinkRequest from "@/pages/LinkRequest"
import LinkContinue from "@/pages/LinkContinue"
import ForgotPassword from "@/pages/ForgotPassword"
import { session, type User } from "@/lib/api"
import { setDateFormat } from "@/lib/format"

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
  const [messages, setMessages] = useState<string[]>([])
  const { pathname, search } = useLocation()
  useEffect(() => {
    session().then((s) => {
      if (!s.user) window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`)
      else if (s.user.must_change_password && pathname !== "/account") window.location.assign("/account")
      else { setDateFormat(s.user.prefs?.date_format); setUser(s.user); if (s.messages?.length) setMessages(s.messages) }
    })
  }, [pathname, search])
  if (!user) return null
  return <AppShell user={user} messages={messages} onDismiss={() => setMessages([])}>{children(user)}</AppShell>
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/login/password" element={<Login />} />
        <Route path="/auth/link" element={<LinkRequest />} />
        <Route path="/auth/link/:token" element={<LinkContinue />} />
        <Route path="/auth/reset" element={<ForgotPassword />} />
        <Route path="/auth/reset/:token" element={<ForgotPassword />} />
        <Route path="/board" element={<Protected>{(user) => <Flow user={user} />}</Protected>} />
        <Route path="/dashboard" element={<Protected>{(user) => <Suspense fallback={<PageSkeleton />}><Dashboard user={user} /></Suspense>}</Protected>} />
        <Route path="/projects" element={<Protected>{(user) => <Projects user={user} />}</Protected>} />
        <Route path="/projects/new" element={<Protected>{(user) => <ProjectForm user={user} />}</Protected>} />
        <Route path="/projects/:id/edit" element={<Protected>{(user) => <ProjectForm user={user} />}</Protected>} />
        <Route path="/projects/:id/report" element={<Protected>{(user) => <Report user={user} />}</Protected>} />
        <Route path="/reports/all" element={<Protected>{(user) => <ReportAll user={user} />}</Protected>} />
        <Route path="/projects/:id" element={<Protected>{(user) => <Project user={user} />}</Protected>} />
        <Route path="/users" element={<Protected>{(user) => <SettingsLayout user={user}><Users user={user} /></SettingsLayout>}</Protected>} />
        <Route path="/audit-logs" element={<Protected>{(user) => <SettingsLayout user={user}><Audit user={user} /></SettingsLayout>}</Protected>} />
        <Route path="/account" element={<Protected>{(user) => <Account user={user} />}</Protected>} />
        <Route path="/my-work" element={<Protected>{(user) => <MyWork user={user} />}</Protected>} />
        <Route path="/people" element={<Protected>{(user) => <People user={user} />}</Protected>} />
        <Route path="/people/:id" element={<Protected>{(user) => <Person user={user} />}</Protected>} />
        <Route path="/alerts" element={<Protected>{(user) => <Alerts user={user} />}</Protected>} />
        <Route path="/analytics" element={<Protected>{(user) => <Analytics user={user} />}</Protected>} />
        <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
        <Route path="/settings/rbac" element={<Protected>{(user) => <SettingsLayout user={user}><Rbac user={user} /></SettingsLayout>}</Protected>} />
        <Route path="/settings/contacts" element={<Protected>{(user) => <SettingsLayout user={user}><Contacts user={user} /></SettingsLayout>}</Protected>} />
        <Route path="/settings/:section" element={<Protected>{(user) => <SettingsLayout user={user}><Settings user={user} /></SettingsLayout>}</Protected>} />
        <Route path="*" element={<HandOffToFlask />} />
      </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
