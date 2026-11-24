"""Build the passage index from the official PDFs listed in knowledge/sources.yaml.

  python -m knowledge.build --pdf-dir path/to/pdfs

Writes knowledge/passages.jsonl (one passage per line, with its page) and knowledge/vectors.npy
(normalised bge-small embeddings, one row per passage). Sources whose PDF is missing are skipped.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
EMBEDDER = "BAAI/bge-small-en-v1.5"
TARGET_WORDS, MAX_WORDS = 140, 220

_NOISE = re.compile(r"^(page \d+ of \d+|\d+|the gazette of india.*|\[part ii.*|.*extraordinary.*|withdrawn)$", re.I)


def load_sources() -> list[dict]:
    return yaml.safe_load((HERE / "sources.yaml").read_text(encoding="utf-8"))["sources"]


def english_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(c.isascii() for c in letters) / max(len(letters), 1)


def page_paragraphs(text: str) -> list[str]:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line and not _NOISE.match(line) and english_share(line) >= 0.5]
    paragraphs, current = [], []
    for line in lines:
        # a numbered clause, a lettered item or a heading starts a new paragraph
        if current and re.match(r"^(\(?[0-9ivx]+[.)]|\([a-z]\)|chapter|rule|section|annex)", line, re.I):
            paragraphs.append(" ".join(current))
            current = []
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def chunk(paragraphs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Merge consecutive paragraphs into passages of about TARGET_WORDS words; long ones are split."""
    out, words, page = [], [], None
    for pg, para in paragraphs:
        tokens = para.split()
        while len(tokens) > MAX_WORDS:
            if words:
                out.append((page, " ".join(words)))
                words = []
            out.append((pg, " ".join(tokens[:TARGET_WORDS])))
            tokens = tokens[TARGET_WORDS:]
        if words and len(words) + len(tokens) > MAX_WORDS:
            out.append((page, " ".join(words)))
            words = []
        if not words:
            page = pg
        words += tokens
        if len(words) >= TARGET_WORDS:
            out.append((page, " ".join(words)))
            words = []
    if words:
        out.append((page, " ".join(words)))
    return [(pg, text) for pg, text in out if len(text.split()) >= 12]


def extract(pdf: Path) -> list[tuple[int, str]]:
    import fitz

    paragraphs = []
    with fitz.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            text = page.get_text()
            if english_share(text) < 0.8:
                continue
            paragraphs += [(number, p) for p in page_paragraphs(text)]
    return chunk(paragraphs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf-dir", required=True)
    args = parser.parse_args()

    rows = []
    for source in load_sources():
        pdf = Path(args.pdf_dir) / source["file"]
        if not pdf.exists() or pdf.read_bytes()[:5] != b"%PDF-":
            print(f"skipped {source['id']}: no PDF at {pdf}")
            continue
        passages = extract(pdf)
        rows += [{"id": f"{source['id']}#{i + 1}", "source": source["id"], "page": page, "text": text}
                 for i, (page, text) in enumerate(passages)]
        print(f"{source['id']}: {len(passages)} passages")

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDER, device="cpu")
    vectors = model.encode([r["text"] for r in rows], normalize_embeddings=True, batch_size=32,
                           show_progress_bar=False).astype(np.float32)
    with open(HERE / "passages.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    np.save(HERE / "vectors.npy", vectors)
    print(f"{len(rows)} passages indexed")


if __name__ == "__main__":
    main()
