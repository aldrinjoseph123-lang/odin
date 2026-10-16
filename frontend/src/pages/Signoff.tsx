import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { PanelTitle } from "@/components/PanelTitle"
import { StatusPill } from "@/components/PlanGantt"
import { toast } from "@/lib/toast"
import { field, filterSelect, pill, fieldArea, checkbox } from "@/lib/ui"
import { askConfirm } from "@/lib/confirm"
import { AIDraftBar } from "@/components/AIDraftBar"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { CheckCircle2, ChevronLeft, Copy, Download, FileSignature, Link2, Printer, ShieldCheck, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Field } from "@/components/ui/field"
import { Notice } from "@/components/Notice"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PrintBrand } from "@/components/Brand"
import { LoadError, PageSkeleton } from "@/components/PageSkeleton"
import { Section } from "@/components/ReportParts"
import { SCOPE_TONE, SCOPE_WORD } from "@/components/ScopePanel"
import { SignaturePad, SignatureView } from "@/components/SignaturePad"
import {
  ApiError, rejectSignoff, sendSignoff, signoff, signoffLink, signSignoff, uploadSignoff, waiveSignoff, withdrawSignoff,
  type Signature, type SignoffContent, type SignoffData, type SignoffStatus, type SignoffVersion, type User, type SignoffLink,
} from "@/lib/api"
import { useUnsavedGuard } from "@/lib/useUnsavedGuard"
import { copyWithToast } from "@/lib/copy"
import { useLoad } from "@/lib/useLoad"
import { TemplatePicker } from "@/components/TemplatePicker"
import { cn } from "@/lib/utils"
import { DatePicker } from "@/components/DatePicker"
import { fmtDate, fmtWhen, localToday, signoffText, toLines } from "@/lib/format"

// The sign-off: the last step of a rollout. The project manager prepares it
// (the scope item by item, or what was delivered; what is outstanding; the
// handover terms) and sends it; that freezes the version and its fingerprint.
// The customer's named signatory reviews, then signs or says what must change;
// we countersign; then the project can close. A signed paper copy can stand in,
// and an admin can waive it with a reason. The server decides who may do what.
const area = cn(fieldArea, "p-3 text-[14px]")   // a document to sign reads at 14 px
const TONE: Record<SignoffStatus, string> = {
  sent: "bg-warn-soft text-warn", signed: "bg-warn-soft text-warn", countersigned: "bg-ok-soft text-ok", uploaded: "bg-ok-soft text-ok",
  waived: "bg-muted text-muted-foreground", rejected: "bg-bad-soft text-bad", withdrawn: "bg-muted text-muted-foreground",
}

const SignoffPill = ({ status }: { status: SignoffStatus | null }) => <StatusPill tone={status ? TONE[status] : "bg-muted text-muted-foreground"}>{signoffText(status)}</StatusPill>

function Facts({ p }: { p: SignoffContent["project"] }) {
  const rows: [string, ReactNode][] = [
    ["Customer", p.client], ["Delivered by", `${p.company}${p.partner_name ? ` with ${p.partner_name}` : ""}`],
    ["Purchase order", [p.po_number, p.po_date && fmtDate(p.po_date)].filter(Boolean).join(" · ") || "—"], ["Project manager", p.owner_name],
    ["Solution", [p.vendor_name, p.product_name].filter(Boolean).join(" ") || "—"], ["Started", fmtDate(p.start_date)],
    ["Target", fmtDate(p.target_end_date)], ["Issued", fmtDate(p.finished)],
  ]
  return <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-2">{rows.map(([k, v]) => <div key={k} className="grid grid-cols-[120px_minmax(0,1fr)] gap-2"><dt className="text-muted-foreground">{k}</dt><dd className="min-w-0 break-words">{v}</dd></div>)}</dl>
}

