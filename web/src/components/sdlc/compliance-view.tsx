"use client"

import { CheckCircle2, CircleDashed, Info, ShieldAlert, Undo2, XCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { Compliance, ObligationRow, Risk } from "@/lib/api"
import { factorLabel } from "@/lib/labels"
import { cn } from "@/lib/utils"

const LEVEL_TONE: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  medium: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  high: "bg-red-500/15 text-red-700 dark:text-red-300",
}

function Status({ covered }: { covered: string[] | null }) {
  if (covered === null)
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <CircleDashed className="size-3.5" /> no plan yet
      </span>
    )
  return covered.length ? (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400">
      <CheckCircle2 className="size-3.5 shrink-0" /> {covered.join(", ")}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs text-red-700 dark:text-red-400">
      <XCircle className="size-3.5 shrink-0" /> not in the plan
    </span>
  )
}

interface ComplianceProps {
  compliance: Compliance
  rejected: Set<string>
  onToggle: (standard: string) => void
  hasPlan: boolean
}

export function ComplianceMap({ compliance, rejected, onToggle, hasPlan }: ComplianceProps) {
  const active = compliance.obligations.filter((o) => !rejected.has(o.standard))
  const covered = active.filter((o) => o.covered_by?.length).length
  const byStandard = new Map<string, ObligationRow[]>()
  for (const o of compliance.obligations) byStandard.set(o.standard, [...(byStandard.get(o.standard) ?? []), o])

  if (!compliance.standards.length) {
    return (
      <p className="flex items-start gap-1.5 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" />
        No standard in the knowledge base is named or clearly implied by the description. If a regulator or
        standard does apply, add it to the description (e.g. &ldquo;certified to IEC 62304&rdquo;) and run again.
      </p>
    )
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="text-sm">
          <span className="text-2xl font-semibold tabular-nums">
            {hasPlan && active.length ? `${Math.round((covered / active.length) * 100)}%` : "–"}
          </span>{" "}
          <span className="text-muted-foreground">
            of {active.length} obligation{active.length === 1 ? "" : "s"} covered by the plan
          </span>
        </p>
        {rejected.size ? (
          <p className="text-xs text-muted-foreground">
            {rejected.size} standard{rejected.size > 1 ? "s" : ""} marked not applicable
          </p>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">
        A checklist to confirm, not a compliance determination. Each standard shows why it was matched: the words
        that name it, or the sentence whose meaning matched its scope. Reject any that do not apply to your
        jurisdiction or product.
      </p>

      {compliance.standards.map((s) => {
        const off = rejected.has(s.standard)
        const rows = byStandard.get(s.standard) ?? []
        return (
          <div key={s.standard} className={cn("rounded-lg border bg-card", off && "opacity-50")}>
            <div className="flex flex-wrap items-start gap-2 border-b p-3">
              <div className="min-w-0 flex-1">
                <p className="font-heading text-sm font-semibold">{s.name}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {s.how === "named" ? (
                    <>
                      <Badge variant="secondary" className="mr-1.5">
                        named
                      </Badge>
                      the description says &ldquo;{s.evidence}&rdquo;
                    </>
                  ) : (
                    <>
                      <Badge variant="outline" className="mr-1.5">
                        inferred · {s.score.toFixed(2)}
                      </Badge>
                      from &ldquo;{s.evidence}&rdquo;
                    </>
                  )}
                </p>
              </div>
              <button
                onClick={() => onToggle(s.standard)}
                className="inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-xs hover:bg-muted"
              >
                {off ? (
                  <>
                    <Undo2 className="size-3" /> Restore
                  </>
                ) : (
                  "Not applicable"
                )}
              </button>
            </div>
            {!off ? (
              <ul className="divide-y">
                {rows.map((o) => (
                  <li key={o.id} className="grid gap-1 p-3 text-sm sm:grid-cols-[6.5rem_1fr_12rem] sm:gap-3">
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {o.ref} · {o.phase}
                    </span>
                    <div className="min-w-0">
                      <p>{o.description}</p>
                      {o.clause ? (
                        <details className="mt-1 text-xs text-muted-foreground">
                          <summary className="cursor-pointer select-none hover:text-foreground">
                            Source text: {o.clause.document}, p. {o.clause.page}
                          </summary>
                          <blockquote className="mt-1.5 border-l-2 border-primary/40 bg-muted/40 py-1.5 pr-2 pl-3 leading-relaxed">
                            {o.clause.text.length > 700 ? `${o.clause.text.slice(0, 700)}…` : o.clause.text}
                          </blockquote>
                        </details>
                      ) : null}
                    </div>
                    <Status covered={o.covered_by} />
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

export function RiskRegister({ risks }: { risks: Risk[] }) {
  if (!risks.length) {
    return <p className="text-sm text-muted-foreground">The factor profile implies no risk in the register.</p>
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Derived from the factors, not generated: each risk cites the evidence it rests on, is scored likelihood ×
        impact from the factor levels, and is checked against the plan for its mitigations.
      </p>
      {risks.map((r) => (
        <div key={r.id} className="rounded-lg border p-3">
          <div className="flex flex-wrap items-start gap-2">
            <span
              className={cn(
                "inline-flex size-8 shrink-0 items-center justify-center rounded-md text-sm font-semibold tabular-nums",
                r.score >= 6 ? LEVEL_TONE.high : r.score >= 3 ? LEVEL_TONE.medium : LEVEL_TONE.low,
              )}
              title="likelihood × impact, 1-9"
            >
              {r.score}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{r.title}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span className={cn("rounded px-1.5 py-0.5", LEVEL_TONE[r.likelihood])}>likelihood {r.likelihood}</span>
                <span className={cn("rounded px-1.5 py-0.5", LEVEL_TONE[r.impact])}>impact {r.impact}</span>
                <span>owner: {r.owner}</span>
                {r.assumed ? <span title="an input factor was not stated and was read as medium">· partly assumed</span> : null}
                {r.note ? <span className="text-red-700 dark:text-red-400">· {r.note}</span> : null}
              </p>
            </div>
            {r.mitigated === false ? (
              <Badge variant="destructive" className="gap-1">
                <ShieldAlert className="size-3" /> unmitigated in plan
              </Badge>
            ) : null}
          </div>
          {r.evidence.length ? (
            <ul className="mt-2 space-y-1 border-l-2 pl-3 text-xs text-muted-foreground">
              {r.evidence.map((e, i) => (
                <li key={i}>
                  <span className="font-medium text-foreground">
                    {e.factor === "standard" ? "Standard" : `${factorLabel(e.factor)} ${e.level}`}
                  </span>
                  {e.evidence ? <> · <span className="italic">&ldquo;{e.evidence}&rdquo;</span></> : null}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="mt-2 grid gap-1 sm:grid-cols-2">
            {r.mitigations.map((m) => (
              <div key={m.id} className="flex items-start justify-between gap-2 rounded-md bg-muted/40 px-2 py-1 text-xs">
                <span>{m.description}</span>
                <Status covered={m.covered_by} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
