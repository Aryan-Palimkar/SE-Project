"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { AlertTriangle, FlaskConical, RefreshCw, Undo2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TypingIndicator } from "@/components/ui/typing-indicator"
import { type Analysis, type Assessment, assess, type Factors, type Level, type Meta, type RequirementQuestion, type ResultEvent, scoreLevels, type StepEvent } from "@/lib/api"
import { expectedNodes, factorLabel, MIN_STATED } from "@/lib/labels"

import { ComplianceMap, RiskRegister } from "./compliance-view"
import { FactorTable } from "./factor-table"
import { PlanView } from "./plan-view"
import { ProgressSteps } from "./progress-steps"
import { Recommendation } from "./recommendation"
import { RequirementsView } from "./requirements-view"
import { SrsView } from "./srs-view"

export interface Run {
  id: string
  kind: "analyze" | "replan"
  planned: boolean
  description: string
  status: "running" | "done" | "error" | "stopped"
  backend: "model" | "lexicon"
  queued: boolean
  loadingModel: boolean
  started: number
  lastStepAt?: number
  steps: StepEvent[]
  result?: ResultEvent
  error?: string
}

const levelsOf = (f: Factors) => Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.level])) as Record<string, Level>

interface Props {
  run: Run
  meta: Meta
  onReplan: (factors: Factors) => void
  onClarify: (answers: Record<string, string>, questions: RequirementQuestion[]) => void
  busy: boolean
}

export function RunCard({ run, meta, onReplan, onClarify, busy }: Props) {
  if (run.status === "error") {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
        <div>
          <p className="font-medium">The run failed</p>
          <p className="text-muted-foreground">{run.error}</p>
        </div>
      </div>
    )
  }
  if (!run.result) {
    const expected = expectedNodes(run.kind, run.backend, run.planned)
    return (
      <div className="w-full max-w-md space-y-3 rounded-xl border bg-card p-4">
        {run.steps.length || run.loadingModel || run.queued ? null : <TypingIndicator />}
        <ProgressSteps
          expected={expected}
          steps={run.steps}
          running={run.status === "running"}
          loadingModel={run.loadingModel}
          queued={run.queued}
          since={run.lastStepAt ?? run.started}
        />
        {run.status === "stopped" ? (
          <p className="text-xs text-muted-foreground">
            Stopped listening. A step already running on the GPU finishes in the background.
          </p>
        ) : null}
      </div>
    )
  }
  return <Result run={run} result={run.result} meta={meta} onReplan={onReplan} onClarify={onClarify} busy={busy} />
}