function ScopeTable({ items }: { items: { title: string; detail: string | null; status: keyof typeof SCOPE_WORD; note: string | null }[] }) {
  return (
    <ol className="divide-y divide-border text-[13px]">
      {items.map((x, i) => (
        <li key={i} className="flex items-start gap-3 py-2">
          <span className="w-5 shrink-0 text-right text-[12px] tabular-nums text-muted-foreground">{i + 1}</span>
          <span className="min-w-0 flex-1"><span className={cn("block font-medium", x.status === "descoped" && "text-muted-foreground line-through")}>{x.title}</span>
            {(x.detail || x.note) && <span className="block text-[12px] text-muted-foreground">{[x.detail, x.note].filter(Boolean).join(" · ")}</span>}</span>
          <span className={cn("shrink-0 rounded-full px-2 py-1 text-[11px] font-medium", SCOPE_TONE[x.status].replace("line-through", ""))}>{SCOPE_WORD[x.status]}</span>
        </li>
      ))}
    </ol>
  )
}

function SignatureBlock({ label, sig, name, title, when, pending, paper }: { label: string; sig: Signature | null; name: string | null; title: string | null; when: string | null; pending?: string | null; paper?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[13px] font-semibold">{label}</div>
      <div className="mt-2 flex h-24 items-center rounded-lg border border-border bg-card px-3 text-foreground">
        {sig ? <SignatureView sig={sig} /> : <span className="text-[13px] text-muted-foreground">{paper ? "Signed on paper; the copy is on file" : when ? "Signed (the signature is shown to the parties only)" : pending ? `Waiting for ${pending}` : "—"}</span>}
      </div>
      <dl className="mt-2 grid grid-cols-[48px_minmax(0,1fr)] gap-x-2 gap-y-1 text-[13px]">
        <dt className="text-muted-foreground">Name</dt><dd>{name ?? "—"}</dd>
        <dt className="text-muted-foreground">Title</dt><dd>{title || "—"}</dd>
        <dt className="text-muted-foreground">Date</dt><dd>{when ? fmtDate(when) : "—"}</dd>
      </dl>
    </div>
  )
}

