"""Orchestrator: a fixed state machine over the agent nodes.

  clarify? -> extract -> [answers] -> rubric -> plan -> check -> repair* -> explain
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agents import nodes, requirements
from agents.runtime import AdapterSpec, ModelHub
from agents.state import RunState
from core.backends import Backend
from core.config import load_factor_ontology


@dataclass
class Pipeline:
    """Backends per stage; each can be a different model."""
    extractor: Backend
    planner: Backend
    assistant: Backend | None = None
    challenger: Backend | None = None         # None = off
    requirements_agent: Backend | None = None  # None = off
    rag_requirements: bool = True      # second pass maps retrieved obligations onto the requirements
    ask_requirements: bool = True      # multiple-choice questions for unclear requirements
    reconcile: bool = False            # stated requirements help fill unstated factors
    reconcile_strict: bool = False
    max_questions: int = 4
    max_repairs: int = 2
    repair_scope: str = "invalid"
    min_stated: int = 3
    rag_plan: bool = True              # retrieved obligations in the plan prompt
    thorough_compliance: bool = False  # also repair uncovered obligations (slower)
    write_plan: bool = True            # False stops after the recommendation
    extract_definitions: bool = False  # level descriptors in the extraction prompt (API or zero-shot models)
    onto: dict = field(default_factory=load_factor_ontology)

    def run(self, state: RunState, answers: dict | None = None, ask: bool = True,
            on_step=None) -> RunState:
        """`on_step(state)` is called after every node, for streaming progress."""
        step = on_step or (lambda _state: None)
        nodes.comply(state)
        step(state)
        if self.requirements_agent is not None:
            requirements.identify(state, self.requirements_agent)
            step(state)
            if self.rag_requirements:
                requirements.regulate(state, self.requirements_agent)
                step(state)
            if ask and self.ask_requirements:
                requirements.ask(state, self.requirements_agent)
                step(state)
        nodes.extract(state, self.extractor, self.onto, self.extract_definitions)
        step(state)
        if self.challenger is not None:
            nodes.challenge(state, self.challenger, self.onto)
            step(state)
        if self.reconcile and self.requirements_agent is not None and state.requirements:
            requirements.reconcile(state, self.requirements_agent, self.onto, self.reconcile_strict)
            step(state)
        if ask:
            nodes.clarify(state, self.assistant, self.onto, self.max_questions)
            step(state)
        if answers:
            state.answers = {**(state.answers or {}), **answers}
            nodes.apply_answers(state, self.assistant or self.planner, self.onto)
            step(state)
            if ask:
                nodes.clarify(state, self.assistant, self.onto, self.max_questions)
                step(state)
        nodes.recommend(state, self.min_stated)
        step(state)
        return self._after_rubric(state, step)

    def replan(self, state: RunState, on_step=None) -> RunState:
        """Everything after extraction, on factors a person has reviewed or edited."""
        step = on_step or (lambda _state: None)
        nodes.clarify(state, self.assistant, self.onto, self.max_questions)
        step(state)
        nodes.recommend(state, self.min_stated)
        step(state)
        nodes.comply(state)
        step(state)
        return self._after_rubric(state, step)

    def _after_rubric(self, state: RunState, step) -> RunState:
        if state.insufficient_evidence or not self.write_plan:
            nodes.assess(state)
            step(state)
            nodes.explain(state)
            step(state)
            return state
        nodes.plan(state, self.planner, self.onto, rag=self.rag_plan)
        step(state)
        nodes.check(state)
        step(state)
        if self.max_repairs:
            nodes.repair(state, self.planner, self.onto, self.max_repairs, self.repair_scope,
                         obligations=self.thorough_compliance)
            step(state)
        nodes.assess(state)
        step(state)
        nodes.explain(state)
        step(state)
        return state


def local_pipeline(model_id: str, extract_adapter: str, plan_adapter: str | None, load_in_4bit: bool = True,
                   max_questions: int = 4, max_repairs: int = 2, repair_scope: str = "invalid",
                   constrained_extract: bool = True, min_stated: int = 3,
                   challenge: bool = False, identify_requirements: bool = True) -> tuple[Pipeline, ModelHub]:
    """Both stages on one lazily loaded base model. `plan_adapter=None` plans zero-shot."""
    if plan_adapter:
        plan_spec = AdapterSpec("plan", plan_adapter, max_new_tokens=2048, task="plan")
    else:
        plan_spec = AdapterSpec("plan", None, max_new_tokens=4096, task=None)
    hub = ModelHub(model_id, {
        "extract": AdapterSpec("extract", extract_adapter, max_new_tokens=768,
                               task="extract" if constrained_extract else None),
        "plan": plan_spec,
    }, load_in_4bit=load_in_4bit)
    pipeline = Pipeline(extractor=hub.backend("extract"), planner=hub.backend("plan"),
                        assistant=hub.backend(None, max_new_tokens=8), max_questions=max_questions,
                        max_repairs=max_repairs, repair_scope=repair_scope, min_stated=min_stated,
                        challenger=hub.backend(None, max_new_tokens=1024) if challenge else None,
                        requirements_agent=hub.backend(None, max_new_tokens=2048) if identify_requirements else None)
    return pipeline, hub


API_STAGES = ("requirements", "extract", "plan")


def use_api(pipeline: Pipeline, model: str, stages=API_STAGES) -> Pipeline:
    """Run the given stages on a Gemini model instead of the local one. Stages left local still
    load the local model lazily; if none are left, it is never loaded."""
    from core.backends import gemini_backend
    unknown = set(stages) - set(API_STAGES)
    if unknown:
        raise ValueError(f"unknown API stages: {sorted(unknown)}")
    backend = gemini_backend(model)
    if "requirements" in stages:
        pipeline.requirements_agent = backend
    if "extract" in stages:
        pipeline.extractor, pipeline.assistant, pipeline.extract_definitions = backend, backend, True
    if "plan" in stages:
        pipeline.planner = backend
    return pipeline
