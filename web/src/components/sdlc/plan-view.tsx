"use client"

import { AlertTriangle, ShieldCheck } from "lucide-react"

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import type { Phase, Plan, PlanValue } from "@/lib/api"

const FIELDS: [keyof Phase, string][] = [
  ["activities", "Activities"],
  ["deliverables", "Deliverables"],
  ["roles", "Roles"],
  ["testing", "Testing"],
  ["security_activities", "Security"],
  ["compliance_checkpoints", "Compliance"],
  ["entry_criteria", "Entry criteria"],
  ["exit_criteria", "Exit criteria"],
]

const items = (v: PlanValue): string[] =>
  v == null ? [] : Array.isArray(v) ? v.map(String).filter(Boolean) : String(v).trim() ? [String(v)] : []

// null = nothing to measure for this plan
const pct = (v: unknown) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "n/a")

function Check({ report, repairs }: { report: Record<string, unknown>; repairs: number }) {
  const missing = (report.missing_elements as string[] | undefined) ?? []
  const missingPhases = (report.missing_phases as string[] | undefined) ?? []
  const stats: [string, string, string][] = [
    ["Required elements present", pct(report.mandatory_recall), "Factor-triggered elements the plan must contain"],
    ["Lifecycle conformance", pct(report.lifecycle_conformance), "Phases match the lifecycle's skeleton"],
    ["Approval gates complete", pct(report.gate_completeness), "Phases with a named approver and criteria"],
    ["Over-generation", pct(report.overgeneration_rate), "Heavyweight activities the factors do not call for"],
  ]
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className="size-4" /> Plan check
        <span className="font-normal text-muted-foreground">(deterministic, eval/plan_checker.py)</span>
        {report.schema_valid ? null : <Badge variant="destructive">schema invalid</Badge>}
        {repairs ? <Badge variant="secondary">{repairs} repair pass{repairs > 1 ? "es" : ""}</Badge> : null}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map(([label, value, hint]) => (
          <div key={label} className="rounded-md bg-muted/50 p-2" title={hint}>
            <div className="text-lg font-semibold tabular-nums">{value}</div>
            <div className="text-xs text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>
      {missing.length || missingPhases.length ? (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3 shrink-0" />
          <span>
            {missing.length ? <>Missing: {missing.join(", ")}. </> : null}
            {missingPhases.length ? <>Phases not found: {missingPhases.join(", ")}.</> : null}
          </span>
        </p>
      ) : null}
    </div>
  )
}

interface Props {
  plan: Plan | null
  justification: string | null
  report: Record<string, unknown> | null
  repairs: number
  stale: boolean
  note?: string
}

export function PlanView({ plan, justification, report, repairs, stale, note }: Props) {
  if (!plan?.phases?.length) {
    return <p className="text-sm text-muted-foreground">{note ?? "No plan was written for this run."}</p>
  }
  return (
    <div className="space-y-4">
      {stale ? (
        <p className="flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
          <AlertTriangle className="size-3.5 shrink-0" /> This plan was written for the factors as first read. You
          have edited them since; regenerate to plan on your version.
        </p>
      ) : null}
      <div>
        <p className="text-sm text-muted-foreground">Lifecycle</p>
        <p className="text-lg font-semibold">{plan.lifecycle}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {plan.phases.map((p) => p.name).filter(Boolean).join(" → ")}
        </p>
      </div>
      {justification ? <p className="text-sm leading-relaxed">{justification}</p> : null}
      {report ? <Check report={report} repairs={repairs} /> : null}
      <Accordion multiple className="rounded-lg border">
        {plan.phases.map((phase, i) => (
          <AccordionItem key={i} value={String(i)} className="px-3">
            <AccordionTrigger>
              <span className="flex items-baseline gap-2 text-left">
                <span className="text-xs tabular-nums text-muted-foreground">{i + 1}</span>
                <span>{phase.name ?? `Phase ${i + 1}`}</span>
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-3 pb-2 text-sm">
                {phase.objective ? <p className="text-muted-foreground">{phase.objective}</p> : null}
                <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[9rem_1fr]">
                  {FIELDS.map(([key, label]) => {
                    const list = items(phase[key] as PlanValue)
                    if (!list.length) return null
                    return (
                      <div key={key} className="contents">
                        <dt className="text-xs font-medium text-muted-foreground sm:pt-0.5">{label}</dt>
                        <dd>
                          <ul className="list-disc space-y-0.5 pl-4">
                            {list.map((x, j) => (
                              <li key={j}>{x}</li>
                            ))}
                          </ul>
                        </dd>
                      </div>
                    )
                  })}
                  {phase.approval_gate?.approver || phase.approval_gate?.criteria ? (
                    <div className="contents">
                      <dt className="text-xs font-medium text-muted-foreground sm:pt-0.5">Approval gate</dt>
                      <dd>
                        <span className="font-medium">{phase.approval_gate?.approver}</span>
                        {phase.approval_gate?.criteria ? <> — {phase.approval_gate.criteria}</> : null}
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}
