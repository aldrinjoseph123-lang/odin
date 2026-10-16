import { useState, type FormEvent } from "react"
import { Ago } from "@/components/Ago"
import { EmptyState } from "@/components/EmptyState"
import { LoadFailed } from "@/components/LoadFailed"
import { Notice } from "@/components/Notice"
import { Panel } from "@/components/PanelTitle"
import { Button } from "@/components/ui/button"
import { Field } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Tag } from "@/components/ui/tag"
import { intakeSettings, postForm, type IntakeCall, type IntakeSettingsData } from "@/lib/api"
import { askConfirm } from "@/lib/confirm"
import { copyWithToast } from "@/lib/copy"
import { fmtDateY } from "@/lib/format"
import { toast } from "@/lib/toast"
import { danger, field as fieldLook, fieldAuto, td, th } from "@/lib/ui"
import { useAction } from "@/lib/useAction"
import { useLoad } from "@/lib/useLoad"
import { cn } from "@/lib/utils"

// Settings › Integrations › Intake: the CRM's way in (services/intake.py). Tokens
// with the create scope (they open POST /api/v1/intake and nothing else), the
// defaults a new intake gets, and the last calls with their results. The defaults
// are policies of the area `intake`, saved through the one policy route.
const RESULT: Record<IntakeCall["result"], string> = { created: "Created", duplicate: "Already had it", refused: "Refused", rate_limited: "Too many" }

export function IntakeSettings() {
  const { data, reload, error } = useLoad("intake-settings", intakeSettings)
  const { busy, note, act } = useAction(reload)
  if (!data) return error ? <LoadFailed what="the CRM intake settings" onRetry={() => void reload()} /> : null
  return (
    <>
      <Tokens d={data} busy={busy} act={act} />
      <Defaults key={JSON.stringify(data.policies.map((p) => p.value))} d={data} busy={busy} act={act} />
      <Calls d={data} reload={reload} />
      {note && <Notice bad={note.bad}>{note.text}</Notice>}
    </>
  )
}

type Act = ReturnType<typeof useAction>["act"]

function Tokens({ d, busy, act }: { d: IntakeSettingsData; busy: boolean; act: Act }) {
  const [name, setName] = useState("")
  const [days, setDays] = useState("365")
  // shown once, until dismissed: Odin keeps only the token's hash
  const [made, setMade] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const now = new Date().toISOString()
  function create(e: FormEvent) {
    e.preventDefault()
    void act(async () => { const r = await postForm("/settings/api-tokens", { name, days, scope: "create" }); setName(""); setMade(r.token ?? null); setCopied(false) })
  }
  return (
    <Panel title="CRM intake" hint="the CRM posts a won deal; a project manager confirms it">
      <p className="max-w-prose text-[13px]">
        The CRM sends <code className="font-mono text-[12px]">POST {d.endpoint}</code> with <code className="font-mono text-[12px]">Authorization: Bearer &lt;token&gt;</code>.
        Odin makes a pending rollout, held by the default project manager below, that waits in the Flow and under Rollouts › Pending intake until someone attaches the PO and takes ownership.
        A repeat of the same deal id answers with the rollout it made before. The fields and errors are in <code className="font-mono text-[12px]">docs/API_V1.md</code>.
      </p>
      <form onSubmit={create} className="mt-3 flex flex-wrap items-end gap-2">
        <Field label="Source (the token's name)" hint="shown on each intake and in the audit trail">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. crm-prod" maxLength={80} required className="h-8 w-56 text-[13px]" />
        </Field>
        <Field label="Valid for">
          <select value={days} onChange={(e) => setDays(e.target.value)} className={fieldAuto}><option value="30">30 days</option><option value="90">90 days</option><option value="365">1 year</option></select>
        </Field>
        <Button type="submit" size="sm" loading={busy} disabled={!name.trim()}>Create intake token</Button>
      </form>
      {made && (
        <div className="mt-3 grid grid-cols-1 gap-2 rounded-lg bg-muted/60 p-3">
          <input id="new-intake-token" readOnly value={made} aria-label="New intake token" onFocus={(e) => e.currentTarget.select()} className={cn(fieldAuto, "w-full font-mono text-[12px]")} />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => void copyWithToast(made, "token").then((ok) => { setCopied(ok); if (!ok) document.getElementById("new-intake-token")?.focus() })}>{copied ? "Copied" : "Copy the token"}</Button>
            <Button size="sm" variant="ghost" onClick={() => setMade(null)}>I have saved it</Button>
            <span className="text-[12px] text-muted-foreground">Shown once: Odin keeps only a fingerprint of it.</span>
          </div>
        </div>
      )}
      <div className="mt-4">
        {d.tokens.length === 0 ? <EmptyState>No intake tokens yet.</EmptyState> : (
          <div className="overflow-x-auto"><table className="w-full text-[13px]" aria-label="Intake tokens">
            <thead><tr>{["Source", "Made", "Last used", "Expires", ""].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
            <tbody>
              {d.tokens.map((t) => {
                const dead = !!t.revoked_at || t.expires_at < now
                return (
                  <tr key={t.id} className={cn("border-t border-border", dead && "text-muted-foreground")}>
                    <td className={cn(td, "font-medium")}>{t.name}</td>
                    <td className={cn(td, "whitespace-nowrap")}><Ago iso={t.created_at} /> · {t.created_by}</td>
                    <td className={cn(td, "whitespace-nowrap")}>{t.last_used_at ? <Ago iso={t.last_used_at} /> : "never"}</td>
                    <td className={cn(td, "whitespace-nowrap")}>{t.revoked_at ? "revoked" : t.expires_at < now ? "expired" : fmtDateY(t.expires_at)}</td>
                    <td className={cn(td, "text-right")}>{!dead && (
                      <Button size="sm" variant="ghost" className={danger} disabled={busy} aria-label={`Revoke ${t.name}`}
                        onClick={async () => { if (await askConfirm(`Revoke ${t.name}? The CRM stops being able to send intakes with it now.`, "Revoke")) void act(() => postForm(`/settings/api-tokens/${t.id}/revoke`), `Revoked ${t.name}.`) }}>Revoke</Button>
                    )}</td>
                  </tr>
                )
              })}
            </tbody>
          </table></div>
        )}
      </div>
    </Panel>
  )
}

