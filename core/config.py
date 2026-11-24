"""Project paths and the factor ontology."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FACTORS_PATH = ROOT / "ontology" / "factors.yaml"


def load_factor_ontology(path: Path | str = FACTORS_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
