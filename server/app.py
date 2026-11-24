"""HTTP API for the web frontend.

  uvicorn server.app:app --port 8000                      # model backend (GPU)
  SDLC_BACKEND=lexicon uvicorn server.app:app --port 8000  # CPU only, keyword lexicon, no plan

Endpoints
  GET  /api/meta      ontology, rubric version, backend mode
  POST /api/score     {levels} -> rubric result and clarifying questions
  POST /api/analyze   {description} -> server-sent events per agent node, then the result
  POST /api/replan    {description, factors} -> same, starting after extraction
  POST /api/assess    {description, factors, plan?} -> compliance map and risk register
  POST /api/unload    free the GPU
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.questions import decision_relevant
from agents.state import RunState
from core.config import load_factor_ontology
from rubric.scorer import load_rubric, score
from train.tasks import LEVELS

BACKEND = os.environ.get("SDLC_BACKEND", "model")          # "model" | "lexicon"
PRESET = os.environ.get("SDLC_PRESET", "4b")
# load the model at startup (model backend only)
PRELOAD = os.environ.get("SDLC_PRELOAD", "1") == "1"
ONTO = load_factor_ontology()
NAMES = list(ONTO["factors"])

_preloading = threading.Event()


def _warm_retrieval() -> None:
    """Load the embedding model used by compliance retrieval ahead of the first request."""
    try:
        from compliance.retrieve import _scope_vectors
        _scope_vectors()
    except Exception as exc:
        print(f"retrieval warm-up failed: {type(exc).__name__}: {exc}")


def _preload() -> None:
    """Load the retrieval embedder, then the base model and extractor, under the GPU lock so early
    requests wait. Loading two models from different threads at once is not safe."""
    _preloading.set()
    try:
        with _gpu:
            _warm_retrieval()
            _get_pipeline()
            _hub.ensure("extract")
    except Exception as exc:
        print(f"preload failed: {type(exc).__name__}: {exc}")
    finally:
        _preloading.clear()


@asynccontextmanager
async def lifespan(_app):
    preload = BACKEND == "model" and PRELOAD
    threading.Thread(target=_preload if preload else _warm_retrieval, daemon=True).start()
    yield


app = FastAPI(title="SDLC recommender", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("SDLC_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["*"], allow_headers=["*"])

_gpu = threading.Lock()          # one GPU, one run at a time
_hub = None
_pipeline = None


def _get_pipeline():
    """The shipped pipeline, built once and kept loaded between requests."""
    global _hub, _pipeline
    if _pipeline is None:
        from agents.cli import PRESETS
        from agents.orchestrator import local_pipeline
        cfg = PRESETS[PRESET]
        plan_adapter = None if cfg["plan_adapter"].lower() == "none" else cfg["plan_adapter"]
        _pipeline, _hub = local_pipeline(cfg["model_id"], cfg["extract_adapter"], plan_adapter,
                                         repair_scope=cfg["repair_scope"],
                                         constrained_extract=cfg["constrained_extract"])
    return _pipeline


def _lexicon_pipeline():
    """Deterministic stand-in: no model calls at all."""
    from agents.orchestrator import Pipeline
    return Pipeline(extractor=None, planner=None, max_repairs=0)


def _clean(levels: dict) -> dict:
    return {f: (levels.get(f) if levels.get(f) in LEVELS else "not_stated") for f in NAMES}


def analysis(levels: dict) -> dict:
    """Everything the UI shows that the rubric decides, for one set of levels."""
    rubric = load_rubric()
    lv = _clean(levels)
    result = score(lv, rubric)
    questions = []
    for q in decision_relevant(lv, rubric):
        d = ONTO["factors"][q["factor"]]
        questions.append({"factor": q["factor"], "question": d["question"], "outcomes": q["outcomes"],
                          "could_lead_to": q["primaries"],
                          "descriptors": {k: d[k] for k in ("low", "medium", "high")}})
    return {"rubric": result, "questions": questions,
            "stated": sum(v != "not_stated" for v in lv.values())}


class ScoreIn(BaseModel):
    levels: dict[str, str]


class AnalyzeIn(BaseModel):
    description: str
    thorough: bool = False
    plan: bool = True


class AssessIn(BaseModel):
    description: str
    factors: dict[str, dict]
    plan: dict | None = None


class ReplanIn(BaseModel):
    description: str
    factors: dict[str, dict]
    thorough: bool = False


class SrsIn(BaseModel):
    state: dict


@app.get("/api/meta")
def meta() -> dict:
    rubric = load_rubric()
    return {
        "backend": BACKEND, "preset": PRESET, "model_loaded": bool(_hub and _hub.loaded),
        "busy": _gpu.locked(), "loading": _preloading.is_set(),
        "rubric_version": rubric["version"], "models": rubric["models"],
        "preconditions": (rubric.get("preconditions") or {}).get("models", {}),
        "factors": [{"name": n, **{k: ONTO["factors"][n].get(k) for k in ("question", "low", "medium", "high")}}
                    for n in NAMES],
    }


@app.post("/api/score")
def score_levels(body: ScoreIn) -> dict:
    unknown = set(body.levels) - set(NAMES)
    if unknown:
        raise HTTPException(422, f"unknown factors: {sorted(unknown)}")
    return analysis(body.levels)


@app.post("/api/assess")
def assess(body: AssessIn) -> dict:
    from compliance.analysis import analyse
    factors = {f: {"level": _clean({f: (body.factors.get(f) or {}).get("level")})[f],
                   "evidence": (body.factors.get(f) or {}).get("evidence")} for f in NAMES}
    return analyse(" ".join(body.description.split()), factors, body.plan)


@app.post("/api/srs")
def srs_document(body: SrsIn) -> dict:
    """Draft the SRS for a finished run (the run's state as returned by /api/analyze)."""
    from agents import srs
    state = RunState.from_dict(body.state)
    if BACKEND == "model":
        with _gpu:
            srs.write(state, _get_pipeline().requirements_agent)
    else:
        srs.write(state, None)
    return {"srs": state.srs, "markdown": srs.markdown(state.srs)}


@app.post("/api/unload")
def unload() -> dict:
    global _hub, _pipeline
    with _gpu:
        if _hub is not None:
            _hub.unload()
        _hub, _pipeline = None, None
    return {"ok": True}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _stream(job) -> Iterator[str]:
    """Run `job(on_step)` in a thread and relay each node's log entry as it lands."""
    events: queue.Queue = queue.Queue()
    sent = {"n": 0}

    def on_step(state: RunState) -> None:
        for s in state.log[sent["n"]:]:
            events.put({"type": "step", "node": s.node, "ok": s.ok, "seconds": s.seconds, "detail": s.detail})
        sent["n"] = len(state.log)

    def worker() -> None:
        if _gpu.locked():
            events.put({"type": "queued"})
        with _gpu:
            started = time.time()
            events.put({"type": "start", "backend": BACKEND,
                        "loading": BACKEND == "model" and not (_hub and _hub.loaded)})
            try:
                state = job(on_step)
                events.put({"type": "result", "seconds": round(time.time() - started, 1),
                            "state": state.to_dict(), **analysis(state.levels())})
            except Exception as exc:
                events.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            finally:
                events.put(None)

    # Sent before the worker starts, since model loading can delay later frames.
    yield _sse({"type": "accepted", "queued": _gpu.locked(),
                "loading": BACKEND == "model" and not (_hub and _hub.loaded)})
    threading.Thread(target=worker, daemon=True).start()
    while (event := events.get()) is not None:
        yield _sse(event)


def _lexicon_run(state: RunState, on_step, reviewed: bool) -> RunState:
    from agents import nodes
    from baselines.lexicon import lexicon_predict
    pipe = _lexicon_pipeline()
    if not reviewed:
        started = time.time()
        state.factors = lexicon_predict(state.description, NAMES)
        state.record("extract", True, started, backend="lexicon",
                     stated=sum(v["level"] != "not_stated" for v in state.factors.values()))
        on_step(state)
    nodes.clarify(state, None, pipe.onto, pipe.max_questions)
    on_step(state)
    nodes.recommend(state, pipe.min_stated)
    on_step(state)
    nodes.comply(state)
    on_step(state)
    nodes.assess(state)
    on_step(state)
    nodes.explain(state)
    on_step(state)
    return state


def _new_state(description: str) -> RunState:
    text = " ".join(description.split())
    if len(text) < 20:
        raise HTTPException(422, "describe the project in at least a sentence or two")
    return RunState(description=text, id=f"web-{int(time.time())}")


@app.post("/api/analyze")
def analyze(body: AnalyzeIn) -> StreamingResponse:
    state = _new_state(body.description)
    if BACKEND == "lexicon":
        job = lambda on_step: _lexicon_run(state, on_step, reviewed=False)
    else:
        def job(on_step):
            pipe = _get_pipeline()
            pipe.thorough_compliance = body.thorough
            pipe.write_plan = body.plan
            return pipe.run(state, ask=True, on_step=on_step)
    return StreamingResponse(_stream(job), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/replan")
def replan(body: ReplanIn) -> StreamingResponse:
    state = _new_state(body.description)
    state.factors = {f: {"level": _clean({f: (body.factors.get(f) or {}).get("level")})[f],
                         "evidence": (body.factors.get(f) or {}).get("evidence")} for f in NAMES}
    if BACKEND == "lexicon":
        job = lambda on_step: _lexicon_run(state, on_step, reviewed=True)
    else:
        def job(on_step):
            pipe = _get_pipeline()
            pipe.thorough_compliance = body.thorough
            pipe.write_plan = True
            return pipe.replan(state, on_step=on_step)
    return StreamingResponse(_stream(job), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