function Result({ run, result, meta, onReplan, onClarify, busy }: Props & { result: ResultEvent }) {
  const extracted = result.state.factors
  const requirements = result.state.requirements ?? []
  const requirementQuestions = result.state.requirement_questions ?? []
  const [levels, setLevels] = useState(() => levelsOf(extracted))
  const original: Analysis = useMemo(
    () => ({ rubric: result.rubric, questions: result.questions, stated: result.stated }),
    [result],
  )
  // rescored analyses, keyed by the levels they were computed for
  const [scored, setScored] = useState<{ key: string; analysis: Analysis } | null>(null)
  const abort = useRef<AbortController | null>(null)

  const edits = useMemo(
    () => Object.keys(levels).filter((f) => levels[f] !== (extracted[f]?.level ?? "not_stated")),
    [levels, extracted],
  )
  const key = JSON.stringify(levels)
  const live = edits.length ? (scored?.analysis ?? original) : original
  const scoring = edits.length > 0 && scored?.key !== key

  useEffect(() => {
    if (!edits.length) return
    abort.current?.abort()
    const ctl = new AbortController()
    abort.current = ctl
    const t = setTimeout(() => {
      scoreLevels(levels, ctl.signal)
        .then((analysis) => setScored({ key, analysis }))
        .catch(() => {})
    }, 120)
    return () => clearTimeout(t)
  }, [key, levels, edits.length])

  // compliance map and risk register, refreshed on edits
  const originalAssessment: Assessment | null = useMemo(
    () => (result.state.compliance ? { compliance: result.state.compliance, risks: result.state.risks ?? [] } : null),
    [result],
  )
  const [assessed, setAssessed] = useState<{ key: string; value: Assessment } | null>(null)
  const [rejected, setRejected] = useState<Set<string>>(() => new Set())
  const assessment = edits.length ? (assessed?.key === key ? assessed.value : originalAssessment) : originalAssessment

  useEffect(() => {
    if (!edits.length || !originalAssessment) return
    const ctl = new AbortController()
    const factors = Object.fromEntries(
      Object.keys(levels).map((f) => [f, { level: levels[f], evidence: extracted[f]?.evidence ?? null }]),
    ) as Factors
    const t = setTimeout(() => {
      assess(result.state.description, factors, result.state.plan, ctl.signal)
        .then((value) => setAssessed({ key, value }))
        .catch(() => {})
    }, 150)
    return () => {
      clearTimeout(t)
      ctl.abort()
    }
  }, [key, levels, edits.length, originalAssessment, extracted, result])

  const toggleStandard = (sid: string) =>
    setRejected((prev) => {
      const next = new Set(prev)
      if (next.has(sid)) next.delete(sid)
      else next.add(sid)
      return next
    })

  const set = (f: string, lv: Level) => setLevels((prev) => ({ ...prev, [f]: lv }))
  const reset = (f: string) => set(f, extracted[f]?.level ?? "not_stated")
  const reviewed = (): Factors =>
    Object.fromEntries(
      Object.keys(levels).map((f) => [
        f,
        edits.includes(f)
          ? { level: levels[f], evidence: levels[f] === "not_stated" ? null : "set by the reviewer" }
          : extracted[f],
      ]),
    )

  const total = meta.factors.length
  const insufficient = live.stated < MIN_STATED
  const noPlanNote =
    run.backend === "lexicon"
      ? "The CPU demo backend does not write plans. Start the server without SDLC_BACKEND=lexicon to use the model."
      : !run.planned && !result.state.insufficient_evidence
        ? "Plan skipped for this run. Tick \"Write an SDLC plan\" and send the description again, or use Regenerate plan."
      : result.state.insufficient_evidence
        ? "No plan: too little evidence to choose a lifecycle. Set a few factors, then regenerate."
        : undefined

  return (
    <div className="w-full space-y-4 rounded-xl border bg-card p-4 sm:p-5">
      {run.backend === "lexicon" ? (
        <p className="flex items-start gap-1.5 rounded-md bg-muted p-2 text-xs text-muted-foreground">
          <FlaskConical className="mt-0.5 size-3.5 shrink-0" />
          CPU demo backend: factors were read by the keyword lexicon baseline, not the fine-tuned model, and are
          much less accurate. Review them in the Factors tab.
        </p>
      ) : null}
      {run.kind === "replan" ? (
        <p className="text-xs text-muted-foreground">Planned on your reviewed factors - nothing was re-read.</p>
      ) : null}

      {edits.length ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-2 text-xs">
          <span>
            You changed {edits.length} factor{edits.length > 1 ? "s" : ""}:{" "}
            <span className="text-muted-foreground">{edits.map(factorLabel).join(", ")}</span>
            {scoring ? <span className="text-muted-foreground"> · rescoring…</span> : null}
          </span>
          <div className="ml-auto flex gap-1.5">
            <Button size="xs" variant="ghost" onClick={() => setLevels(levelsOf(extracted))}>
              <Undo2 /> Undo all
            </Button>
            <Button size="xs" onClick={() => onReplan(reviewed())} disabled={busy || insufficient}>
              <RefreshCw /> Regenerate plan with these factors
            </Button>
          </div>
        </div>
      ) : null}

      <Tabs defaultValue={requirements.length ? "requirements" : "rec"}>
        <TabsList>
          {requirements.length ? (
            <TabsTrigger value="requirements">
              Requirements <span className="ml-1 text-muted-foreground tabular-nums">{requirements.length}</span>
            </TabsTrigger>
          ) : null}
          <TabsTrigger value="rec">Recommendation</TabsTrigger>
          <TabsTrigger value="factors">
            Factors <span className="ml-1 text-muted-foreground tabular-nums">{live.stated}/{total}</span>
          </TabsTrigger>
          <TabsTrigger value="plan">Plan</TabsTrigger>
          <TabsTrigger value="compliance">
            Compliance &amp; risk
            {assessment?.compliance.standards.length ? (
              <span className="ml-1 text-muted-foreground tabular-nums">
                {assessment.compliance.standards.filter((s) => !rejected.has(s.standard)).length}
              </span>
            ) : null}
          </TabsTrigger>
          {requirements.length ? <TabsTrigger value="srs">SRS</TabsTrigger> : null}
          <TabsTrigger value="log">Run</TabsTrigger>
        </TabsList>

        <TabsContent value="requirements" className="pt-4">
          <RequirementsView
            requirements={requirements}
            questions={requirementQuestions}
            onClarify={(answers) => onClarify(answers, requirementQuestions)}
            busy={busy}
          />
        </TabsContent>

        <TabsContent value="rec" className="pt-4">
          <Recommendation rubric={live.rubric} stated={live.stated} total={total} meta={meta} levels={levels} onSet={set} />
          {live.questions.length ? (
            <p className="mt-4 text-xs text-muted-foreground">
              {live.questions.length} unstated factor{live.questions.length > 1 ? "s" : ""} would change this answer
              - see the Factors tab.
            </p>
          ) : null}
        </TabsContent>

        <TabsContent value="factors" className="pt-4">
          <p className="mb-3 text-xs text-muted-foreground">
            What the extractor read, with the sentence it relied on. Correct anything it got wrong; the recommendation
            updates immediately.
          </p>
          <FactorTable
            meta={meta}
            extracted={extracted}
            levels={levels}
            questions={live.questions}
            onSet={set}
            onReset={reset}
          />
        </TabsContent>

        <TabsContent value="plan" className="pt-4">
          <PlanView
            plan={result.state.plan}
            justification={result.state.justification}
            report={result.state.report}
            repairs={result.state.repairs}
            stale={edits.length > 0}
            note={noPlanNote}
          />
        </TabsContent>

        <TabsContent value="compliance" className="space-y-6 pt-4">
          {assessment ? (
            <>
              <section className="space-y-3">
                <h3 className="text-sm font-semibold">Compliance map</h3>
                <ComplianceMap
                  compliance={assessment.compliance}
                  rejected={rejected}
                  onToggle={toggleStandard}
                  hasPlan={Boolean(result.state.plan?.phases?.length)}
                />
              </section>
              <section className="space-y-3">
                <h3 className="text-sm font-semibold">Risk register</h3>
                <RiskRegister risks={assessment.risks} />
              </section>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No compliance analysis for this run.</p>
          )}
        </TabsContent>

        <TabsContent value="srs" className="pt-4">
          <SrsView state={result.state} available={requirements.length > 0} />
        </TabsContent>

        <TabsContent value="log" className="space-y-3 pt-4">
          <ProgressSteps
            expected={[]}
            steps={result.state.log}
            running={false}
            loadingModel={false}
            queued={false}
            since={run.started}
          />
          <p className="text-xs text-muted-foreground">
            Total {result.seconds}s · backend {run.backend} · rubric v{result.rubric.rubric_version}
          </p>
        </TabsContent>
      </Tabs>
    </div>
  )
}
