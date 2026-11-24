// Typed client for server/app.py.

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type Level = "low" | "medium" | "high" | "not_stated"
export const LEVELS: Level[] = ["high", "medium", "low", "not_stated"]
export type Model = "Waterfall" | "V-Model" | "Spiral" | "Agile" | "DevSecOps"

export interface Factor {
  level: Level
  evidence: string | null
}
export type Factors = Record<string, Factor>

export interface Rubric {
  scores: Record<Model, number>
  ranking: Model[]
  primary: Model
  primary_withheld: boolean
  supported_models: Model[] | null
  acceptable_set: Model[]
  margin: number
  low_evidence: boolean
  stated_coverage: number
  hybrid: { backbone: Model; overlays: string[] } | null
  triggered_rules: string[]
  top_contributors: Record<Model, string[]>
  rubric_version: string
}

export interface Question {
  factor: string
  question: string
  outcomes: Record<"low" | "medium" | "high", Model>
  could_lead_to: Model[]
  descriptors: Record<"low" | "medium" | "high", string>
}

export interface Analysis {
  rubric: Rubric
  questions: Question[]
  stated: number
}

export type PlanValue = string | string[] | null | undefined
export interface Phase {
  name?: string
  objective?: string
  activities?: PlanValue
  roles?: PlanValue
  deliverables?: PlanValue
  security_activities?: PlanValue
  testing?: PlanValue
  compliance_checkpoints?: PlanValue
  entry_criteria?: PlanValue
  exit_criteria?: PlanValue
  approval_gate?: { approver?: string; criteria?: string } | null
}
export interface Plan {
  lifecycle?: string
  phases?: Phase[]
}

export interface StepEvent {
  node: string
  ok: boolean
  seconds: number
  detail: Record<string, unknown>
}

export interface StandardHit {
  standard: string
  name: string
  how: "named" | "inferred"
  evidence: string
  score: number
}
export interface ObligationRow {
  id: string
  standard: string
  standard_name: string
  ref: string
  phase: string
  description: string
  covered_by: string[] | null // null = no plan to check against
  clause?: Clause | null
}
export interface Compliance {
  standards: StandardHit[]
  obligations: ObligationRow[]
  coverage: number | null
  missing: string[]
}
export interface Risk {
  id: string
  title: string
  owner: string
  evidence: { factor: string; level: string; evidence: string | null }[]
  likelihood: "low" | "medium" | "high"
  impact: "low" | "medium" | "high"
  score: number
  assumed: boolean
  note: string | null
  mitigations: { id: string; description: string; covered_by: string[] | null }[]
  mitigated: boolean | null
}
export interface Assessment {
  compliance: Compliance
  risks: Risk[]
}

export interface Clause {
  passage: string
  document: string
  page: number
  text: string
}

export interface Requirement {
  id: string
  statement: string
  type: "functional" | "non-functional"
  category: string
  basis: "stated" | "regulation" | "inferred"
  source: string | null
  citation: { obligation: string; standard: string; ref: string; clause?: Clause | null } | null
}

export interface RequirementQuestion {
  id: string
  question: string
  options: string[]
  requirements: string[]
}

export interface Srs {
  title: string
  version: string
  date: string
  purpose: string
  scope: string
  stakeholders: { role: string; interest: string }[]
  operating_environment: string
  constraints: string[]
  assumptions: string[]
  glossary: { term: string; definition: string }[]
  functional: Requirement[]
  non_functional: { category: string; requirements: Requirement[] }[]
  regulations: {
    standard: string
    name: string
    basis: "named" | "inferred"
    evidence: string
    obligations: { id: string; ref: string; text: string; page: number | null; excerpt: string | null }[]
  }[]
  clauses: { id: string; document: string; page: number; text: string }[]
  sdlc: { primary: string; hybrid: string[]; ranking: string[]; acceptable: string[]; provisional: boolean; withheld: boolean } | null
  traceability: { id: string; requirement: string; basis: string; source: string; regulation: string; verification: string }[]
  open_questions: { question: string; options: string[] }[]
}

export interface RunStateDTO {
  description: string
  requirements?: Requirement[]
  requirement_questions?: RequirementQuestion[]
  clauses?: { id: string; source: string; title: string; page: number; text: string; score: number }[]
  factors: Factors
  recommendation: { primary: Model; hybrid: string[]; low_evidence: boolean } | null
  plan: Plan | null
  justification: string | null
  report: Record<string, unknown> | null
  repairs: number
  insufficient_evidence: boolean
  summary: string
  log: StepEvent[]
  compliance: Compliance | null
  risks: Risk[]
}

export interface ResultEvent extends Analysis {
  type: "result"
  seconds: number
  state: RunStateDTO
}

export type StreamEvent =
  | { type: "accepted"; queued: boolean; loading: boolean }
  | { type: "queued" }
  | { type: "start"; backend: "model" | "lexicon"; loading: boolean }
  | ({ type: "step" } & StepEvent)
  | ResultEvent
  | { type: "error"; message: string }

export interface FactorMeta {
  name: string
  question: string
  low: string
  medium: string
  high: string
}

export interface Meta {
  backend: "model" | "lexicon"
  preset: string
  model_loaded: boolean
  busy: boolean
  loading: boolean
  rubric_version: string
  models: Model[]
  preconditions: Record<Model, Record<string, Level[]>>
  factors: FactorMeta[]
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const getMeta = () => fetch(`${API}/api/meta`, { cache: "no-store" }).then(json<Meta>)

export const scoreLevels = (levels: Record<string, Level>, signal?: AbortSignal) =>
  fetch(`${API}/api/score`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ levels }),
    signal,
  }).then(json<Analysis>)

export const assess = (description: string, factors: Factors, plan: Plan | null, signal?: AbortSignal) =>
  fetch(`${API}/api/assess`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ description, factors, plan }),
    signal,
  }).then(json<Assessment>)

export const generateSrs = (state: RunStateDTO, signal?: AbortSignal) =>
  fetch(`${API}/api/srs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ state }),
    signal,
  }).then(json<{ srs: Srs; markdown: string }>)

/** POST and read a server-sent-event stream, calling `onEvent` for each `data:` frame. */
export async function stream(
  path: "/api/analyze" | "/api/replan",
  body: unknown,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    await json(res)
    throw new Error(`stream failed: ${res.status}`)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ""
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let cut
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      for (const line of frame.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as StreamEvent)
      }
    }
  }
}
