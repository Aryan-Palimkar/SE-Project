export interface Suggestion {
  title: string
  tag: string
  text: string
}

interface PromptSuggestionsProps {
  label: string
  append: (message: { role: "user"; content: string }) => void
  suggestions: Suggestion[]
}

export function PromptSuggestions({ label, append, suggestions }: PromptSuggestionsProps) {
  return (
    <div className="space-y-3">
      <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {suggestions.map((s) => (
          <button
            key={s.title}
            onClick={() => append({ role: "user", content: s.text })}
            className="rounded-lg border bg-card p-4 text-left shadow-xs transition-colors hover:border-primary/50 hover:bg-accent/40"
          >
            <div className="flex items-baseline justify-between gap-2">
              <p className="font-heading font-semibold">{s.title}</p>
              <span className="shrink-0 text-xs text-muted-foreground">{s.tag}</span>
            </div>
            <p className="mt-1.5 line-clamp-3 text-sm text-muted-foreground">{s.text}</p>
          </button>
        ))}
      </div>
    </div>
  )
}
