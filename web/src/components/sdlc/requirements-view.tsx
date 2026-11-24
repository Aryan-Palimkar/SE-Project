"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight, HelpCircle, MessageSquareText, Quote, Scale } from "lucide-react"
import type { ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Clause, Requirement, RequirementQuestion } from "@/lib/api"
import { cn } from "@/lib/utils"

const GROUPS: { basis: Requirement["basis"]; title: string; note: string; icon: ReactNode }[] = [
  {
    basis: "stated",
    title: "From the description",
    note: "Each requirement quotes the sentence it comes from.",
    icon: <Quote className="size-4" />,
  },
  {
    basis: "regulation",
    title: "From applicable regulations",
    note: "Not stated in the description: derived from regulatory clauses retrieved for this project.",
    icon: <Scale className="size-4" />,
  },
  {
    basis: "inferred",
    title: "Inferred - to confirm",
    note: "Proposed by the model without a supporting sentence in the description.",
    icon: <HelpCircle className="size-4" />,
  },
]

function ClauseText({ clause }: { clause: Clause }) {
  return (
    <blockquote className="mt-2 border-l-2 border-primary/40 bg-muted/40 py-2 pr-2 pl-3 text-xs leading-relaxed text-muted-foreground">
      <p className="mb-1 font-medium text-foreground">
        {clause.document}, p. {clause.page}
      </p>
      {clause.text.length > 700 ? `${clause.text.slice(0, 700)}…` : clause.text}
    </blockquote>
  )
}

function Row({ r }: { r: Requirement }) {
  const [open, setOpen] = useState(false)
  const clause = r.citation?.clause
  return (
    <li className="grid gap-1 px-4 py-3 text-sm sm:grid-cols-[6.5rem_1fr] sm:gap-4">
      <span className="font-mono text-xs leading-6 text-muted-foreground">{r.id}</span>
      <div className="min-w-0 space-y-1.5">
        <p className="leading-6">{r.statement}</p>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-normal">
            {r.category}
          </Badge>
          {r.citation ? (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              disabled={!clause}
              className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-foreground enabled:hover:bg-muted"
              title={clause ? "Show the clause this is based on" : r.citation.standard}
            >
              {clause ? open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" /> : null}
              {r.citation.standard.split(" - ")[0]} {r.citation.ref}
            </button>
          ) : null}
          {r.source ? <span className="italic">&ldquo;{r.source}&rdquo;</span> : null}
        </div>
        {open && clause ? <ClauseText clause={clause} /> : null}
      </div>
    </li>
  )
}

function Questions({
  questions,
  onApply,
  busy,
}: {
  questions: RequirementQuestion[]
  onApply: (answers: Record<string, string>) => void
  busy: boolean
}) {
  const [chosen, setChosen] = useState<Record<string, string>>({})
  const answered = Object.keys(chosen).length
  return (
    <section className="rounded-lg border border-primary/25 bg-primary/[0.03]">
      <div className="border-b border-primary/15 px-4 py-3">
        <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
          <MessageSquareText className="size-4 text-primary" /> Clarify requirements
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          These requirements are not yet precise enough to agree on. Pick the option that fits; the answers are added
          to the description and the analysis is run again.
        </p>
      </div>
      <ol className="divide-y divide-primary/10">
        {questions.map((q, i) => (
          <li key={q.id} className="px-4 py-3">
            <p className="text-sm font-medium">
              {i + 1}. {q.question}
              {q.requirements.length ? (
                <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">{q.requirements.join(", ")}</span>
              ) : null}
            </p>
            <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
              {q.options.map((option) => {
                const active = chosen[q.id] === option
                return (
                  <label
                    key={option}
                    className={cn(
                      "flex cursor-pointer items-start gap-2 rounded-md border bg-card px-3 py-2 text-sm transition-colors",
                      active ? "border-primary ring-1 ring-primary/40" : "hover:border-primary/40",
                    )}
                  >
                    <input
                      type="radio"
                      name={q.id}
                      className="mt-1 accent-[var(--primary)]"
                      checked={active}
                      onChange={() => setChosen((c) => ({ ...c, [q.id]: option }))}
                    />
                    <span>{option}</span>
                  </label>
                )
              })}
            </div>
          </li>
        ))}
      </ol>
      <div className="flex items-center justify-end gap-3 border-t border-primary/15 px-4 py-2.5">
        <span className="text-xs text-muted-foreground">
          {answered} of {questions.length} answered
        </span>
        <Button size="sm" disabled={!answered || busy} onClick={() => onApply(chosen)}>
          Apply answers and re-run
        </Button>
      </div>
    </section>
  )
}

export function RequirementsView({
  requirements,
  questions = [],
  onClarify,
  busy = false,
}: {
  requirements: Requirement[]
  questions?: RequirementQuestion[]
  onClarify?: (answers: Record<string, string>) => void
  busy?: boolean
}) {
  if (!requirements.length) {
    return <p className="text-sm text-muted-foreground">No requirements were identified for this run.</p>
  }
  const functional = requirements.filter((r) => r.type === "functional").length
  const cited = requirements.filter((r) => r.citation).length
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Requirements", requirements.length],
          ["Functional", functional],
          ["Non-functional", requirements.length - functional],
          ["Linked to a regulation", cited],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border bg-card px-3 py-2.5">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-heading text-2xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      {questions.length && onClarify ? <Questions questions={questions} onApply={onClarify} busy={busy} /> : null}

      {GROUPS.map((g) => {
        const rows = requirements.filter((r) => r.basis === g.basis)
        if (!rows.length) return null
        return (
          <section key={g.basis} className="overflow-hidden rounded-lg border bg-card">
            <div className="border-b bg-muted/40 px-4 py-2.5">
              <h3 className="flex items-center gap-2 font-heading text-base font-semibold">
                {g.icon} {g.title}{" "}
                <span className="font-sans text-sm font-normal text-muted-foreground tabular-nums">({rows.length})</span>
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">{g.note}</p>
            </div>
            <ul className="divide-y">
              {rows.map((r) => (
                <Row key={r.id} r={r} />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
