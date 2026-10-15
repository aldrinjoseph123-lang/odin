import { Component, type ErrorInfo, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { reportClientError } from "@/lib/api"

// A render error in one page must not blank the whole app. The boundary
// shows a way out, keeps the error in the console and sends it to the server's log.
// `resetKey` (the address) clears the error when the person navigates away;
// `inShell` draws it inside AppShell's main, under the nav.
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string; inShell?: boolean }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidUpdate(prev: { resetKey?: string }) { if (this.state.failed && prev.resetKey !== this.props.resetKey) this.setState({ failed: false }) }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("Odin page error", error, info.componentStack); reportClientError("render", error) }
  render() {
    if (!this.state.failed) return this.props.children
    const Wrap = this.props.inShell ? "div" : "main"
    return (
      <Wrap className={cn("flex items-center justify-center p-6", this.props.inShell ? "flex-1" : "min-h-svh bg-background text-foreground")}>
        <div className="w-full max-w-md rounded-xl border border-border bg-card p-8 text-center">
          <div className="text-[12px] text-muted-foreground">Something went wrong</div>
          <h1 className="mt-1 text-[24px] font-semibold tracking-tight">This page hit an error</h1>
          <p className="mt-2 text-[13px] text-muted-foreground">Nothing you saved was lost. Reload to try again; if it keeps happening, tell an admin what you were doing.</p>
          <div className="mt-5 flex justify-center gap-2">
            <button type="button" onClick={() => window.location.reload()} className="h-8 rounded-lg bg-primary px-3 text-[13px] font-medium text-primary-foreground">Reload</button>
            <a href="/board" className="inline-flex h-8 items-center panel px-3 text-[13px] font-medium hover:bg-muted">Back to the flow</a>
          </div>
        </div>
      </Wrap>
    )
  }
}
