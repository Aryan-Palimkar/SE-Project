"""Search the passage index built by knowledge.build."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from knowledge.build import load_sources

HERE = Path(__file__).resolve().parent
MIN_SCORE = 0.62


@lru_cache(maxsize=1)
def load() -> tuple[list[dict], np.ndarray]:
    path, vectors = HERE / "passages.jsonl", HERE / "vectors.npy"
    if not path.exists() or not vectors.exists():
        return [], np.zeros((0, 384), dtype=np.float32)
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows, np.load(vectors)


@lru_cache(maxsize=1)
def sources() -> dict[str, dict]:
    return {s["id"]: s for s in load_sources()}


def documents_for(standard_ids) -> set[str]:
    """Indexed documents that belong to the given standards."""
    wanted = set(standard_ids)
    rows, _ = load()
    indexed = {r["source"] for r in rows}
    return {sid for sid, s in sources().items() if s.get("standard") in wanted and sid in indexed}


def search(queries: list[str], documents: set[str] | None = None, k: int = 6,
           min_score: float = MIN_SCORE) -> list[dict]:
    """The k passages most similar to any of the queries, restricted to `documents`.
    Each result carries the document title, page and similarity."""
    rows, vectors = load()
    queries = [q for q in queries if q and q.strip()]
    if not rows or not queries or documents == set():
        return []
    from compliance.retrieve import _QUERY, _embedder
    q = _embedder().encode([_QUERY + text for text in queries], normalize_embeddings=True)
    scores = (q @ vectors.T).max(axis=0)
    out = []
    for i in np.argsort(-scores):
        if scores[i] < min_score or len(out) >= k:
            break
        row = rows[i]
        if documents is None or row["source"] in documents:
            out.append({**row, "score": round(float(scores[i]), 4), "title": sources()[row["source"]]["title"]})
    return out


def best_passage(text: str, document: str) -> dict | None:
    """The single passage of `document` closest to `text`, if any is similar enough."""
    hits = search([text], {document}, k=1)
    return hits[0] if hits else None