function Document({ v }: { v: SignoffVersion }) {
  const c = v.content
  return (
    <div className="grid grid-cols-1 gap-4">
      <Section n title="The rollout"><Facts p={c.project} /></Section>
      <Section n title="Summary"><p className="whitespace-pre-line text-[14px] leading-relaxed">{c.summary}</p></Section>
      {c.scope.length > 0
        ? <Section n title="Agreed scope and what was delivered" sub={`${c.scope.filter((x) => x.status === "delivered").length} of ${c.scope.length} in full`}><ScopeTable items={c.scope} /></Section>
        : <Section n title="What was delivered"><ul className="list-disc pl-5 text-[14px]">{c.delivered.map((x, i) => <li key={i}>{x}</li>)}</ul></Section>}
      <Section n title="Outstanding items" sub="recorded here; they do not hold up acceptance">
        {c.outstanding.length ? <ul className="list-disc pl-5 text-[14px]">{c.outstanding.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="text-[14px] text-muted-foreground">None.</p>}
      </Section>
      {c.terms.length > 0 && <Section n title="Handover and support"><ul className="list-disc pl-5 text-[14px]">{c.terms.map((x, i) => <li key={i}>{x}</li>)}</ul></Section>}
      <Section n title="Acceptance">
        <p className="rounded-lg bg-muted/60 p-3 text-[14px] leading-relaxed">{c.statement}</p>
        <div className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-2">
          <SignatureBlock label={`For ${c.project.client}`} sig={v.signature} name={v.signer_name ?? c.signer?.name ?? null} title={v.signer_title} when={v.signed_at}
            pending={v.status === "sent" ? c.signer?.name : null} paper={v.status === "uploaded"} />
          <SignatureBlock label={`For ${c.project.company}`} sig={v.counter_signature} name={v.counter_name ?? c.countersigner?.name ?? null} title={v.counter_title} when={v.counter_signed_at}
            pending={v.status === "signed" || v.status === "sent" ? c.countersigner?.name : null} />
        </div>
      </Section>
      <Section title="Signing record">
        <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[13px]">
          <dt className="text-muted-foreground">Version</dt><dd>{v.version}, prepared by {v.created_by}, {fmtWhen(v.created_at, true)}</dd>
          <dt className="text-muted-foreground">Fingerprint</dt><dd className="break-all font-mono text-[12px]">SHA-256 {v.content_hash}</dd>
          <dt className="text-muted-foreground">Integrity</dt>
          <dd className={cn("flex items-center gap-2", v.intact ? "text-ok" : "font-medium text-destructive")}><ShieldCheck className="h-3.5 w-3.5" aria-hidden />{v.intact ? "The content matches its fingerprint." : "The content no longer matches its fingerprint."}</dd>
          {v.signed_at && v.status !== "uploaded" && <><dt className="text-muted-foreground">Customer</dt><dd>{v.signer_name}{v.signer_email && ` (${v.signer_email})`} signed {fmtWhen(v.signed_at, true)} in Odin, after a one-time sign-in link sent to that address{v.signed_ip ? `; from ${v.signed_ip}` : ""}</dd></>}
          {v.link_issued_by && <><dt className="text-muted-foreground">Sign-in link</dt><dd>Issued by {v.link_issued_by}, {fmtWhen(v.link_issued_at, true)}, and passed on by hand</dd></>}
          {v.counter_signed_at && <><dt className="text-muted-foreground">Countersigned</dt><dd>{v.counter_name}, {fmtWhen(v.counter_signed_at, true)}{v.counter_ip ? `; from ${v.counter_ip}` : ""}</dd></>}
          {v.status === "uploaded" && <><dt className="text-muted-foreground">Paper copy</dt><dd>Signed by {v.signer_name} on {fmtDate(v.signed_at)}; the scan is in the rollout's documents</dd></>}
          {v.status === "rejected" && <><dt className="text-muted-foreground">Not accepted</dt><dd>{fmtWhen(v.rejected_at, true)}: {v.reject_comment}</dd></>}
          {v.status === "waived" && <><dt className="text-muted-foreground">Waived</dt><dd>by {v.waived_by}: {v.waiver_reason}</dd></>}
        </dl>
      </Section>
    </div>
  )
}

function SignForm({ who, client, counter, onDone, busy, setBusy, id, version, canReject }: {
  who: string; client: string; counter: boolean; onDone: (m: string) => void; busy: boolean; setBusy: (b: boolean) => void; id: number; version: number; canReject: boolean
}) {
  const [name, setName] = useState(who)
  const [title, setTitle] = useState("")
  const [sig, setSig] = useState<Signature | null>(null)
  const [accept, setAccept] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState("")
  const [err, setErr] = useState<string | null>(null)
  const missing = [!name.trim() && "enter your full name", !sig && "draw or type your signature", !accept && "tick the box to accept"].filter(Boolean) as string[]
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!sig) { setErr("Sign by drawing or typing your name"); return }
    setBusy(true); setErr(null)
    try { await signSignoff(id, version, { name, title, accept, signature: sig }, counter); onDone(counter ? "Countersigned. The rollout can now close." : "Signed. Thank you — we will countersign and send you the signed copy.") }
    catch (x) { setErr(x instanceof ApiError ? x.message : "That did not go through") } finally { setBusy(false) }
  }
  async function reject() {
    setBusy(true); setErr(null)
    try { await rejectSignoff(id, version, comment); onDone("Sent back with your comments. The project manager will send a new version.") }
    catch (x) { setErr(x instanceof ApiError ? x.message : "That did not go through") } finally { setBusy(false) }
  }
  if (rejecting) return (
    <div className="grid grid-cols-1 gap-2">
      <Field label="What needs to change before you can sign?">
        <textarea rows={4} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} className={area} autoFocus />
      </Field>
      {err && <Notice bad>{err}</Notice>}
      <div className="flex gap-2"><Button size="sm" variant="ghost" onClick={() => setRejecting(false)} disabled={busy}>Back</Button>
        <Button size="sm" variant="outline" className="ml-auto" onClick={reject} loading={busy} disabled={!comment.trim()}>Send back</Button></div>
    </div>
  )
  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3">
      <div className="grid grid-cols-2 gap-2">
        <Field label="Full name"><Input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
        <Field label="Title"><Input maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} autoComplete="organization-title" placeholder="e.g. IT Director" /></Field>
      </div>
      <SignaturePad value={sig} onChange={setSig} typedDefault={name} />
      <label className="flex items-start gap-2 text-[13px] leading-snug">
        <input type="checkbox" className={cn(checkbox, "mt-1")} checked={accept} onChange={(e) => setAccept(e.target.checked)} />
        <span>{counter ? "I confirm the work above is complete and countersign on our behalf." : `I have read this document and accept it on behalf of ${client}.`}</span>
      </label>
      {err && <Notice bad>{err}</Notice>}
      {/* a disabled button says what it waits for (WCAG 3.3.1), and the reason is tied to it */}
      {missing.length > 0 && <p id="sign-missing" className="text-[12px] text-muted-foreground">To {counter ? "countersign" : "sign"}: {missing.join(", ")}.</p>}
      <Button type="submit" loading={busy} disabled={missing.length > 0} aria-describedby={missing.length ? "sign-missing" : undefined}><FileSignature className="h-4 w-4" /> {counter ? "Countersign" : "Sign"}</Button>
      {canReject && <button type="button" onClick={() => setRejecting(true)} className="text-[13px] text-muted-foreground hover:text-foreground hover:underline">I can't sign this yet</button>}
    </form>
  )
}

