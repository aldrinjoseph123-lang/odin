import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Tag } from "@/components/ui/tag"

// A file an outside party uploaded waits for staff review (services/doc_review.py):
// it cannot be opened until someone who manages the rollout's documents accepts it.
// Reject deletes it and asks them to upload again.
export function PendingDoc({ doc, canReview, onDecide }: {
  doc: { filename: string; uploaded_by: string }
  canReview: boolean
  onDecide: (decision: "accept" | "reject", confirmText?: string) => Promise<unknown>
}) {
  const [working, setWorking] = useState<"accept" | "reject" | null>(null)
  const decide = (decision: "accept" | "reject", confirmText?: string) => {
    if (working) return
    setWorking(decision)
    void onDecide(decision, confirmText).finally(() => setWorking(null))
  }
  return (
    <>
      <span className="min-w-0 flex-1 truncate font-medium" title="Not reviewed yet: accept it to open it">{doc.filename}</span>
      <Tag kind="warn">Uploaded by {doc.uploaded_by} · not reviewed yet</Tag>
      {canReview && (
        <span className="flex shrink-0 gap-2">
          <Button size="sm" loading={working === "accept"} onClick={() => decide("accept")} aria-label={`Accept ${doc.filename}`}>Accept</Button>
          <Button size="sm" variant="outline" loading={working === "reject"} aria-label={`Reject ${doc.filename}`}
            onClick={() => decide("reject", `Reject ${doc.filename}? The file is deleted and ${doc.uploaded_by} is asked to upload it again.`)}>Reject</Button>
        </span>
      )}
    </>
  )
}
