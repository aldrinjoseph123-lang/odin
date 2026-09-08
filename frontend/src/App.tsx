import { BrowserRouter, Route, Routes } from "react-router-dom"
import Login from "@/pages/Login"

// Strangler router: only ported pages are listed. Anything else is a Jinja
// page, so hand the URL back to Flask with a real navigation.
function HandOffToFlask() {
  window.location.replace(window.location.pathname + window.location.search)
  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<HandOffToFlask />} />
      </Routes>
    </BrowserRouter>
  )
}
