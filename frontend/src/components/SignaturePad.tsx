import { useRef, useState, type PointerEvent } from "react"
import { Eraser } from "lucide-react"
import type { Signature } from "@/lib/api"
import { cn } from "@/lib/utils"

// A signature: drawn with a finger, pen or mouse (stored as strokes on a
// 1000 x 300 pad, so the PDF can draw them as vectors) or typed. Typing is
// the keyboard route and is just as binding.
const W = 1000, H = 300

export function SignatureView({ sig, className }: { sig: Signature | null; className?: string }) {
  if (!sig) return null
  if (sig.kind === "typed") return <span className={cn("block truncate pr-2 text-[24px] italic leading-tight tracking-tight", className)}>{sig.text}</span>
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("h-full w-full", className)} role="img" aria-label="Drawn signature">
      {sig.strokes.map((st, i) => <polyline key={i} points={st.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />)}
    </svg>
  )
}

export function SignaturePad({ value, onChange, typedDefault }: { value: Signature | null; onChange: (s: Signature | null) => void; typedDefault: string }) {
  const [mode, setMode] = useState<"draw" | "type">(value?.kind === "typed" ? "type" : "draw")
  const strokes = value?.kind === "drawn" ? value.strokes : []
  const drawing = useRef(false)
  const svg = useRef<SVGSVGElement>(null)
  const point = (e: PointerEvent) => {
    const r = svg.current!.getBoundingClientRect()
    return [Math.round(((e.clientX - r.left) / r.width) * W), Math.round(((e.clientY - r.top) / r.height) * H)]
  }
  const down = (e: PointerEvent<SVGSVGElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    drawing.current = true
    onChange({ kind: "drawn", strokes: [...strokes, [point(e)]] })
  }
  const move = (e: PointerEvent<SVGSVGElement>) => {
    if (!drawing.current || !strokes.length) return
    const last = strokes[strokes.length - 1]
    onChange({ kind: "drawn", strokes: [...strokes.slice(0, -1), [...last, point(e)]] })
  }
  const setKind = (m: "draw" | "type") => { setMode(m); onChange(m === "type" ? { kind: "typed", text: typedDefault } : null) }
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="flex rounded-full bg-muted p-0.5" role="group" aria-label="How to sign">
          {(["draw", "type"] as const).map((m) => <button key={m} type="button" aria-pressed={mode === m} onClick={() => setKind(m)}
            className={cn("h-6 rounded-full px-2.5 text-[12px]", mode === m ? "bg-card font-medium shadow-card" : "text-muted-foreground")}>{m === "draw" ? "Draw" : "Type"}</button>)}
        </span>
        {mode === "draw" && strokes.length > 0 && <button type="button" onClick={() => onChange(null)} className="ml-auto inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><Eraser className="h-3.5 w-3.5" /> Clear</button>}
      </div>
      {mode === "draw" ? (
        <svg ref={svg} viewBox={`0 0 ${W} ${H}`} onPointerDown={down} onPointerMove={move} onPointerUp={() => { drawing.current = false }} onPointerCancel={() => { drawing.current = false }}
          role="img" aria-label="Signature pad: draw your signature, or choose Type"
          className="h-32 w-full cursor-crosshair touch-none rounded-lg border border-dashed border-input bg-card text-foreground">
          <line x1={40} x2={W - 40} y1={H - 60} y2={H - 60} stroke="var(--border)" strokeWidth={2} />
          {strokes.map((st, i) => <polyline key={i} points={st.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />)}
          {strokes.length === 0 && <text x={W / 2} y={H / 2} textAnchor="middle" fontSize={34} fill="var(--muted-foreground)">Sign here</text>}
        </svg>
      ) : (
        <div className="grid grid-cols-1 gap-1.5">
          <input aria-label="Typed signature" maxLength={80} value={value?.kind === "typed" ? value.text : ""} onChange={(e) => onChange(e.target.value ? { kind: "typed", text: e.target.value } : null)}
            className="h-9 rounded-md border border-input bg-background px-2 text-[14px]" />
          <div className="flex h-20 items-center rounded-lg border border-dashed border-input bg-card px-4"><SignatureView sig={value} /></div>
        </div>
      )}
    </div>
  )
}
