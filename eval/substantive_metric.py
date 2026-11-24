"""Substantive coverage: was an obligation planned for, or only restated?

An obligation counts as covered when a mention passes all three checks:
  1. not a restatement of the standard (unless it names a concrete artefact)
  2. an actionable field (activities, deliverables, testing, security)
  3. the right stage, or an adjacent one (ongoing duties are exempt)
"""
from __future__ import annotations

import re

from eval.plan_checker import _loose

ACTIONABLE = {"activities", "deliverables", "testing", "security_activities"}
CRITERIA = {"compliance_checkpoints", "entry_criteria", "exit_criteria", "approval_gate"}
STAGES = ("planning", "requirements", "design", "implementation", "verification", "release", "operations")

# keywords that name a concrete artefact or activity
_CONCRETE = re.compile(r"assessment|statement|audit|test|model|plan\b|matrix|report|file|review|analysis|"
                       r"sbom|bill of materials|safety class|specification|\bsrs\b|log\b|register|dpia|scan")
# a line that cites a standard or clause
_CITATION = re.compile(r"service standard|point\s*\d|\bart\.?\s*\d|gdpr|wcag|iec\s*\d|iso\s*\d|\bfda\b|"
                       r"\b\d{3}\.\d|pci|hipaa|do-?178|:\s*\d+(\.\d+)?\s*-")
_WORD = re.compile(r"[a-z]{4,}")
_STOP = {"with", "that", "this", "from", "their", "each", "every", "where", "when", "into", "them", "have",
         "keep", "make", "users", "user", "service", "services", "before", "after", "including", "included"}

# phase-name cues -> stage; a phase can carry several ("Development and Verification")
_STAGE_CUES = [
    ("planning", r"\bplans?\b|planning|initiat|inception|objective|concept|sprint 0|discovery|kick"),
    ("requirements", r"requirement|analysis|research|discovery|user need"),
    ("design", r"design|architect|prototyp"),
    ("implementation", r"implement|develop|build|code|construct|sprint|iteration|increment"),
    ("verification", r"test|verif|validat|\bqa\b|acceptance|integration"),
    ("release", r"release|deploy|transition|launch|go-live|go live|rollout|cutover|acceptance"),
    ("operations", r"operat|maintain|maintenance|monitor|support|feedback|live\b|run\b"),
]
# obligations that apply across the whole life cycle
_ANYWHERE = {"govuk-1", "govuk-8", "govuk-9", "gdpr-32", "iso27001-8.25", "soc2-cc6", "hipaa-312a"}
# ongoing duties are met wherever the plan maintains the artefact
_ONGOING = re.compile(r"^(keep|maintain)\b|keep them traceable|throughout")
_ARTEFACT = re.compile(r"document|report|matrix|\bplan\b|\bfile\b|statement|\blog\b|register|specification|"
                       r"assessment|\bmodel\b|audit|sbom|dpia")


def stages_of(phase_name: str) -> set[str]:
    name = phase_name.lower()
    return {stage for stage, cue in _STAGE_CUES if re.search(cue, name)}


def _content(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def restated(item: str, obligation: dict) -> bool:
    """Cites a standard and mostly repeats the obligation's own words (or is little more than a citation)."""
    if not _CITATION.search(item.lower()):
        return False
    words, ob = _content(item), _content(obligation["description"])
    overlap = len(words & ob) / max(len(words), 1)
    return overlap >= 0.5 or len(words) <= 4


def location_counts(loc: dict, obligation: dict) -> bool:
    item, field = loc["item"], loc["field"]
    concrete = bool(_CONCRETE.search(_loose(loc["keyword"])))
    if restated(item, obligation) and not concrete:
        return False
    names_artefact = concrete or bool(_ARTEFACT.search(item.lower()))
    if field not in ACTIONABLE and not (field in CRITERIA and names_artefact):
        return False
    if obligation["id"] in _ANYWHERE or _ONGOING.search(obligation["description"].lower()):
        return True
    phase_stages = stages_of(loc["phase"])
    if not phase_stages:
        return True
    want = STAGES.index(obligation["phase"])
    return any(abs(STAGES.index(s) - want) <= 1 for s in phase_stages)


def substantively_covered(obligation: dict, locations: list[dict]) -> bool:
    return any(location_counts(loc, obligation) for loc in locations)

