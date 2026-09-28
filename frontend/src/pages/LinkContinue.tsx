import { useEffect, useState } from "react"
import { AuthLayout } from "@/components/Brand"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { session } from "@/lib/api"

// Opening an emailed sign-in link lands here, not in the app: mail security
// scanners open links too, and a link that signed in on open would be spent
// before its owner clicked it. The button posts the same address, which is
// what signs in (and keeps ?next, so a project link lands on the project).
export default function LinkContinue() {
  const [csrf, setCsrf] = useState<string | null>(null)
  useEffect(() => {
    document.title = "Sign in · Odin"
    session().then((s) => setCsrf(s.csrf)).catch(() => setCsrf(""))
  }, [])
  return (
    <AuthLayout>
      <Card className="w-full max-w-sm">
        <CardHeader><CardTitle className="text-[20px] font-bold tracking-tight">Your sign-in link</CardTitle></CardHeader>
        <CardContent>
          <p className="mb-4 text-[13px] text-muted-foreground">The link works once. Continue to sign in to Odin on this device.</p>
          <form method="post" action={window.location.pathname + window.location.search}>
            <input type="hidden" name="_csrf" value={csrf ?? ""} />
            <Button type="submit" className="w-full" disabled={!csrf} autoFocus>Continue to Odin</Button>
          </form>
          <p className="mt-4 text-center text-[12.5px] text-muted-foreground">Link expired? <a href="/auth/link" className="text-primary-text hover:underline">Request a new one</a></p>
        </CardContent>
      </Card>
    </AuthLayout>
  )
}
