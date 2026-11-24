"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Cpu, FlaskConical, Moon, Plus, Sun } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MessageInput } from "@/components/ui/message-input"
import { PromptSuggestions, type Suggestion } from "@/components/ui/prompt-suggestions"
import { type Run, RunCard } from "@/components/sdlc/run-card"
import { type Factors, getMeta, type Meta, type RequirementQuestion, stream, type StreamEvent } from "@/lib/api"

type Message =
  | { id: string; role: "user"; text: string; addition: boolean }
  | { id: string; role: "assistant"; run: Run }

const SUGGESTIONS: Suggestion[] = [
  {
    title: "Video KYC for a bank",
    tag: "RBI · DPDP · CERT-In",
    text: "Sahyadri Bank, a private sector bank regulated by the RBI, wants new savings account customers to complete KYC through its mobile app using video-based customer identification. Customers complete Aadhaar OTP e-KYC, upload their PAN and join a live video call with a trained bank official. Calls from outside India must be blocked and recordings stored on servers in India. The app will hold Aadhaar numbers, PAN and video recordings, the RBI may inspect the controls, and the video-KYC vendor has not been integrated with the core banking system before.",
  },
  {
    title: "Digital lending app",
    tag: "RBI · NBFC",
    text: "An NBFC registered with the Reserve Bank of India is launching a mobile app for personal loans of ₹10,000 to ₹2 lakh. Before signing, borrowers must see a Key Fact Statement with the annual percentage rate and all fees. The app may access the camera and location only with consent. The credit team changes the scoring rules every month and the product team releases every two weeks.",
  },
  {
    title: "State scholarship portal",
    tag: "GIGW 3.0 · Aadhaar",
    text: "The higher education department of a state government wants a scholarship portal and app. Students register with an Aadhaar-linked mobile number and upload certificates; colleges verify them and the department pays through direct benefit transfer. The portal must follow the Guidelines for Indian Government Websites and Apps and pass a security audit. The rules are fixed by a government order and the scope is fixed in a tender.",
  },
  {
    title: "Community events app",
    tag: "no regulator",
    text: "Four of us are building a neighbourhood events app. We want something in front of real users in six weeks, then add or drop features based on what people use. The founders sit with the developer every day and we ship weekly.",
  },
]

