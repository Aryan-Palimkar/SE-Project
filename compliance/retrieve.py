"""Find the standards that apply to a project description.

Modes:
  alias   regex triggers only (the text names the standard)
  tfidf   lexical similarity of each sentence to each standard's scope
  dense   embedding similarity (BAAI/bge-small-en-v1.5)
  hybrid  alias, plus dense for standards the text does not name
"""
from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
KB_PATH = ROOT / "ontology" / "standards.yaml"
CONFIG_PATH = ROOT / "ontology" / "retrieval.yaml"
MODES = ("alias", "tfidf", "dense", "hybrid")
EMBEDDER = "BAAI/bge-small-en-v1.5"
_QUERY = "Represent this sentence for searching relevant passages: "     # bge's query instruction
_SENT = re.compile(r"[^.;!?]+[.;!?]?")


@dataclass
class Hit:
    standard: str
    name: str
    how: str            # "named" | "inferred"
    evidence: str       # the matching span or sentence
    score: float        # 1.0 for a named hit, similarity otherwise

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def load_kb(path: str = str(KB_PATH)) -> dict:
    with open(path, encoding="utf-8") as f:
        kb = yaml.safe_load(f)
    for s in kb["standards"]:
        s["_triggers"] = [re.compile(t, re.IGNORECASE) for t in s.get("triggers", [])]
        s["_all"] = [re.compile(t, re.IGNORECASE) for t in s.get("triggers_all", [])]
        s["_where"] = re.compile(s["jurisdiction"], re.IGNORECASE) if s.get("jurisdiction") else None
    return kb


def load_config(path: Path = CONFIG_PATH) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"mode": "alias"}


def sentences(text: str) -> list[str]:
    out = [s.strip() for s in _SENT.findall(" ".join(text.split())) if len(s.strip()) > 3]
    return out or [text]


_init_lock = threading.Lock()
_models: dict = {}


def _embedder():
    with _init_lock:
        if "embedder" not in _models:
            from sentence_transformers import SentenceTransformer
            _models["embedder"] = SentenceTransformer(EMBEDDER, device="cpu")
        return _models["embedder"]


def _scope_vectors() -> np.ndarray:
    if "scopes" not in _models:
        vecs = _embedder().encode([s["scope"] for s in load_kb()["standards"]], normalize_embeddings=True)
        with _init_lock:
            _models.setdefault("scopes", vecs)
    return _models["scopes"]


@lru_cache(maxsize=1)
def _tfidf():
    from sklearn.feature_extraction.text import TfidfVectorizer
    kb = load_kb()
    docs = [f"{s['name']} {s['scope']}" for s in kb["standards"]]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit(docs)
    return vec, vec.transform(docs)


def similarities(text: str, method: str) -> tuple[list[str], np.ndarray]:
    """(sentences, matrix [n_sentences, n_standards]) of similarity to each standard's scope."""
    sents = sentences(text)
    if method == "dense":
        q = _embedder().encode([_QUERY + s for s in sents], normalize_embeddings=True)
        return sents, q @ _scope_vectors().T
    if method == "tfidf":
        vec, docs = _tfidf()
        return sents, (vec.transform(sents) @ docs.T).toarray()
    raise ValueError(method)


def named(text: str) -> list[Hit]:
    """Standards the text names: any pattern in `triggers` matches, or every pattern in `triggers_all`."""
    hits = []
    for s in load_kb()["standards"]:
        m = next((m for p in s["_triggers"] if (m := p.search(text))), None)
        if m:
            hits.append(Hit(s["id"], s["name"], "named", m.group(0), 1.0))
            continue
        if s["_all"]:
            matches = [p.search(text) for p in s["_all"]]
            if all(matches):
                hits.append(Hit(s["id"], s["name"], "named", " + ".join(m.group(0) for m in matches), 1.0))
    return hits


def inferred(text: str, method: str, threshold: float, exclude: set[str] = frozenset(),
             relative: bool = False, cap: int | None = None) -> list[Hit]:
    """Standards whose scope matches some sentence of `text`.

    A standard with a `jurisdiction` pattern is only inferred when the text matches it, so a national
    regulation is not suggested for a project in another country.
    relative: score is best-sentence similarity minus the median over all standards.
    cap: at most this many inferred standards per description.
    """
    kb = load_kb()["standards"]
    sents, sim = similarities(text, method)
    best = sim.max(axis=0)
    base = float(np.median(best)) if relative else 0.0
    hits = []
    for j, s in enumerate(kb):
        if s["id"] in exclude or (s["_where"] and not s["_where"].search(text)):
            continue
        i = int(np.argmax(sim[:, j]))
        if best[j] - base >= threshold:
            hits.append(Hit(s["id"], s["name"], "inferred", sents[i], round(float(best[j] - base), 4)))
    hits.sort(key=lambda h: -h.score)
    return hits[:cap] if cap else hits


def retrieve(text: str, mode: str | None = None, threshold: float | None = None) -> list[Hit]:
    """Standards that apply to `text` under `mode`, using retrieval.yaml unless a threshold is given."""
    cfg = load_config()
    mode = mode or cfg.get("mode", "alias")
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if mode == "alias":
        return named(text)
    method = "dense" if mode in ("dense", "hybrid") else "tfidf"
    relative = cfg.get("scoring") == "relative"
    key = f"{method}_relative" if relative else method
    thr = threshold if threshold is not None else cfg.get("thresholds", {}).get(key)
    if thr is None:
        raise ValueError(f"no threshold for {key}: run python -m eval.compliance_eval first")
    cap = cfg.get("cap") if relative else None
    if mode == "hybrid":
        base = named(text)
        return base + inferred(text, method, thr, exclude={h.standard for h in base}, relative=relative, cap=cap)
    return inferred(text, method, thr, relative=relative, cap=cap)


def obligations(standard_ids: list[str]) -> list[dict]:
    """Obligations of the given standards in the plan checker's element format."""
    by_id = {s["id"]: s for s in load_kb()["standards"]}
    out = []
    for sid in standard_ids:
        s = by_id[sid]
        for o in s["obligations"]:
            out.append({"id": o["id"], "standard": sid, "standard_name": s["name"], "ref": o["ref"],
                        "phase": o["phase"], "description": o["text"], "keywords": o["keywords"],
                        "document": s.get("document")})
    return out