// Mail not connected, or the email went astray: a one-time link to hand over yourself.
function SignerLink({ id, version, name }: { id: number; version: number; name: string }) {
  const [link, setLink] = useState<SignoffLink | null>(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function get() {
    setErr(null); setCopied(false)
    try { setLink(await signoffLink(id, version)) } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not make a link") }
  }
  async function copy() {
    setCopied(await copyWithToast(link!.link ?? "", "link"))
  }
  return (
    <section className="panel grid grid-cols-1 gap-2 p-4">
      <PanelTitle n={false} className="mb-0">Send the link yourself</PanelTitle>
      <p className="text-[12px] text-muted-foreground">If {name} did not get the email, give them a one-time sign-in link that opens this sign-off.</p>
      {link && !link.link ? (
        <p className="text-[13px]" role="status">{link.message || (link.emailed ? `A new one-time link was emailed to ${link.email}.` : "No link was made.")}</p>
      ) : link?.link ? (
        <>
          <input readOnly value={link.link} aria-label="Sign-in link for the signatory" onFocus={(e) => e.currentTarget.select()} className={cn(field, "font-mono text-[12px]")} />
          <Button size="sm" variant="outline" onClick={copy}><Copy className="h-3.5 w-3.5" /> {copied ? "Copied" : "Copy the link"}</Button>
          <p className="text-[12px] text-muted-foreground">For {link.email} only. It works once and expires in {link.minutes} minutes; make a new one if it lapses.</p>
        </>
      ) : <Button size="sm" variant="outline" onClick={get}><Link2 className="h-3.5 w-3.5" /> Get a sign-in link</Button>}
      {err && <Notice bad>{err}</Notice>}
    </section>
  )
}

function Composer({ d, id, onSent, template, onTemplate }: { d: SignoffData; id: number; onSent: (m: string) => void; template: number | null; onTemplate: (t: number | null) => void }) {
  const draft = d.draft!
  const cand = d.candidates!
  const [summary, setSummary] = useState(draft.summary)
  const [aiDraft, setAiDraft] = useState<number | null>(null)   // the AI draft the summary came from, recorded with the send
  const [delivered, setDelivered] = useState(draft.delivered.join("\n"))
  const [outstanding, setOutstanding] = useState(draft.outstanding.join("\n"))
  const [terms, setTerms] = useState(draft.terms.join("\n"))
  const [signer, setSigner] = useState<number | "">(cand.signers[0]?.id ?? "")
  const [counter, setCounter] = useState<number | "">(cand.default_counter_id ?? "")
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const dirty = summary !== draft.summary || outstanding !== draft.outstanding.join("\n") || terms !== draft.terms.join("\n") || delivered !== draft.delivered.join("\n")
  useUnsavedGuard(dirty && !busy)
  const unmarked = draft.scope.filter((x) => x.status === "agreed").length
  const who = cand.signers.find((s) => s.id === signer)
  async function send() {
    if (!signer || !counter) return
    setBusy(true); setErr(null)
    try {
      const r = await sendSignoff(id, { summary, delivered: toLines(delivered), outstanding: toLines(outstanding), terms: toLines(terms), signer_id: signer, counter_id: counter, template_id: template, ai_suggestion: aiDraft })
      onSent(`Version ${r.version} sent to ${who?.name}. They get the link by email when mail is set up; otherwise make a one-time link below and pass it on.`)
    } catch (x) { setErr(x instanceof ApiError ? x.message : "That did not send"); setConfirming(false) } finally { setBusy(false) }
  }
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="grid grid-cols-1 content-start gap-4">
        <Section n title="Summary" sub="drafted from the rollout; make it yours">
          <AIDraftBar<{ summary: string }> projectId={id} feature="signoff_summary"
            idle="Draft this summary with AI from the scope, dates and deliverables."
            working="Drafting from the scope, dates and deliverables…"
            note="It fills the summary for you to check word by word: the customer signs under it."
            onUse={(s) => { setSummary(s.payload.summary); setAiDraft(s.id) }} />
          <textarea aria-label="Summary" rows={4} maxLength={4000} value={summary} onChange={(e) => setSummary(e.target.value)} className={area} />
        </Section>
        {draft.scope.length > 0 ? (
          <Section n title="Agreed scope and what was delivered" sub={unmarked ? `${unmarked} still marked agreed` : "from the Scope panel"}>
            {unmarked > 0 && <p className="mb-2 rounded-lg bg-warn-soft px-3 py-2 text-[13px] text-warn">Mark every item delivered, partly delivered or descoped on the <Link to={`/projects/${id}#scope`} className="font-medium underline">rollout page</Link> before sending.</p>}
            <ScopeTable items={draft.scope} />
          </Section>
        ) : (
          <Section n title="What was delivered" sub="one per line; drafted from the stages, as no scope was recorded">
            <textarea aria-label="What was delivered" rows={6} maxLength={20000} value={delivered} onChange={(e) => setDelivered(e.target.value)} className={area} />
          </Section>
        )}
        <Section n title="Outstanding items" sub="one per line; open tasks and issues, drafted">
          <textarea aria-label="Outstanding items" rows={4} maxLength={20000} value={outstanding} onChange={(e) => setOutstanding(e.target.value)} className={area} placeholder="None" />
        </Section>
        <Section n title="Handover and support" sub="one per line">
          <textarea aria-label="Handover and support" rows={3} maxLength={20000} value={terms} onChange={(e) => setTerms(e.target.value)} className={area} />
        </Section>
        <Section n title="Acceptance" sub="set by an admin in Settings › Rollouts &amp; workflow"><p className="rounded-lg bg-muted/60 p-3 text-[14px] leading-relaxed">{draft.statement}</p></Section>
      </div>
      <aside className="grid grid-cols-1 content-start gap-3 lg:sticky lg:top-4 print:hidden">
        <section className="panel grid grid-cols-1 gap-3 p-4">
          <PanelTitle n={false} className="mb-0">Send for signature</PanelTitle>
          {/* another template brings its own terms: typing is not dropped without asking (review P2-30) */}
          <TemplatePicker kind="signoff" value={template} onChange={async (t) => { if (!dirty || await askConfirm("Switch the template? Its own terms replace the words on this page, and what you typed is lost.")) onTemplate(t) }} />
          <Field label="Customer's signatory">
            <select className={field} value={signer} onChange={(e) => setSigner(e.target.value ? Number(e.target.value) : "")}>
              {cand.signers.length === 0 && <option value="">Nobody yet</option>}
              {cand.signers.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.role}</option>)}
            </select>
          </Field>
          {cand.signers.length === 0 && <p className="text-[12px] text-muted-foreground">Invite the customer's contact on the <Link to={`/projects/${id}`} className="underline">rollout page</Link> (Team › Invite, role Customer). They sign with a one-time link: by email when mail is set up, or one you pass on.</p>}
          <Field label="Countersigns for us">
            <select className={field} value={counter} onChange={(e) => setCounter(e.target.value ? Number(e.target.value) : "")}>
              {cand.countersigners.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.role}</option>)}
            </select>
          </Field>
          {d.not_yet && <p className="rounded-md bg-warn-soft px-3 py-2 text-[13px] text-warn" role="note">{d.not_yet}. You can prepare the document now and send it then.</p>}
          <p className="text-[12px] text-muted-foreground">Sending freezes this version and its fingerprint. To change it later, withdraw it and send a new one.</p>
          {err && <Notice bad>{err}</Notice>}
          {confirming ? (
            <div className="grid grid-cols-1 gap-2" role="group" aria-label="Confirm sending">
              <Button onClick={send} loading={busy} autoFocus>{`Send to ${who?.name ?? "the customer"} now`}</Button>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={busy}>Cancel</Button>
            </div>
          ) : (
            <Button disabled={!!d.not_yet || !signer || !counter || unmarked> 0 || !summary.trim()} onClick={() => setConfirming(true)}><FileSignature className="h-4 w-4" /> Send for signature</Button>
          )}
        </section>
      </aside>
    </div>
  )
}

