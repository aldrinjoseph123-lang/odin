import { Fragment, Suspense, useEffect, useState } from "react"
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom"
import AppShell from "@/components/AppShell"
import { SettingsLayout } from "@/components/SettingsLayout"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import Flow from "@/pages/Flow"
import { LoadError } from "@/components/PageSkeleton"
import { lazyPage } from "@/lib/lazyPage"

// the dashboard carries the chart library: its own chunk, fetched on first visit
const Dashboard = lazyPage(() => import("@/pages/Dashboard"))
import { PageSkeleton } from "@/components/PageSkeleton"
import Projects from "@/pages/Projects"
import Project from "@/pages/Project"
import ProjectForm from "@/pages/ProjectForm"
import Account from "@/pages/Account"
import MyWork from "@/pages/MyWork"
import People from "@/pages/People"
import Person from "@/pages/Person"
import Alerts from "@/pages/Alerts"
// the admin pages: most people never open them, so they are not in the main bundle (advice A21)
const Users = lazyPage(() => import("@/pages/Users"))
const Audit = lazyPage(() => import("@/pages/Audit"))
const Workload = lazyPage(() => import("@/pages/Workload"))   // People › Workload
const Settings = lazyPage(() => import("@/pages/Settings"))
const Rbac = lazyPage(() => import("@/pages/Rbac"))
const Contacts = lazyPage(() => import("@/pages/Contacts"))
const Automations = lazyPage(() => import("@/pages/Automations"))   // Settings › Automations (manage_rules)
const Analytics = lazyPage(() => import("@/pages/Analytics"))
const ReportAll = lazyPage(() => import("@/pages/ReportAll"))
// the report carries the chart library too: its own chunk
const Report = lazyPage(() => import("@/pages/Report"))
const Signoff = lazyPage(() => import("@/pages/Signoff"))
import Login from "@/pages/Login"
import LinkRequest from "@/pages/LinkRequest"
import LinkContinue from "@/pages/LinkContinue"
const Join = lazyPage(() => import("@/pages/Join"))
import ForgotPassword from "@/pages/ForgotPassword"
import { newerVersion, reportClientError, session, type User } from "@/lib/api"
import { setDateFormat, setWorkspaceZone } from "@/lib/format"
import { setPrefUser } from "@/lib/usePref"
import { currentToasts, toast } from "@/lib/toast"

// errors no boundary sees (an event handler, a promise nobody awaited) reach the server's log too
window.addEventListener("error", (e) => reportClientError("error", e.error ?? e.message))
window.addEventListener("unhandledrejection", (e) => reportClientError("rejection", e.reason))

// a release landed while this tab was open: its code is older than the server's (advice A20).
// The toast stays until Reload or dismissed; pushed out by later toasts (or dismissed), the
// next session check (any navigation) shows it again: this tab still runs the old code.
let told = 0
function updated() {
  if (currentToasts().some((t) => t.id === told)) return
  told = toast("Odin was updated.", { action: { label: "Reload", run: () => window.location.reload() } })
}

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
  const [failed, setFailed] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => {
    // every navigation re-checks the session (it may have ended); a filter
    // change in the query does not (review P3-35). The user object is only
    // replaced when it changed, so the page does not re-render.
    session().then((s) => {
      if (!s.user) window.location.assign(`/login?next=${encodeURIComponent(pathname + window.location.search)}`)
      else if ((s.user.must_change_password || s.user.must_enroll_mfa) && pathname !== "/account") window.location.assign("/account")
      else {
        const next = s.user
        if (newerVersion(s.version)) updated()
        setDateFormat(next.prefs?.date_format)
        setWorkspaceZone(s.timezone)
        setPrefUser(next.id)
        setUser((prev) => prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next)
        if (s.messages?.length) setMessages(s.messages)
      }
    }).catch(() => setFailed(true))   // a page already shown keeps showing; a first load says so
  }, [pathname])
  if (!user && failed) return <main className="min-h-svh bg-background pt-8"><LoadError message="Odin is not answering just now (it may be restarting). Try again in a moment." /></main>
  if (!user) return null
  return <AppShell user={user} messages={messages} onDismiss={() => setMessages([])}>{children(user)}</AppShell>
}

// One record per address: a new :id (or a new ?from= on the form) mounts the
// page afresh, so nothing of the last record shows against the new one (review P3-35).
function Remount({ children, search = false }: { children: React.ReactNode; search?: boolean }) {
  const { pathname, search: q } = useLocation()
  return <Fragment key={pathname + (search ? q : "")}>{children}</Fragment>
}
const admin = (page: React.ReactNode) => <Suspense fallback={<PageSkeleton />}>{page}</Suspense>

