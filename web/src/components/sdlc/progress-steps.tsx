"use client"

import { useEffect, useState } from "react"
import { Check, Circle, Loader2, X } from "lucide-react"

import type { StepEvent } from "@/lib/api"
import { NODE_LABEL } from "@/lib/labels"
import { cn } from "@/lib/utils"

interface Props {
  expected: string[]
  steps: StepEvent[]
  running: boolean
  loadingModel: boolean
  queued: boolean
  since: number
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(t)
  }, [])
  return <span className="tabular-nums">{Math.max(0, (now - since) / 1000).toFixed(0)}s</span>
}

export function ProgressSteps({ expected, steps, running, loadingModel, queued, since }: Props) {
  // one row per node; the latest outcome wins
  const done = new Map<string, StepEvent>()
  for (const s of steps) done.set(s.node, s)
  const rows = [...new Set([...expected, ...steps.map((s) => s.node)])]
  const current = running ? rows.find((n) => !done.has(n)) : undefined
  return (
    <div className="space-y-1.5 text-sm">
      {queued ? <p className="text-xs text-muted-foreground">Waiting for the GPU - another run is in progress…</p> : null}
      {loadingModel && !steps.length ? (
        <p className="text-xs text-muted-foreground">Loading the model onto the GPU (first run only, about a minute)…</p>
      ) : null}
      {rows.map((node) => {
        const s = done.get(node)
        const active = node === current
        return (
          <div key={node} className={cn("flex items-center gap-2", !s && !active && "text-muted-foreground/60")}>
            {s ? (
              s.ok ? (
                <Check className="size-4 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <X className="size-4 text-destructive" />
              )
            ) : active ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Circle className="size-4" />
            )}
            <span className={cn(active && "font-medium")}>{NODE_LABEL[node] ?? node}</span>
            <span className="ml-auto text-xs text-muted-foreground">
              {s ? `${s.seconds.toFixed(1)}s` : active ? <Elapsed since={since} /> : ""}
            </span>
          </div>
        )
      })}
      {running && current === "plan" ? (
        <p className="pt-1 text-xs text-muted-foreground">
          The plan is written by a 4B model on this machine&apos;s GPU and can take a few minutes.
        </p>
      ) : null}
    </div>
  )
}