function Defaults({ d, busy, act }: { d: IntakeSettingsData; busy: boolean; act: Act }) {
  const by = Object.fromEntries(d.policies.map((p) => [p.key, p]))
  const [v, setV] = useState<Record<string, string>>(() => Object.fromEntries(d.policies.map((p) => [p.key, String(p.value ?? "")])))
  const dirty = d.policies.some((p) => String(p.value ?? "") !== v[p.key])
  const set = (k: string) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value })
  function save(e: FormEvent) {
    e.preventDefault()
    void act(async () => { await postForm("/settings/policies/intake", v); toast("Intake defaults saved.") })
  }
  const rate = by.intake_rate_per_min
  return (
    <Panel title="Intake defaults" hint="what a new intake starts with">
      <form onSubmit={save} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={by.intake_template?.label ?? "Stage template"} hint={by.intake_template?.help}>
          <select value={v.intake_template} onChange={set("intake_template")} className={fieldLook}>
            <option value="">First template ({d.templates[0]?.name ?? "none"})</option>
            {d.templates.map((t) => <option key={t.id} value={String(t.id)}>{t.name}</option>)}
          </select>
        </Field>
        <Field label={by.intake_owner?.label ?? "Default project manager"} hint={by.intake_owner?.help}>
          <select value={v.intake_owner} onChange={set("intake_owner")} className={fieldLook}>
            <option value="">First active Admin</option>
            {d.owners.map((o) => <option key={o.id} value={String(o.id)}>{o.name}</option>)}
          </select>
        </Field>
        <Field label={by.intake_sources?.label ?? "Allowed sources"} hint={by.intake_sources?.help}>
          <Input value={v.intake_sources} onChange={set("intake_sources")} maxLength={by.intake_sources?.max} placeholder="crm-prod, crm-test" className="h-8 text-[13px]" />
        </Field>
        <Field label={rate?.label ?? "Most intakes per minute"} hint={`${rate?.help ?? ""} ${rate?.min}–${rate?.max}.`}>
          <Input type="number" min={rate?.min} max={rate?.max} required value={v.intake_rate_per_min} onChange={set("intake_rate_per_min")} className="h-8 w-28 text-[13px]" />
        </Field>
        <div className="sm:col-span-2"><Button type="submit" size="sm" loading={busy} disabled={!dirty}>Save</Button></div>
      </form>
    </Panel>
  )
}

function Calls({ d, reload }: { d: IntakeSettingsData; reload: () => unknown }) {
  return (
    <Panel title="Recent calls" hint={`the last ${d.calls.length} of the newest ${d.keep} kept`}>
      {d.calls.length === 0 ? <EmptyState>No call yet. The CRM's first intake appears here with its result.</EmptyState> : (
        <div className="overflow-x-auto"><table className="w-full text-[13px]" aria-label="Recent intake calls">
          <thead><tr>{["When", "Source", "Result", "Deal", "Detail"].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
          <tbody>
            {d.calls.map((c) => (
              <tr key={c.id} className="border-t border-border">
                <td className={cn(td, "whitespace-nowrap")}><Ago iso={c.at} /></td>
                <td className={td}>{c.token_name}</td>
                <td className={cn(td, "whitespace-nowrap")}><Tag kind={c.result === "created" ? "default" : "plain"}>{c.status} {RESULT[c.result]}</Tag></td>
                <td className={cn(td, "font-mono text-[12px]")}>{c.deal_id ?? "—"}</td>
                <td className={cn(td, "text-muted-foreground wrap-anywhere")}>{c.project_id ? <a href={`/projects/${c.project_id}`} className="text-primary-text hover:underline">Rollout {c.project_id}</a> : c.detail ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
      <Button size="sm" variant="ghost" className="mt-2" onClick={() => void reload()}>Refresh</Button>
    </Panel>
  )
}
