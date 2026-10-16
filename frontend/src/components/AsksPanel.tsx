import { useRef, useState } from "react"
import { Check, FileUp, Star } from "lucide-react"
import { Panel } from "@/components/PanelTitle"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Field } from "@/components/ui/field"
import { Tag } from "@/components/ui/tag"
import { Notice } from "@/components/Notice"
import { FieldInput } from "@/components/FieldValues"
import { answerAsk, asks as loadAsks, toggleTask, uploadAsk, type Ask, type AskQuestion } from "@/lib/api"
import { useLoad } from "@/lib/useLoad"
import { useAction } from "@/lib/useAction"
import { fmtDate, fmtWhen } from "@/lib/format"
import { cn } from "@/lib/utils"

// Customer self-service (services/asks.py). An outside party (a customer,
// reseller or contractor) sees "What we need from you" at the top of their
// rollout: their own asks only, each done in place: a tick, a file into the
// asked category, or a short form the server checks question by question.
// Staff see every ask on the rollout with what came back, and the ratings
// given at sign-off.

const KIND_WORD = { task: "To do", upload: "Upload", form: "Form" } as const

function answerText(q: Pick<AskQuestion, "kind">, value: string) {
  if (q.kind === "yesno") return value === "yes" ? "Yes" : "No"
  if (q.kind === "date") return fmtDate(value)
  return value
}

function Due({ ask, today }: { ask: Ask; today: string }) {
  if (!ask.due_date || ask.done) return null
  const late = ask.due_date < today
  return <span className={cn("text-[12px]", late ? "font-medium text-bad" : "text-muted-foreground")}>{late ? "overdue · " : ""}due {fmtDate(ask.due_date)}</span>
}

function AskForm({ ask, busy, onSubmit }: { ask: Ask; busy: boolean; onSubmit: (answers: Record<string, string>) => void }) {
  const [v, setV] = useState<Record<string, string>>(() => Object.fromEntries(ask.answers.map((a) => [a.key, a.value])))
  const missing = ask.questions.filter((q) => q.required !== false && !(v[q.key!] ?? "").trim()).map((q) => q.label)
  return (
    <form className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); onSubmit(v) }}>
      {ask.questions.map((q) => (
        <Field key={q.key} label={`${q.label}${q.required === false ? " (optional)" : ""}`}>
          <FieldInput field={{ name: q.label, kind: q.kind, choices: q.choices ?? [] }} value={v[q.key!] ?? ""} onChange={(x) => setV({ ...v, [q.key!]: x })} />
        </Field>
      ))}
      <div className="flex items-center gap-2 sm:col-span-2">
        <Button type="submit" size="sm" loading={busy} disabled={missing.length > 0} aria-describedby={missing.length ? `ask-${ask.id}-missing` : undefined}>Send answers</Button>
        {missing.length > 0 && <span id={`ask-${ask.id}-missing`} className="text-[12px] text-muted-foreground">Still to answer: {missing.join(", ")}</span>}
      </div>
    </form>
  )
}

