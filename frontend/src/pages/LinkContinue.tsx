import { useCallback, useEffect, useState } from "react"
import { AuthHeading, AuthLayout } from "@/components/Brand"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { session } from "@/lib/api"

// Opening an emailed sign-in link lands here, not in the app: mail security
// scanners open links too, and a link that signed in on open would be spent
// before its owner clicked it. The button posts the same address, which is
// what signs in (and keeps ?next, so a project link lands on the project).
// An address-check link (?verify=1) uses the same page: the button proves the
// address, and a scanner's open proves nothing (review P2-3).
export default function LinkContinue() {
  const [csrf, setCsrf] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)   // the session check failed: say so, and offer the retry (review P3-39)
  const verify = new URLSearchParams(window.location.search).has("verify")
  const check = useCallback(() => { setFailed(false); session().then((s) => setCsrf(s.csrf)).catch(() => setFailed(true)) }, [])
  useEffect(() => {
    document.title = verify ? "Confirm your email · Odin" : "Sign in · Odin"
    check()
  }, [verify, check])
  return (
    <AuthLayout>
      {verify
        ? <AuthHeading title="Confirm your email address">The link works once. Confirm that this address is yours.</AuthHeading>
        : <AuthHeading title="Your sign-in link">The link works once. Continue to sign in to Odin on this device.</AuthHeading>}
      {failed && (
        <Alert variant="destructive" className="mb-5"><AlertDescription className="flex flex-wrap items-center gap-3">
          <span className="min-w-0 flex-1">Odin did not answer, so the link has not been used. Try again in a moment.</span>
          <Button type="button" size="sm" variant="outline" onClick={check}>Try again</Button>
        </AlertDescription></Alert>
      )}
      <form method="post" action={window.location.pathname + window.location.search}>
        <input type="hidden" name="_csrf" value={csrf ?? ""} />
        <Button type="submit" className="h-11 w-full text-sm" disabled={!csrf} autoFocus>{verify ? "Confirm my address" : "Continue to Odin"}</Button>
      </form>
      {!verify && <p className="mt-6 text-[14px] text-muted-foreground">Link expired? <a href="/auth/link" className="text-primary-text hover:underline">Request a new one</a></p>}
    </AuthLayout>
  )
}
