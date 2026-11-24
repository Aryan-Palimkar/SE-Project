"use client"

import { useState } from "react"
import { Download, FileText, Loader2, Printer } from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { generateSrs, type Requirement, type RunStateDTO, type Srs } from "@/lib/api"

function H({ n, children }: { n: string; children: ReactNode }) {
  return (
    <h2 className="mt-8 mb-3 border-b pb-1 font-heading text-lg font-semibold">
      <span className="mr-2 text-muted-foreground tabular-nums">{n}</span>
      {children}
    </h2>
  )
}

function Sub({ children }: { children: ReactNode }) {
  return <h3 className="mt-5 mb-2 font-heading text-sm font-semibold">{children}</h3>
}

function basis(r: Requirement) {
  if (r.source) return <span className="italic">&ldquo;{r.source}&rdquo;</span>
  if (r.citation) return `${r.citation.standard.split(" - ")[0]} ${r.citation.ref}`
  return <span className="text-muted-foreground">Inferred - to confirm</span>
}

function ReqTable({ rows }: { rows: Requirement[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          <th className="w-24 py-1.5 pr-3 font-medium">ID</th>
          <th className="py-1.5 pr-3 font-medium">Requirement</th>
          <th className="w-[34%] py-1.5 font-medium">Basis</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-b align-top last:border-0">
            <td className="py-2 pr-3 font-mono text-xs">{r.id}</td>
            <td className="py-2 pr-3">{r.statement}</td>
            <td className="py-2 text-xs">{basis(r)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Document({ srs }: { srs: Srs }) {
  return (
    <article id="srs-print" className="rounded-lg border bg-card px-6 py-6 sm:px-10 sm:py-8">
      <header className="border-b pb-4 text-center">
        <p className="text-xs tracking-widest text-muted-foreground uppercase">Software Requirements Specification</p>
        <h1 className="mt-1 font-heading text-2xl font-semibold">{srs.title}</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Version {srs.version} · {srs.date} · structured after ISO/IEC/IEEE 29148
        </p>
      </header>

      <H n="1">Introduction</H>
      <Sub>1.1 Purpose</Sub>
      <p className="text-sm leading-relaxed">{srs.purpose || "-"}</p>
      <Sub>1.2 Scope</Sub>
      <p className="text-sm leading-relaxed">{srs.scope || "-"}</p>
      {srs.glossary.length ? (
        <>
          <Sub>1.3 Definitions</Sub>
          <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[12rem_1fr]">
            {srs.glossary.map((g) => (
              <div key={g.term} className="contents">
                <dt className="font-medium">{g.term}</dt>
                <dd className="text-muted-foreground">{g.definition}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}

      <H n="2">Overall description</H>
      {srs.stakeholders.length ? (
        <>
          <Sub>2.1 Stakeholders</Sub>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">
            {srs.stakeholders.map((s) => (
              <li key={s.role}>
                <span className="font-medium">{s.role}</span>: {s.interest}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <Sub>2.2 Operating environment</Sub>
      <p className="text-sm leading-relaxed">{srs.operating_environment || "-"}</p>
      <Sub>2.3 Constraints</Sub>
      <ul className="list-disc space-y-0.5 pl-5 text-sm">
        {(srs.constraints.length ? srs.constraints : ["-"]).map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <Sub>2.4 Assumptions and dependencies</Sub>
      <ul className="list-disc space-y-0.5 pl-5 text-sm">
        {(srs.assumptions.length ? srs.assumptions : ["-"]).map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>

      <H n="3">Requirements</H>
      <Sub>3.1 Functional requirements</Sub>
      {srs.functional.length ? <ReqTable rows={srs.functional} /> : <p className="text-sm">-</p>}
      {srs.non_functional.map((g, i) => (
        <div key={g.category}>
          <Sub>
            3.{i + 2} {g.category.charAt(0).toUpperCase() + g.category.slice(1)} requirements
          </Sub>
          <ReqTable rows={g.requirements} />
        </div>
      ))}

      <H n="4">Applicable regulations and standards</H>
      {srs.regulations.length ? (
        srs.regulations.map((reg) => (
          <div key={reg.standard} className="mb-4">
            <Sub>{reg.name}</Sub>
            <p className="mb-1.5 text-xs text-muted-foreground">
              {reg.basis === "named" ? "Named in the description" : "Inferred from"}: &ldquo;{reg.evidence}&rdquo;
            </p>
            <ul className="space-y-1.5 text-sm">
              {reg.obligations.map((o) => (
                <li key={o.id}>
                  <span className="font-medium">{o.ref}</span> - {o.text}
                  {o.page ? <span className="text-xs text-muted-foreground"> (source p. {o.page})</span> : null}
                </li>
              ))}
            </ul>
          </div>
        ))
      ) : (
        <p className="text-sm">No standard in the knowledge base applies to this description.</p>
      )}
      {srs.clauses.length ? (
        <>
          <Sub>Clauses retrieved from official documents</Sub>
          <ol className="space-y-2 text-xs leading-relaxed">
            {srs.clauses.map((c) => (
              <li key={c.id} className="border-l-2 border-primary/30 pl-3">
                <span className="font-medium text-foreground">
                  [{c.id}] {c.document}, p. {c.page}
                </span>
                <p className="text-muted-foreground">{c.text.length > 450 ? `${c.text.slice(0, 450)}…` : c.text}</p>
              </li>
            ))}
          </ol>
        </>
      ) : null}

      <H n="5">Recommended development lifecycle</H>
      {srs.sdlc ? (
        <p className="text-sm">
          <span className="font-medium">
            {srs.sdlc.primary}
            {srs.sdlc.hybrid.length ? ` with ${srs.sdlc.hybrid.join(", ")}` : ""}
          </span>
          {srs.sdlc.provisional || srs.sdlc.withheld ? " (provisional)" : ""}. Ranking: {srs.sdlc.ranking.join(" > ")}.
        </p>
      ) : (
        <p className="text-sm">Not enough information to recommend a lifecycle; see the open questions.</p>
      )}

      <H n="6">Traceability matrix</H>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-1.5 pr-3 font-medium">ID</th>
            <th className="py-1.5 pr-3 font-medium">Source</th>
            <th className="py-1.5 pr-3 font-medium">Regulation</th>
            <th className="py-1.5 font-medium">Verification</th>
          </tr>
        </thead>
        <tbody>
          {srs.traceability.map((t) => (
            <tr key={t.id} className="border-b align-top last:border-0">
              <td className="py-1.5 pr-3 font-mono">{t.id}</td>
              <td className="py-1.5 pr-3">{t.source ? `“${t.source.slice(0, 90)}${t.source.length > 90 ? "…" : ""}”` : t.basis}</td>
              <td className="py-1.5 pr-3">{t.regulation || "-"}</td>
              <td className="py-1.5">{t.verification}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {srs.open_questions.length ? (
        <>
          <H n="7">Open questions</H>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {srs.open_questions.map((q) => (
              <li key={q.question}>
                {q.question}
                {q.options.length ? <span className="text-muted-foreground"> Options: {q.options.join("; ")}.</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </article>
  )
}

export function SrsView({ state, available }: { state: RunStateDTO; available: boolean }) {
  const [doc, setDoc] = useState<{ srs: Srs; markdown: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generate = () => {
    setBusy(true)
    setError(null)
    generateSrs(state)
      .then(setDoc)
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setBusy(false))
  }

  const download = () => {
    if (!doc) return
    const url = URL.createObjectURL(new Blob([doc.markdown], { type: "text/markdown" }))
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `${(doc.srs.title || "srs").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-srs.md`,
    })
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!doc) {
    return (
      <div className="rounded-lg border bg-card px-6 py-8 text-center">
        <FileText className="mx-auto size-8 text-primary" />
        <h3 className="mt-2 font-heading text-lg font-semibold">Software Requirements Specification</h3>
        <p className="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">
          Drafts an SRS following ISO/IEC/IEEE 29148 from this analysis: introduction, stakeholders, constraints drawn
          from the retrieved regulatory clauses, the requirement tables, applicable regulations, the recommended
          lifecycle and a traceability matrix.
        </p>
        <Button className="mt-4" onClick={generate} disabled={busy || !available}>
          {busy ? <Loader2 className="animate-spin" /> : <FileText />}
          {busy ? "Drafting the SRS (about a minute)…" : "Generate SRS"}
        </Button>
        {!available ? <p className="mt-2 text-xs text-muted-foreground">No requirements in this run.</p> : null}
        {error ? <p className="mt-2 text-xs text-destructive">{error}</p> : null}
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap justify-end gap-2 print:hidden">
        <Button size="sm" variant="outline" onClick={download}>
          <Download /> Download (.md)
        </Button>
        <Button size="sm" variant="outline" onClick={() => window.print()}>
          <Printer /> Print / save as PDF
        </Button>
        <Button size="sm" variant="ghost" onClick={generate} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : null} Regenerate
        </Button>
      </div>
      <Document srs={doc.srs} />
    </div>
  )
}
