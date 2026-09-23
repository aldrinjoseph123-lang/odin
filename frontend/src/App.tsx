import { useEffect, useState } from "react"
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom"
import AppShell from "@/components/AppShell"
import Flow from "@/pages/Flow"
import Projects from "@/pages/Projects"
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
      else if (s.user.must_change_password) window.location.assign("/account")
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
        <Route path="*" element={<HandOffToFlask />} />
      </Routes>
    </BrowserRouter>
  )
}