// The last resort for pages outside the shell (sign-in, links); a signed-in
// page has its own boundary inside AppShell, so the nav stays.
function PageBoundary({ children }: { children: React.ReactNode }) {
  const { pathname, search } = useLocation()
  return <ErrorBoundary resetKey={pathname + search}>{children}</ErrorBoundary>
}

export default function App() {
  return (
    <BrowserRouter>
      <PageBoundary>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/login/password" element={<Login />} />
        <Route path="/auth/link" element={<LinkRequest />} />
        <Route path="/auth/link/:token" element={<LinkContinue />} />
        <Route path="/join/:token" element={<Suspense fallback={null}><Join /></Suspense>} />
        <Route path="/auth/reset" element={<ForgotPassword />} />
        <Route path="/auth/reset/:token" element={<ForgotPassword />} />
        <Route path="/board" element={<Protected>{(user) => <Flow user={user} />}</Protected>} />
        <Route path="/dashboard" element={<Protected>{(user) => user.kind === "external"
          ? <Navigate to="/board" replace />   /* partners always get the flow (test report UX-5: a bookmark showed a bare 403) */
          : <Suspense fallback={<PageSkeleton />}><Dashboard user={user} /></Suspense>}</Protected>} />
        <Route path="/projects" element={<Protected>{(user) => <Projects user={user} />}</Protected>} />
        <Route path="/projects/new" element={<Protected>{(user) => <Remount search><ProjectForm user={user} /></Remount>}</Protected>} />
        <Route path="/projects/:id/edit" element={<Protected>{(user) => <Remount><ProjectForm user={user} /></Remount>}</Protected>} />
        <Route path="/projects/:id/signoff" element={<Protected>{(user) => <Suspense fallback={<PageSkeleton />}><Signoff user={user} /></Suspense>}</Protected>} />
        <Route path="/projects/:id/report" element={<Protected>{(user) => <Suspense fallback={<PageSkeleton />}><Report user={user} /></Suspense>}</Protected>} />
        <Route path="/reports/all" element={<Protected>{(user) => <Suspense fallback={<PageSkeleton />}><ReportAll user={user} /></Suspense>}</Protected>} />
        <Route path="/projects/:id" element={<Protected>{(user) => <Remount><Project user={user} /></Remount>}</Protected>} />
        <Route path="/users" element={<Protected>{(user) => <SettingsLayout user={user}>{admin(<Users user={user} />)}</SettingsLayout>}</Protected>} />
        <Route path="/audit-logs" element={<Protected>{(user) => <SettingsLayout user={user}>{admin(<Audit user={user} />)}</SettingsLayout>}</Protected>} />
        <Route path="/account" element={<Protected>{(user) => <Account user={user} />}</Protected>} />
        <Route path="/my-work" element={<Protected>{(user) => <MyWork user={user} />}</Protected>} />
        <Route path="/people" element={<Protected>{(user) => <People user={user} />}</Protected>} />
        <Route path="/people/workload" element={<Protected>{(user) => <Workload user={user} />}</Protected>} />
        <Route path="/people/:id" element={<Protected>{(user) => <Remount><Person user={user} /></Remount>}</Protected>} />
        <Route path="/alerts" element={<Protected>{(user) => <Alerts user={user} />}</Protected>} />
        <Route path="/analytics" element={<Protected>{(user) => admin(<Analytics user={user} />)}</Protected>} />
        <Route path="/settings" element={<Navigate to="/settings/general" replace />} />
        <Route path="/settings/rbac" element={<Protected>{(user) => <SettingsLayout user={user}>{admin(<Rbac user={user} />)}</SettingsLayout>}</Protected>} />
        <Route path="/settings/contacts" element={<Protected>{(user) => <SettingsLayout user={user}>{admin(<Contacts user={user} />)}</SettingsLayout>}</Protected>} />
        <Route path="/settings/automations" element={<Protected>{(user) => <SettingsLayout user={user}>{admin(<Automations user={user} />)}</SettingsLayout>}</Protected>} />
        <Route path="/settings/:section" element={<Protected>{(user) => <SettingsLayout user={user}>{admin(<Settings user={user} />)}</SettingsLayout>}</Protected>} />
        <Route path="*" element={<HandOffToFlask />} />
      </Routes>
      </PageBoundary>
    </BrowserRouter>
  )
}
