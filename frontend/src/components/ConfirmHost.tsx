import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { answerConfirm, confirmParts, useConfirmAsk } from "@/lib/confirm"

// The one confirm dialog (see lib/confirm.ts); mounted once, beside the toasts.
export function ConfirmHost() {
  const ask = useConfirmAsk()
  const p = ask ? confirmParts(ask.text) : null
  return (
    <Dialog open={!!ask} onOpenChange={(o) => { if (!o) answerConfirm(false) }}>
      <DialogContent className="sm:max-w-md" role="alertdialog">
        {p && <>
          <DialogHeader><DialogTitle>{p.title}</DialogTitle>{p.detail && <DialogDescription>{p.detail}</DialogDescription>}</DialogHeader>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => answerConfirm(false)} autoFocus>Cancel</Button>
            <Button size="sm" variant={p.danger ? "destructive" : "default"} onClick={() => answerConfirm(true)} data-confirm-yes>{ask?.action ?? p.verb}</Button>
          </div>
        </>}
      </DialogContent>
    </Dialog>
  )
}