function AskUpload({ ask, busy, onUpload }: { ask: Ask; busy: boolean; onUpload: (f: File) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  return (
    <form className="mt-2 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (file) onUpload(file) }}>
      <Input ref={input} type="file" aria-label={`File for ${ask.title}`} className="h-auto w-auto max-w-full py-1 text-[13px]" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <Button type="submit" size="sm" loading={busy} disabled={!file}><FileUp className="h-3.5 w-3.5" /> Upload</Button>
      <span className="text-[12px] text-muted-foreground">Filed under {ask.category}</span>
    </form>
  )
}

// What came back: the answers, or the file
function Given({ ask, projectId }: { ask: Ask; projectId: number }) {
  if (ask.kind === "upload" && ask.file) return <p className="mt-1 text-[12px] text-muted-foreground">Uploaded <a className="text-primary-text hover:underline" href={`/projects/${projectId}/documents/${ask.file.id}/download`}>{ask.file.filename}</a>{ask.answered_at && ` ${fmtWhen(ask.answered_at)}`}</p>
  if (ask.kind !== "form" || ask.answers.length === 0) return null
  const byKey = Object.fromEntries(ask.questions.map((q) => [q.key, q]))
  return (
    <dl className="mt-2 grid grid-cols-[minmax(96px,auto)_minmax(0,1fr)] gap-x-4 gap-y-1 text-[13px] [&_dd]:min-w-0 [&_dd]:break-words">
      {ask.answers.map((a) => <div key={a.key} className="contents"><dt className="text-muted-foreground">{a.label}</dt><dd>{answerText(byKey[a.key] ?? { kind: "text" }, a.value)}</dd></div>)}
    </dl>
  )
}

export function AsksPanel({ projectId, staff, today, onChanged }: { projectId: number; staff: boolean; today: string; onChanged?: () => unknown }) {
  const { data, reload } = useLoad(`asks:${projectId}`, () => loadAsks(projectId))
  const { busy, note, act } = useAction(async () => { await reload(); await onChanged?.() })
  const [working, setWorking] = useState<number | null>(null)
  const [showDone, setShowDone] = useState(false)
  if (!data || (data.asks.length === 0 && data.ratings.length === 0)) return null
  const open = data.asks.filter((a) => !a.done), done = data.asks.filter((a) => a.done)
  const run = (id: number, fn: () => Promise<unknown>, said: string) => { setWorking(id); void act(fn, said).finally(() => setWorking(null)) }

  if (!staff) return (
    <Panel title="What we need from you" hint={open.length ? `${open.length} open` : "all done, thank you"} id="asks">
      <ul className="grid grid-cols-1 gap-3">
        {[...open, ...(showDone ? done : [])].map((a) => (
          <li key={a.id} className="rounded-lg bg-muted/50 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Tag kind="role">{KIND_WORD[a.kind]}</Tag>
              <span className={cn("min-w-0 flex-1 text-[14px] font-medium", a.done && "text-muted-foreground")}>{a.title}</span>
              <Due ask={a} today={today} />
              {a.done && <span className="flex items-center gap-1 text-[12px] text-ok"><Check className="h-3.5 w-3.5" /> Done</span>}
              {!a.done && a.kind === "task" && <Button size="sm" variant="outline" loading={busy && working === a.id} onClick={() => run(a.id, () => toggleTask(projectId, a.id, true), `Done: ${a.title}`)}>Mark done</Button>}
            </div>
            {!a.done && a.kind === "upload" && <AskUpload ask={a} busy={busy && working === a.id} onUpload={(f) => run(a.id, () => uploadAsk(projectId, a.id, f), `Uploaded for ${a.title}. Thank you.`)} />}
            {!a.done && a.kind === "form" && <AskForm ask={a} busy={busy && working === a.id} onSubmit={(v) => run(a.id, () => answerAsk(projectId, a.id, v), `Answers sent for ${a.title}. Thank you.`)} />}
            {a.done && <Given ask={a} projectId={projectId} />}
          </li>
        ))}
        {open.length === 0 && !showDone && <li className="text-[13px] text-muted-foreground">Nothing is waiting on you right now.</li>}
      </ul>
      {done.length > 0 && <button type="button" onClick={() => setShowDone(!showDone)} className="mt-2 text-[12px] text-muted-foreground hover:text-foreground">{showDone ? "Hide finished" : `${done.length} finished`}</button>}
      {note && <Notice bad={note.bad} className="mt-2">{note.text}</Notice>}
    </Panel>
  )

  return (
    <Panel title="Asked of the customer and partners" hint="what each outside party was asked, and what came back" id="asks">
      <ul className="grid grid-cols-1 gap-2">
        {data.asks.map((a) => (
          <li key={a.id} className="border-b border-border pb-2 text-[13px] last:border-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-2">
              <Tag kind="role">{KIND_WORD[a.kind]}</Tag>
              <span className={cn("min-w-0 flex-1 font-medium", a.done && "text-muted-foreground")}>{a.title}</span>
              <span className="text-muted-foreground">{a.assignee} · {a.assignee_role}</span>
              <Due ask={a} today={today} />
              {a.done && <span className="flex items-center gap-1 text-[12px] text-ok"><Check className="h-3.5 w-3.5" /> {a.answered_by ? `by ${a.answered_by}` : "Done"}</span>}
            </div>
            <Given ask={a} projectId={projectId} />
          </li>
        ))}
      </ul>
      {data.ratings.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <h3 className="mb-2 text-[12px] font-semibold text-nav-fg">Rating at sign-off</h3>
          <ul className="grid grid-cols-1 gap-1 text-[13px]">
            {data.ratings.map((r) => (
              <li key={r.signoff_version} className="flex flex-wrap items-baseline gap-2">
                <span className="flex items-center gap-1 font-medium"><Star className="h-3.5 w-3.5" aria-hidden /> {r.rating} of 5</span>
                <span className="text-muted-foreground">{r.by_name}, version {r.signoff_version}, {fmtWhen(r.at)}</span>
                {r.comment && <span className="w-full">{r.comment}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}
