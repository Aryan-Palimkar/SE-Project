# SDLC Advisor - web frontend

An interface over the agent pipeline: paste a project brief, watch each agent step run, and get the requirements,
the SDLC recommendation, the 14 factors with the sentence behind each, the plan, the compliance map and an SRS.

* **Requirements** lists the functional and non-functional requirements in three groups: from the description (with
  the sentence each was quoted from), added from regulations by the retrieval step (with the clause), and inferred
  ones to confirm with a stakeholder. A citation badge expands to the text of the clause retrieved from the official
  document. When requirements are vague, **Clarify requirements** offers multiple-choice questions; the chosen
  answers are added to the brief and the analysis runs again.
* **Recommendation** shows the recommended lifecycle, the ranking of all five, the acceptable alternatives and any
  hybrid. When the rubric cannot separate the top models, **What would decide it** lists the facts that would settle
  it; clicking one applies it.
* **Factors** shows what the extractor read. Any factor can be corrected and the rubric rescores instantly (it is
  deterministic, so no model call is needed). **Regenerate plan** re-runs planning, checking and repair on the
  reviewed factors without re-reading the description.
* **Compliance & risk** lists the standards the description names or implies (`ontology/standards.yaml`), why each
  matched, and every obligation with the plan phase that covers it. A standard from the wrong jurisdiction can be
  marked not applicable. The risk register is derived from the factors; each risk cites its evidence and is checked
  against the plan for its mitigations. Each obligation can expand to its source text and page.
* **SRS** drafts a Software Requirements Specification from the run (ISO/IEC/IEEE 29148 layout), with a traceability
  matrix; download it as Markdown or print it (only the document is printed).

## Run it

From the repository root:

```bash
uvicorn server.app:app --port 8000    # the API; loads the model at startup (about 1 minute)
npm --prefix web run dev              # http://localhost:3000
```

Untick **Write an SDLC plan** for the fastest runs (requirements and recommendation in about 2-3 minutes; the plan
adds 3-10). Without a GPU, `SDLC_BACKEND=lexicon uvicorn server.app:app --port 8000` reads factors with a keyword
lexicon instead of the model and writes no plan.

| Variable | Default | |
|---|---|---|
| `SDLC_BACKEND` | `model` | `model` or `lexicon` |
| `SDLC_PRESET` | `4b` | model preset (see `agents/cli.py`) |
| `SDLC_PRELOAD` | `1` | load the model at startup instead of on the first request |
| `SDLC_ORIGINS` | `http://localhost:3000` | CORS origins, comma-separated |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | where the frontend finds the API |

## Layout

- `src/app/page.tsx` - thread, input, streaming
- `src/components/sdlc/` - requirements, recommendation, factor table, plan view, compliance view, SRS view,
  progress steps, run card
- `src/lib/api.ts` - typed client for `server/app.py`, including the server-sent-events reader
- `src/components/ui/` - [shadcn/ui](https://ui.shadcn.com) and
  [shadcn-chatbot-kit](https://github.com/Blazity/shadcn-chatbot-kit) components
