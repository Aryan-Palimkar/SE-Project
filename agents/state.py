"""Run state passed between agent nodes, and the run log."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Step:
    node: str
    ok: bool
    seconds: float
    detail: dict = field(default_factory=dict)


@dataclass
class RunState:
    description: str
    id: str = "run"
    requirements: list = field(default_factory=list)
    clauses: list = field(default_factory=list)        # passages retrieved from official documents
    requirement_questions: list = field(default_factory=list)
    srs: dict | None = None
    factors: dict = field(default_factory=dict)        # {factor: {"level", "evidence"}}
    questions: list = field(default_factory=list)
    answers: dict = field(default_factory=dict)        # factor -> answer text
    recommendation: dict | None = None
    plan: dict | None = None
    justification: str | None = None
    report: dict | None = None                         # plan checker output
    repairs: int = 0
    insufficient_evidence: bool = False
    compliance: dict | None = None
    risks: list = field(default_factory=list)
    summary: str = ""
    log: list = field(default_factory=list)

    def levels(self) -> dict:
        return {f: v["level"] for f, v in self.factors.items()}

    def record(self, node: str, ok: bool, started: float, **detail) -> None:
        self.log.append(Step(node=node, ok=ok, seconds=round(time.time() - started, 2), detail=detail))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["log"] = [asdict(s) if isinstance(s, Step) else s for s in self.log]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        state.log = [Step(**s) if isinstance(s, dict) else s for s in state.log]
        return state

    @classmethod
    def load(cls, path) -> "RunState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path