export default function Signoff(_props: { user: User }) {
  const id = Number(useParams().id)
  const [params, setParams] = useSearchParams()
  const v = Number(params.get("v")) || null
  const template = Number(params.get("template")) || null
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<"upload" | "waive" | null>(null)
  const [reason, setReason] = useState("")
  const [dialogErr, setDialogErr] = useState<string | null>(null)
  // a failed refresh keeps the page; an error clears on the next success (review P2-29)
  const { data: d, error: failed, reload: load } = useLoad(`signoff:${id}:${v}:${template}`, () => signoff(id, v, template))
  useEffect(() => { if (d) document.title = `Sign-off · ${d.project.name} · Odin` }, [d])
  const error = failed ? (failed.status === 404 ? "This rollout or version does not exist, or you are not on it." : failed.message) : null
  if (error) return <LoadError message={error} back={error.startsWith("This rollout or version does not exist") ? { href: "/projects", label: "All rollouts" } : undefined} />
  if (!d) return <PageSkeleton />
  const cur = d.current
  // a version set aside when the rollout was reopened closes nothing: the manager sends a new one
  const composing = d.can.manage && !!d.draft && (!cur || cur.status === "rejected" || cur.status === "withdrawn" || !!cur.superseded_at) && !v
  const done = (m: string) => { toast(m); setParams({}, { replace: true }); void load() }
  async function act(fn: () => Promise<unknown>, message: string) {
    setBusy(true)
    try { await fn(); done(message) } catch (e) { toast(e instanceof ApiError ? e.message : "That did not go through", { tone: "bad" }) } finally { setBusy(false) }
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true); setDialogErr(null)
    try { await uploadSignoff(id, cur!.version, new FormData(e.currentTarget)); setDialog(null); done("Signed copy on file. The rollout can now close.") }
    catch (x) { setDialogErr(x instanceof ApiError ? x.message : "That did not upload") } finally { setBusy(false) }
  }
  async function waive() {
    setBusy(true); setDialogErr(null)
    try { await waiveSignoff(id, reason); setDialog(null); setReason(""); done("Sign-off waived. The rollout can now close.") }
    catch (x) { setDialogErr(x instanceof ApiError ? x.message : "That did not go through") } finally { setBusy(false) }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-5 pb-10 pt-2 print:max-w-none print:px-0">
      <PrintBrand />
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <Link to={`/projects/${id}`} className="inline-flex min-w-0 max-w-full items-start gap-1 text-[13px] text-muted-foreground wrap-anywhere hover:text-foreground"><ChevronLeft className="mt-1 h-3.5 w-3.5 shrink-0" />{d.project.name}</Link>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {d.versions.length > 0 && (
            <select value={v ?? ""} onChange={(e) => setParams(e.target.value ? { v: e.target.value } : {}, { replace: true })} aria-label="Version" className={filterSelect}>
              <option value="">Latest</option>
              {d.versions.map((x) => <option key={x.version} value={x.version}>v{x.version} · {signoffText(x.status).split(";")[0].split(",")[0]} · {fmtDate(x.created_at)}</option>)}
            </select>
          )}
          {cur && !composing && <a href={`/projects/${id}/signoff.pdf?v=${cur.version}`} target="_blank" rel="noreferrer" className={pill}><Download className="h-3.5 w-3.5" /> PDF</a>}
          {cur && !composing && <button type="button" onClick={() => window.print()} className={pill}><Printer className="h-3.5 w-3.5" /> Print</button>}
          {d.can.waive && <button type="button" onClick={() => { setDialogErr(null); setDialog("waive") }} className={pill}>Close without signatures</button>}
        </span>
      </div>

      <header className="mt-3">
        <h1 className="text-[24px] font-semibold tracking-tight">Sign-off</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">{d.project.name} · {d.project.client} · now in {d.project.stage}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <SignoffPill status={composing ? null : cur?.status ?? null} />
          {cur && !composing && <span className="text-[13px] text-muted-foreground">Version {cur.version}, sent {fmtWhen(cur.created_at, true)}</span>}
        </div>
      </header>
      {d.state.complete && !v && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-ok-soft px-3 py-2 text-[13px] text-ok"><CheckCircle2 className="h-4 w-4" aria-hidden />
          <span>Signed off. {d.project.stage === "Sign-off" ? "The rollout can move to its last stage." : ""}</span>
          <Link to={`/projects/${id}`} className="ml-auto font-medium underline">Back to the rollout</Link>
        </div>
      )}
      {cur?.superseded_at && (
        <p className="mt-3 rounded-lg bg-warn-soft px-3 py-2 text-[13px] text-warn" role="note">
          <b>Superseded {fmtDate(cur.superseded_at)}.</b> The rollout was reopened after version {cur.version} was signed, so it is kept on record but no longer closes the rollout.
          {composing ? " Send a new version below." : d.can.manage ? " A new version is needed to close it again." : " The project manager has to send a new version to close it again."}
        </p>
      )}
      {composing && cur?.status === "rejected" && (
        <p className="mt-3 rounded-lg bg-bad-soft px-3 py-2 text-[13px] text-bad">Version {cur.version} was not accepted: {cur.reject_comment}</p>
      )}

      <div className="mt-4">
        {composing ? <Composer key={template ?? 0} d={d} id={id} onSent={done} template={template} onTemplate={(t) => setParams(t ? { template: String(t) } : {}, { replace: true })} /> : cur ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <Document v={cur} />
            <aside className="grid grid-cols-1 content-start gap-3 print:hidden lg:sticky lg:top-4">
              {(d.can.sign || d.can.countersign) && (
                <section className="panel p-4">
                  <PanelTitle n={false} className="mb-1">{d.can.sign ? "Your signature" : "Countersign"}</PanelTitle>
                  <p className="mb-3 text-[13px] text-muted-foreground">{d.can.sign ? "Read the document, then sign. You can send it back with comments instead." : `${cur.signer_name} signed for ${cur.content.project.client}. Countersign to complete it.`}</p>
                  <SignForm who={d.me.name} client={cur.content.project.client} counter={d.can.countersign} onDone={done} busy={busy} setBusy={setBusy} id={id} version={cur.version} canReject={d.can.sign} />
                </section>
              )}
              {!d.can.sign && !d.can.countersign && (cur.status === "sent" || cur.status === "signed") && (
                <section className="panel p-4 text-[13px] text-muted-foreground">
                  {cur.status === "sent" ? `Waiting for ${cur.content.signer?.name} to sign.` : `Waiting for ${cur.content.countersigner?.name} to countersign.`}
                </section>
              )}
              {d.can.withdraw && cur.status === "sent" && <SignerLink id={id} version={cur.version} name={cur.content.signer?.name ?? "the signatory"} />}
              {(d.can.upload || d.can.withdraw) && (
                <section className="panel grid grid-cols-1 gap-2 p-4">
                  <PanelTitle n={false} className="mb-0">If the customer signs on paper</PanelTitle>
                  <p className="text-[12px] text-muted-foreground">Send them the PDF; upload the signed copy when it comes back.</p>
                  {d.can.upload && <Button size="sm" variant="outline" onClick={() => { setDialogErr(null); setDialog("upload") }}><Upload className="h-3.5 w-3.5" /> Upload the signed copy</Button>}
                  {d.can.withdraw && <Button size="sm" variant="ghost" disabled={busy} onClick={async () => { if (await askConfirm("Withdraw this version? The signatory can no longer sign it; you can then send a new one.")) void act(() => withdrawSignoff(id, cur.version), `Version ${cur.version} withdrawn. Revise it and send again.`) }}>Withdraw and revise</Button>}
                </section>
              )}
            </aside>
          </div>
        ) : (
          <p className="text-[14px] text-muted-foreground">{d.state.complete ? "Signed off." : "The project manager has not sent the sign-off yet."}</p>
        )}
      </div>

      <Dialog open={dialog === "upload"} onOpenChange={(o) => { if (!o) setDialog(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Upload the signed copy</DialogTitle><DialogDescription>For version {cur?.version}. It completes the sign-off and is filed under the rollout's documents.</DialogDescription></DialogHeader>
          <form onSubmit={upload} className="grid grid-cols-1 gap-3">
            <Field label="Signed copy (PDF or image)"><Input name="file" type="file" required accept=".pdf,.png,.jpg,.jpeg" className="h-auto py-1" /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Signed by"><Input name="signer_name" required maxLength={120} defaultValue={cur?.content.signer?.name ?? ""} /></Field>
              <Field label="Title"><Input name="signer_title" maxLength={120} /></Field>
            </div>
            <Field label="Signed on"><SignedOn /></Field>
            {dialogErr && <Notice bad>{dialogErr}</Notice>}
            <div className="flex justify-end gap-2"><Button type="button" size="sm" variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button type="submit" size="sm" loading={busy}>Upload</Button></div>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={dialog === "waive"} onOpenChange={(o) => { if (!o) setDialog(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Close without signatures</DialogTitle><DialogDescription>An admin's exception: the rollout can close without the customer's signature. The reason is kept on the record and in the audit log.</DialogDescription></DialogHeader>
          <Field label="Why">
            <textarea rows={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} className={area} placeholder="Customer confirmed acceptance by email on 3 Oct; reference attached to the rollout." />
          </Field>
          {dialogErr && <Notice bad>{dialogErr}</Notice>}
          <div className="flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={() => setDialog(null)}>Cancel</Button><Button size="sm" loading={busy} disabled={reason.trim().length < 10} onClick={waive}>Waive the sign-off</Button></div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// the paper copy's signing date: today unless changed, never empty, never in the future
function SignedOn() {
  const [v, setV] = useState(localToday())
  return <DatePicker name="signed_on" value={v} onChange={(x) => setV(x || localToday())} label="Signed on" clearable={false} max={localToday()} className="h-9 w-full" />
}
