"use client"

import { RotateCcw, Sparkles } from "lucide-react"

import type { Factors, Level, Meta, Question } from "@/lib/api"
import { factorLabel, LEVEL_LABEL } from "@/lib/labels"
import { cn } from "@/lib/utils"

const ORDER: Level[] = ["low", "medium", "high", "not_stated"]
const SHORT: Record<Level, string> = { low: "Low", medium: "Med", high: "High", not_stated: "—" }

interface Props {
  meta: Meta
  extracted: Factors
  levels: Record<string, Level>
  questions: Question[]
  onSet: (factor: string, level: Level) => void
  onReset: (factor: string) => void
}

export function FactorTable({ meta, extracted, levels, questions, onSet, onReset }: Props) {
  const relevant = new Map(questions.map((q) => [q.factor, q]))
  return (
    <div className="divide-y rounded-lg border">
      {meta.factors.map((fm) => {
        const f = fm.name
        const level = levels[f] ?? "not_stated"
        const original = extracted[f]?.level ?? "not_stated"
        const edited = level !== original
        const evidence = extracted[f]?.evidence
        const q = relevant.get(f)
        return (
          <div key={f} className={cn("grid gap-2 p-3 sm:grid-cols-[13rem_1fr]", edited && "bg-muted/40")}>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium" title={fm.question}>
                  {factorLabel(f)}
                </span>
                {edited ? (
                  <button
                    onClick={() => onReset(f)}
                    title={`Back to the extracted level (${LEVEL_LABEL[original]})`}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <RotateCcw className="size-3" />
                  </button>
                ) : null}
              </div>
              <div className="mt-1.5 inline-flex rounded-md border p-0.5" role="radiogroup" aria-label={factorLabel(f)}>
                {ORDER.map((lv) => (
                  <button
                    key={lv}
                    role="radio"
                    aria-checked={level === lv}
                    title={lv === "not_stated" ? "Not stated" : (fm[lv] as string)}
                    onClick={() => onSet(f, lv)}
                    className={cn(
                      "rounded px-2 py-0.5 text-xs transition-colors",
                      level === lv
                        ? lv === "not_stated"
                          ? "bg-muted font-medium"
                          : "bg-foreground font-medium text-background"
                        : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    {SHORT[lv]}
                  </button>
                ))}
              </div>
            </div>
            <div className="min-w-0 text-sm">
              {edited ? (
                <p className="text-xs font-medium">
                  Set by you · extracted as {LEVEL_LABEL[original].toLowerCase()}
                </p>
              ) : null}
              {level !== "not_stated" && !edited && evidence ? (
                <blockquote className="border-l-2 pl-2.5 text-muted-foreground italic">“{evidence}”</blockquote>
              ) : null}
              {level !== "not_stated" ? (
                <p className="mt-1 text-xs text-muted-foreground">{fm[level as "low" | "medium" | "high"]}</p>
              ) : (
                <p className="text-xs text-muted-foreground">{fm.question}</p>
              )}
              {q && level === "not_stated" ? (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                  <Sparkles className="size-3 text-amber-600 dark:text-amber-400" />
                  <span className="font-medium text-amber-700 dark:text-amber-400">Would change the answer:</span>
                  {(["low", "medium", "high"] as const).map((lv) => (
                    <button
                      key={lv}
                      onClick={() => onSet(f, lv)}
                      title={q.descriptors[lv]}
                      className="rounded-full border px-2 py-0.5 hover:bg-muted"
                    >
                      {LEVEL_LABEL[lv].toLowerCase()} → {q.outcomes[lv]}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}
