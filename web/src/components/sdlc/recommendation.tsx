"use client"

import { AlertTriangle, CheckCircle2, CircleSlash, Info, Scale } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { Level, Meta, Rubric } from "@/lib/api"
import { factorLabel, LEVEL_LABEL, MIN_STATED, MODEL_BLURB, MODEL_VAR } from "@/lib/labels"
import { cn } from "@/lib/utils"

interface Props {
  rubric: Rubric
  stated: number
  total: number
  meta: Meta
  levels: Record<string, Level>
  onSet: (factor: string, level: Level) => void
}

function Headline({ rubric, stated, total, meta }: Omit<Props, "levels" | "onSet">) {
  if (stated < MIN_STATED) {
    return (
      <div className="flex items-start gap-3">
        <CircleSlash className="mt-1 size-6 shrink-0 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium text-muted-foreground">No recommendation</p>
          <h2 className="text-2xl font-semibold tracking-tight">Not enough to go on</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Only {stated} of {total} characteristics could be read from the description. Any ranking now
            would reflect the rubric&apos;s tie-break order, not your project. Set a few factors below, or
            answer the questions.
          </p>
        </div>
      </div>
    )
  }
  if (rubric.primary_withheld) {
    const precondition = rubric.triggered_rules.includes("PRECONDITION_UNMET")
    const needs = Object.entries(meta.preconditions[rubric.primary] ?? {})
      .map(([f, lv]) => `${factorLabel(f).toLowerCase()} ${lv.join("/")}`)
      .join(" or ")
    return (
      <div className="flex items-start gap-3">
        <Scale className="mt-1 size-6 shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <p className="text-sm font-medium text-amber-700 dark:text-amber-400">No single lifecycle</p>
          <h2 className="text-2xl font-semibold tracking-tight">
            {rubric.acceptable_set.join(" · ")}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {precondition ? (
              <>
                {rubric.primary} ranks first, but the description states nothing {rubric.primary} needs
                ({needs}), so the ranking is not evidence for it.
              </>
            ) : (
              <>The leading lifecycles are level on the stated evidence.</>
            )}
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-start gap-3">
      <CheckCircle2 className="mt-1 size-6 shrink-0" style={{ color: MODEL_VAR[rubric.primary] }} />
      <div>
        <p className="text-sm font-medium text-muted-foreground">Recommended lifecycle</p>
        <h2 className="text-2xl font-semibold tracking-tight">
          {rubric.primary}
          {rubric.hybrid?.overlays.length ? (
            <span className="font-normal text-muted-foreground"> with {rubric.hybrid.overlays.join(", ")}</span>
          ) : null}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{MODEL_BLURB[rubric.primary]}</p>
      </div>
    </div>
  )
}

function ScoreBars({ rubric }: { rubric: Rubric }) {
  const max = Math.max(1, ...Object.values(rubric.scores).map((s) => Math.abs(s)))
  return (
    <div className="space-y-1.5">
      {rubric.ranking.map((m, i) => {
        const s = rubric.scores[m]
        const width = `${(Math.abs(s) / max) * 50}%`
        const inSet = rubric.acceptable_set.includes(m)
        const supported = rubric.supported_models?.includes(m)
        return (
          <div key={m} className="grid grid-cols-[7.5rem_1fr_3rem] items-center gap-3 text-sm">
            <div className={cn("flex items-center gap-1.5 truncate", inSet ? "font-medium" : "text-muted-foreground")}>
              <span className="w-3 text-xs tabular-nums text-muted-foreground">{i + 1}</span>
              <span className="truncate">{m}</span>
              {supported ? (
                <CheckCircle2 className="size-3 shrink-0 text-muted-foreground" aria-label="its defining conditions are stated" />
              ) : null}
            </div>
            <div className="relative h-5 rounded bg-muted/60">
              <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
              <div
                className={cn("absolute inset-y-0.5 rounded-sm transition-all duration-500", !inSet && "opacity-35")}
                style={{
                  width,
                  left: s >= 0 ? "50%" : undefined,
                  right: s < 0 ? "50%" : undefined,
                  background: MODEL_VAR[m],
                }}
              />
            </div>
            <div className="text-right tabular-nums text-muted-foreground">{s > 0 ? `+${s}` : s}</div>
          </div>
        )
      })}
      <p className="pt-1 text-xs text-muted-foreground">
        Rubric scores (centre = 0). Faded = outside the defensible set.
        {rubric.supported_models ? " ✓ = its defining conditions are stated." : ""}
      </p>
    </div>
  )
}

function Deciders({ rubric, meta, levels, onSet }: Pick<Props, "rubric" | "meta" | "levels" | "onSet">) {
  if (!rubric.primary_withheld) return null
  const rows = rubric.acceptable_set
    .map((m) => ({ m, conds: Object.entries(meta.preconditions[m] ?? {}) }))
    .filter((r) => r.conds.length)
  if (!rows.length) return null
  return (
    <div className="rounded-lg border border-dashed p-3">
      <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
        <Info className="size-4" /> What would decide it
      </p>
      <p className="mb-3 text-xs text-muted-foreground">
        If one of these is true of your project, click it. The rubric rescores instantly; nothing is re-read.
      </p>
      <div className="space-y-2">
        {rows.map(({ m, conds }) => (
          <div key={m} className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="w-24 shrink-0 font-medium" style={{ color: MODEL_VAR[m] }}>
              {m}
            </span>
            <span className="text-xs text-muted-foreground">if</span>
            {conds.flatMap(([f, lvls]) =>
              lvls.map((lv) => {
                const on = levels[f] === lv
                return (
                  <button
                    key={`${f}-${lv}`}
                    onClick={() => onSet(f, on ? "not_stated" : lv)}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                      on ? "border-foreground bg-foreground text-background" : "hover:bg-muted",
                    )}
                  >
                    {factorLabel(f)} = {LEVEL_LABEL[lv].toLowerCase()}
                  </button>
                )
              }),
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function Recommendation(props: Props) {
  const { rubric, stated, total } = props
  const contributors = rubric.top_contributors[rubric.primary] ?? []
  return (
    <div className="space-y-5">
      <Headline {...props} />
      <div className="flex flex-wrap gap-1.5">
        {rubric.low_evidence ? (
          <Badge variant="outline" className="gap-1">
            <AlertTriangle className="size-3" /> Provisional · {stated} of {total} factors stated
          </Badge>
        ) : (
          <Badge variant="secondary">
            {stated} of {total} factors stated
          </Badge>
        )}
        {!rubric.primary_withheld && stated >= MIN_STATED ? (
          <Badge variant="secondary">Lead of {rubric.margin} over the runner-up</Badge>
        ) : null}
        {rubric.triggered_rules.includes("C3") ? (
          <Badge variant="secondary">Frequent delivery rules out plan-driven models</Badge>
        ) : null}
        <Badge variant="outline">Rubric v{rubric.rubric_version}</Badge>
      </div>
      <ScoreBars rubric={rubric} />
      <Deciders {...props} />
      {!rubric.primary_withheld && stated >= MIN_STATED && contributors.length ? (
        <p className="text-sm text-muted-foreground">
          Driven mostly by{" "}
          {contributors.map((f, i) => (
            <span key={f}>
              <span className="font-medium text-foreground">{factorLabel(f).toLowerCase()}</span>
              {i < contributors.length - 2 ? ", " : i === contributors.length - 2 ? " and " : ""}
            </span>
          ))}
          .
        </p>
      ) : null}
    </div>
  )
}
