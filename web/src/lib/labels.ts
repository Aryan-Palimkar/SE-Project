import type { Level, Model } from "./api"

export const FACTOR_LABEL: Record<string, string> = {
  requirement_stability: "Requirement stability",
  change_frequency: "Change frequency",
  continuous_delivery_need: "Delivery cadence",
  regulatory_criticality: "Regulation",
  security_risk: "Security risk",
  failure_consequence: "Failure consequence",
  verification_rigor: "Verification rigour",
  test_doc_rigor: "Test & documentation rigour",
  complexity: "Complexity",
  size: "Size",
  technical_novelty: "Technical novelty",
  legacy_dependence: "Legacy dependence",
  stakeholder_availability: "Stakeholder availability",
  scope_rigidity: "Scope rigidity",
}

export const factorLabel = (f: string) => FACTOR_LABEL[f] ?? f.replaceAll("_", " ")

export const LEVEL_LABEL: Record<Level, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  not_stated: "Not stated",
}

export const MODEL_BLURB: Record<Model, string> = {
  Waterfall: "Sequential phases on a stable, fixed scope",
  "V-Model": "Every specification level paired with a test level",
  Spiral: "Risk-driven cycles that retire technical unknowns",
  Agile: "Short iterations steered by users and feedback",
  DevSecOps: "Continuous delivery with security built into the pipeline",
}

// css variable per model, defined in globals.css (light and dark)
export const MODEL_VAR: Record<Model, string> = {
  Waterfall: "var(--model-waterfall)",
  "V-Model": "var(--model-vmodel)",
  Spiral: "var(--model-spiral)",
  Agile: "var(--model-agile)",
  DevSecOps: "var(--model-devsecops)",
}

export const NODE_LABEL: Record<string, string> = {
  requirements: "Identifying the requirements",
  regulate: "Adding regulatory requirements (RAG)",
  ask_requirements: "Finding unclear requirements",
  srs: "Drafting the SRS",
  extract: "Reading the description",
  challenge: "Re-checking unstated factors",
  reconcile: "Using the requirements as evidence",
  clarify: "Finding what would change the answer",
  apply_answers: "Applying your answers",
  rubric: "Scoring the five lifecycles",
  comply: "Mapping standards and obligations",
  assess: "Checking compliance and risks",
  plan: "Writing the plan",
  check: "Checking the plan",
  repair: "Repairing the plan",
  explain: "Summarising",
}

const PLAN_NODES = ["plan", "check", "repair"]

export const expectedNodes = (kind: "analyze" | "replan", backend: "model" | "lexicon", planned = true) =>
  (backend === "lexicon"
    ? kind === "analyze"
      ? ["extract", "clarify", "rubric", "comply", "assess", "explain"]
      : ["clarify", "rubric", "comply", "assess", "explain"]
    : kind === "analyze"
      ? ["comply", "requirements", "regulate", "ask_requirements", "extract", "clarify", "rubric", "plan", "check", "repair", "assess", "explain"]
      : ["clarify", "rubric", "comply", "plan", "check", "repair", "assess", "explain"]
  ).filter((n) => planned || !PLAN_NODES.includes(n))

export const MIN_STATED = 3
