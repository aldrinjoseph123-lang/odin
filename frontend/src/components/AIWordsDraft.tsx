import { AIDraftBar } from "@/components/AIDraftBar"
import type { WeeklyWordsDraft } from "@/lib/api"

type Words = { summary: string; next_steps: string; asks: string }

// The weekly words on the report page: the AI draft fills the three boxes.
export function AIWordsDraft({ projectId, onUse }: { projectId: number; onUse: (w: Words, suggestion: number) => void }) {
  return (
    <AIDraftBar<WeeklyWordsDraft> projectId={projectId} feature="weekly_words"
      idle="Draft the summary, next steps and asks with AI from this week's notes, plan and risks."
      working="Drafting from this week's notes, plan and risks… about a minute."
      note="It fills the three boxes for you to edit; the customer copy uses the same words."
      onUse={(s) => onUse({ summary: s.payload.summary, next_steps: s.payload.next_steps.join("\n"), asks: s.payload.asks.join("\n") }, s.id)} />
  )
}
