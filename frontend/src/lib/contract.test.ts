/// <reference types="node" />
import { readdirSync, readFileSync } from "node:fs"
import path from "node:path"
import ts from "typescript"
import { describe, expect, it } from "vitest"

// The API contract (advice A14). src/lib/__contract__/<TypeName>.json is the real
// answer of a GET that api.ts calls, saved from the seeded UAT world by
// test_v18_meta.ApiContractTestCase (which fails when the server's answer changes
// shape). Each file is checked here against the exported type of the same name in
// api.ts: every required property present, of the declared kind. Between the two
// tests the server and the client types cannot drift apart unseen.
//   regenerate: ODIN_WRITE_CONTRACT=1 venv/bin/python -m unittest test_v18_meta.ApiContractTestCase
// An extra key in the answer is fine (the client reads what it names); a missing or
// mistyped one is the bug this exists to catch.

const root = path.resolve(import.meta.dirname, "../..")
const dir = path.join(import.meta.dirname, "__contract__")
const config = ts.getParsedCommandLineOfConfigFile(path.join(root, "tsconfig.app.json"), {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} })!
const program = ts.createProgram([path.join(import.meta.dirname, "api.ts")], config.options)
const checker = program.getTypeChecker()
const apiFile = program.getSourceFile(path.join(import.meta.dirname, "api.ts"))!
const exported = new Map(checker.getExportsOfModule(checker.getSymbolAtLocation(apiFile)!).map((s) => [s.getName(), s]))

const kind = (v: unknown) => (v === null ? "null" : Array.isArray(v) ? "array" : typeof v)
const F = ts.TypeFlags

// the problems of a value against a type, as "path: what" lines; none means it fits
export function problems(t: ts.Type, v: unknown, at: string): string[] {
  if (t.flags & (F.Any | F.Unknown | F.TypeParameter)) return []
  const want = (name: string, ok: boolean) => (ok ? [] : [`${at}: expected ${name}, the answer has ${kind(v)}${typeof v === "string" || typeof v === "number" ? ` ${JSON.stringify(v)}` : ""}`])
  if (t.flags & F.Boolean) return want("boolean", typeof v === "boolean")   // boolean is the union true | false: said as one word
  if (t.isUnion()) {
    const tries = t.types.map((m) => problems(m, v, at))
    return tries.some((p) => p.length === 0) ? [] : [tries.sort((a, b) => a.length - b.length)[0][0] ?? `${at}: fits no member of the union`]
  }
  if (t.isIntersection()) return t.types.flatMap((m) => problems(m, v, at))
  if (t.flags & F.Null) return want("null", v === null)
  if (t.flags & (F.Undefined | F.Void)) return want("undefined", v === undefined)
  if (t.flags & F.StringLiteral) return want(JSON.stringify((t as ts.StringLiteralType).value), v === (t as ts.StringLiteralType).value)
  if (t.flags & F.NumberLiteral) return want(String((t as ts.NumberLiteralType).value), v === (t as ts.NumberLiteralType).value)
  if (t.flags & F.BooleanLiteral) return want((t as unknown as { intrinsicName: string }).intrinsicName, v === ((t as unknown as { intrinsicName: string }).intrinsicName === "true"))
  if (t.flags & F.String) return want("string", typeof v === "string")
  if (t.flags & F.Number) return want("number", typeof v === "number")
  if (t.flags & F.Never) return [`${at}: the type allows nothing here`]
  if (checker.isTupleType(t)) {
    const items = checker.getTypeArguments(t as ts.TypeReference)
    return !Array.isArray(v) ? want("array", false) : v.flatMap((x, i) => (items[i] ? problems(items[i], x, `${at}[${i}]`) : []))
  }
  if (checker.isArrayType(t)) {
    const item = checker.getTypeArguments(t as ts.TypeReference)[0]
    return !Array.isArray(v) ? want("array", false) : v.flatMap((x, i) => problems(item, x, `${at}[${i}]`))
  }
  if (t.flags & F.Object) {
    if (v === null || typeof v !== "object" || Array.isArray(v)) return want("object", false)
    const obj = v as Record<string, unknown>
    const out: string[] = []
    const named = new Set<string>()
    for (const prop of checker.getPropertiesOfType(t)) {
      named.add(prop.getName())
      const optional = !!(prop.flags & ts.SymbolFlags.Optional)
      if (!(prop.getName() in obj)) { if (!optional) out.push(`${at}.${prop.getName()}: missing from the answer`); continue }
      if (optional && obj[prop.getName()] === undefined) continue
      out.push(...problems(checker.getTypeOfSymbol(prop), obj[prop.getName()], `${at}.${prop.getName()}`))
    }
    const index = checker.getIndexInfoOfType(t, ts.IndexKind.String)
    if (index) for (const [k, x] of Object.entries(obj)) if (!named.has(k)) out.push(...problems(index.type, x, `${at}.${k}`))
    return out
  }
  return []
}

const files = readdirSync(dir).filter((f: string) => f.endsWith(".json")).sort()

describe("API contract: the server's answers against api.ts", () => {
  it("has the answers saved", () => {
    expect(files.length, "run ODIN_WRITE_CONTRACT=1 python -m unittest test_v18_meta.ApiContractTestCase").toBeGreaterThan(20)
  })
  for (const file of files) {
    const name = file.replace(/\.json$/, "")
    it(`${name} matches its type`, () => {
      const symbol = exported.get(name)
      expect(symbol, `api.ts does not export a type named ${name}`).toBeDefined()
      const type = checker.getDeclaredTypeOfSymbol(symbol!)
      const answer = JSON.parse(readFileSync(path.join(dir, file), "utf8")) as unknown
      expect(problems(type, answer, name)).toEqual([])
    })
  }
  it("can tell a wrong answer from a right one", () => {
    const flow = checker.getDeclaredTypeOfSymbol(exported.get("FlowData")!)
    const answer = JSON.parse(readFileSync(path.join(dir, "FlowData.json"), "utf8")) as { can_move: unknown; rows: { state: unknown }[] }
    expect(problems(flow, answer, "FlowData")).toEqual([])
    expect(problems(flow, { ...answer, can_move: "yes" }, "FlowData")[0]).toMatch(/can_move: expected boolean/)
    expect(problems(flow, { ...answer, rows: [{ ...answer.rows[0], state: "stuck" }] }, "FlowData").length).toBeGreaterThan(0)
    const { today: _today, ...without } = answer as Record<string, unknown>
    expect(problems(flow, without, "FlowData")).toContain("FlowData.today: missing from the answer")
  })
})