const uid = () => Math.random().toString(36).slice(2)

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [description, setDescription] = useState<string | null>(null)
  const [dark, setDark] = useState(false)
  const [thorough, setThorough] = useState(false)
  const [withPlan, setWithPlan] = useState(true)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const running = messages.some((m) => m.role === "assistant" && m.run.status === "running")

  useEffect(() => {
    getMeta().then(setMeta).catch((e) => setMetaError(String(e.message ?? e)))
    try {
      const saved = localStorage.getItem("theme")
      const d = saved === "dark"
      setDark(d)
    } catch {}
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages.length])

  const patchRun = useCallback((id: string, patch: (r: Run) => Run) => {
    setMessages((ms) => ms.map((m) => (m.role === "assistant" && m.run.id === id ? { ...m, run: patch(m.run) } : m)))
  }, [])

  const start = useCallback(
    async (kind: Run["kind"], body: object, text: string, planned: boolean) => {
      if (!meta) return
      const run: Run = {
        id: uid(),
        kind,
        planned,
        description: text,
        status: "running",
        backend: meta.backend,
        queued: false,
        loadingModel: false,
        started: Date.now(),
        steps: [],
      }
      setMessages((ms) => [...ms, { id: uid(), role: "assistant", run }])
      const ctl = new AbortController()
      abort.current = ctl
      const onEvent = (e: StreamEvent) =>
        patchRun(run.id, (r) => {
          switch (e.type) {
            case "accepted":
              return { ...r, queued: e.queued, loadingModel: e.loading }
            case "queued":
              return { ...r, queued: true }
            case "start":
              return { ...r, queued: false, backend: e.backend, loadingModel: r.loadingModel || e.loading, started: Date.now() }
            case "step":
              return { ...r, loadingModel: false, lastStepAt: Date.now(), steps: [...r.steps, e] }
            case "result":
              return { ...r, status: "done", result: e }
            case "error":
              return { ...r, status: "error", error: e.message }
          }
        })
      try {
        await stream(kind === "analyze" ? "/api/analyze" : "/api/replan", body, onEvent, ctl.signal)
      } catch (err) {
        if (ctl.signal.aborted) patchRun(run.id, (r) => ({ ...r, status: r.result ? "done" : "stopped" }))
        else patchRun(run.id, (r) => ({ ...r, status: "error", error: String((err as Error).message ?? err) }))
      }
      getMeta().then(setMeta).catch(() => {})
    },
    [meta, patchRun],
  )

  const send = (text: string) => {
    const clean = text.trim()
    if (!clean || running) return
    // a follow-up adds to the same project rather than starting a new one
    const addition = description !== null
    const full = addition ? `${description} ${clean}` : clean
    setDescription(full)
    setMessages((ms) => [...ms, { id: uid(), role: "user", text: clean, addition }])
    setInput("")
    start("analyze", { description: full, thorough, plan: withPlan }, full, withPlan)
  }

  const clarify = (answers: Record<string, string>, questions: RequirementQuestion[]) => {
    const lines = questions.filter((q) => answers[q.id]).map((q) => `${q.question} ${answers[q.id]}.`)
    if (lines.length) send(`Clarifications: ${lines.join(" ")}`)
  }

  const replan = (factors: Factors) => {
    if (!description || running) return
    setMessages((ms) => [
      ...ms,
      { id: uid(), role: "user", text: "Regenerate the plan with my reviewed factors.", addition: false },
    ])
    start("replan", { description, factors, thorough }, description, true)
  }

  const reset = () => {
    abort.current?.abort()
    setMessages([])
    setDescription(null)
    setInput("")
  }

  const toggleTheme = () => {
    setDark((d) => {
      try {
        localStorage.setItem("theme", d ? "light" : "dark")
      } catch {}
      return !d
    })
  }

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-2.5 sm:py-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary font-heading text-sm font-semibold text-primary-foreground">
            SA
          </div>
          <div className="min-w-0">
            <h1 className="truncate font-heading text-lg leading-tight font-semibold">SDLC Advisor</h1>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              Requirements engineering and lifecycle selection, grounded in the project brief and applicable regulations
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            {meta ? (
              <Badge variant="outline" className="hidden gap-1 sm:inline-flex">
                {meta.backend === "lexicon" ? <FlaskConical className="size-3" /> : <Cpu className="size-3" />}
                {meta.backend === "lexicon" ? "CPU demo" : `Qwen3-${meta.preset.toUpperCase()}`}
                {meta.backend === "model"
                  ? meta.loading
                    ? " · loading…"
                    : meta.model_loaded
                      ? " · loaded"
                      : " · loads on first run"
                  : ""}
              </Badge>
            ) : null}
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
              {dark ? <Sun /> : <Moon />}
            </Button>
            <Button variant="outline" size="sm" onClick={reset} disabled={!messages.length}>
              <Plus /> New project
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 space-y-4 px-4 py-6">
        {metaError ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
            <p className="font-medium">Cannot reach the API</p>
            <p className="mt-1 text-muted-foreground">
              Start it from the repository root: <code>uvicorn server.app:app --port 8000</code> (add{" "}
              <code>SDLC_BACKEND=lexicon</code> for the CPU demo). {metaError}
            </p>
          </div>
        ) : null}

        {!messages.length && meta ? (
          <div className="pt-6 sm:pt-12">
            <div className="mb-8 text-center">
              <h2 className="font-heading text-2xl font-semibold sm:text-3xl">Analyse a software project</h2>
              <p className="mx-auto mt-2 max-w-2xl text-sm text-muted-foreground">
                Paste a project brief. The agents list its requirements (citing the sentence or regulatory clause
                behind each), ask about anything unclear, recommend a development lifecycle and draft an SRS.
              </p>
            </div>
            <PromptSuggestions label="Or start from an example" append={(m) => send(m.content)} suggestions={SUGGESTIONS} />
          </div>
        ) : null}

        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="rounded-lg border-l-4 border-primary bg-card px-4 py-3 shadow-xs">
              <p className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {m.addition ? "Added to the brief" : "Project brief"}
              </p>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{m.text}</p>
            </div>
          ) : (
            <div key={m.id} className="flex">
              {meta ? <RunCard run={m.run} meta={meta} onReplan={replan} onClarify={clarify} busy={running} /> : null}
            </div>
          ),
        )}
        <div ref={bottom} />
      </main>

      <div className="sticky bottom-0 border-t bg-background/85 backdrop-blur">
        <form
          className="mx-auto max-w-5xl px-4 py-2 sm:py-3"
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
        >
          <MessageInput
            value={input}
            onChange={(e) => setInput(e.target.value)}
            isGenerating={running}
            stop={() => abort.current?.abort()}
            placeholder={
              description ? "Add detail - e.g. “the contract fixes the scope”…" : "Paste or describe a software project…"
            }
            disabled={!meta}
          />
          <div className="mt-1.5 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            {meta?.backend === "model" ? (
              <label
                className="inline-flex cursor-pointer items-center gap-1.5"
                title="Requirements and the SDLC recommendation take about 3 minutes; writing, checking and repairing the plan adds 3-10 more."
              >
                <input
                  type="checkbox"
                  className="size-3.5 accent-foreground"
                  checked={withPlan}
                  onChange={(e) => setWithPlan(e.target.checked)}
                  disabled={running}
                />
                Write an SDLC plan (+3-10 min)
              </label>
            ) : null}
            {meta?.backend === "model" && withPlan ? (
              <label
                className="inline-flex cursor-pointer items-center gap-1.5"
                title="The repair loop also feeds back compliance obligations the plan does not cover."
              >
                <input
                  type="checkbox"
                  className="size-3.5 accent-foreground"
                  checked={thorough}
                  onChange={(e) => setThorough(e.target.checked)}
                  disabled={running}
                />
                Thorough compliance check (about +4 min)
              </label>
            ) : null}
            <span className="hidden sm:inline">Decision support for analysts: every output cites its source.</span>
          </div>
        </form>
      </div>
    </div>
  )
}
