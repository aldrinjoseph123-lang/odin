import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { answerConfirm, confirmParts, useConfirmAsk } from "@/lib/confirm"
import { fieldArea } from "@/lib/ui"

// The one confirm dialog (see lib/confirm.ts); mounted once, beside the toasts.
export function ConfirmHost() {
  const ask = useConfirmAsk()
  const p = ask ? confirmParts(ask.text) : null
  const [reason, setReason] = useState("")
  const need = ask?.reason?.min ?? 0
  const short = reason.trim().length < need
  return (
    <Dialog open={!!ask} onOpenChange={(o) => { if (!o) { answerConfirm(false); setReason("") } }}>
      <DialogContent className="sm:max-w-md" role="alertdialog">
        {p && <>
          <DialogHeader><DialogTitle>{p.title}</DialogTitle>{p.detail && <DialogDescription>{p.detail}</DialogDescription>}</DialogHeader>
          {ask?.reason && <textarea rows={3} maxLength={ask.reason.max} value={reason} onChange={(e) => setReason(e.target.value)} className={fieldArea} aria-label="Reason" placeholder="Why is this being deleted?" />}
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => { answerConfirm(false); setReason("") }} autoFocus>Cancel</Button>
            <Button size="sm" variant={p.danger ? "destructive" : "default"} disabled={short} onClick={() => { answerConfirm(true, reason.trim()); setReason("") }} data-confirm-yes>{ask?.action ?? p.verb}</Button>
          </div>
        </>}
      </DialogContent>
    </Dialog>
  )
}
