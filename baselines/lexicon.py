"""Keyword-lexicon factor reader: a fast, model-free stand-in for the extractor (CPU-only server mode)."""
from __future__ import annotations

import re

_N_BIG = r"(?:2[6-9]|[3-9]\d|\d{3,})"
_N_MID = r"(?:[6-9]|1\d|2[0-5]|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)"
_N_SMALL = r"(?:[1-5]|one|two|three|four|five|a single)"
_PEOPLE = r"(?:people|engineers|developers|contributors|students|researchers|staff|maintainers|members of staff)"
_MANY = r"(?:9|1\d|[2-9]\d|nine|ten|eleven|twelve)"
_THINGS = r"(?:systems|feeds|sources|functions|models|tools|components|integrations|interfaces|subsystems)"

# Per factor: (level, cue patterns) in priority order; the first matching level wins.
LEXICON: dict[str, list[tuple[str, list[str]]]] = {
    "requirement_stability": [
        ("low", [r"still (being )?(decided|debated|undecided)", r"undecided", r"rethought", r"keeps? changing",
                 r"not (yet )?(agreed|settled|decided)", r"won't be settled", r"exploratory"]),
        ("medium", [r"core [\w -]+ (are|is) agreed", r"the rest aren't", r"\bof \d+ [\w -]+, \d+ are agreed"]),
        ("high", [r"signed off", r"sign-off", r"frozen", r"fixes exactly", r"fixed by (the )?(statute|law|contract)",
                  r"full (feature )?list was"]),
    ],
    "change_frequency": [
        ("high", [r"almost (weekly|daily|monthly)", r"every (week|day)", r"each week", r"constantly", r"continuously"]),
        ("low", [r"once a year", r"\byearly\b", r"rarely", r"hardly changed", r"only once", r"1 time a year"]),
        ("medium", [r"a few times a year", r"quarterly", r"twice a year", r"\d times a year"]),
    ],
    "continuous_delivery_need": [
        ("high", [r"within hours", r"same day", r"times a day", r"several times", r"on demand", r"\bdaily\b releases?"]),
        ("medium", [r"\bmonthly\b", r"every month", r"12 updates a year"]),
        ("low", [r"once a year", r"twice a year", r"one release", r"single release", r"at the end",
                 r"\d releases? a year", r"only at the"]),
    ],
    "regulatory_criticality": [
        ("low", [r"no regulator", r"not (subject|regulated)", r"exempt", r"0 regulator", r"no [\w ]*review of the"]),
        ("medium", [r"though (nothing|the [\w ]+|it) (is|isn't) (certified|not certified)", r"isn't certified",
                    r"nothing is certified", r"gdpr", r"data protection", r"may request"]),
        ("high", [r"audit", r"certif", r"regulator", r"inspect"]),
    ],
    "security_risk": [
        ("low", [r"non-sensitive", r"nothing sensitive", r"no personal", r"anonymi[sz]ed", r"only (public|order|room|"
                 r"test|unclassified|depot|farm|claim|totals)", r"0 personal"]),
        ("medium", [r"personal but not", r"not sensitive", r"names and", r"not (critical|classified)"]),
        ("high", [r"payment", r"credential", r"health", r"sensitive", r"attack", r"fraud", r"target", r"classified",
                  r"hacker", r"ransomware", r"leak"]),
    ],
    "failure_consequence": [
        ("low", [r"rerun", r"re-?enter", r"simply", r"just means", r"minor", r"try later", r"later\b"]),
        ("medium", [r"delay", r"complain", r"disruption", r"a day late"]),
        ("high", [r"safety", r"injur", r"harm", r"life", r"lives", r"death", r"million", r"billion", r"explosion",
                  r"hospital", r"patients?", r"black out", r"wildfire", r"penalt"]),
    ],
    "verification_rigor": [
        ("low", [r"own (tests|code|work|changes)", r"test their own", r"untested", r"ad[- ]hoc", r"developer testing",
                 r"that's our testing", r"0 independent"]),
        ("medium", [r"spot-?checks?", r"a sample of", r"\d+ of every \d+", r"second (engineer|analyst|producer|scientist)"]),
        ("high", [r"independent", r"traceab", r"every [\w -]+ is (independently )?(tested|validated|checked)",
                  r"v&v", r"validated against"]),
    ],
    "test_doc_rigor": [
        ("low", [r"readme", r"comments are the documentation", r"minimal documentation"]),
        ("medium", [r"short test report", r"user guide", r"admin guide", r"integration guide"]),
        ("high", [r"full test report", r"design document", r"manual"]),
    ],
    "complexity": [
        ("low", [r"one (form|screen|thing|login|model|engine|nightly job|chart)", r"\b1 (data source|form)",
                 r"single (form|screen)", r"\bone data feed"]),
        ("high", [rf"\b{_MANY} (linked )?{_THINGS}", r"many (components|integrations)"]),
        ("medium", [r"three (parts|steps|things)", r"\b3 parts", r"several components"]),
    ],
    "size": [
        ("high", [rf"\b{_N_BIG} {_PEOPLE}", rf"at least {_N_BIG}", rf"team of {_N_BIG}"]),
        ("low", [r"one-developer", rf"\b{_N_SMALL} {_PEOPLE}",
                 rf"\b{_N_SMALL} (developer|engineer|maintainer|student|researcher)s?\b"]),
        ("medium", [rf"\b{_N_MID} {_PEOPLE}", rf"team (is|of) {_N_MID}\b", rf"grew to {_N_MID}\b"]),
    ],
    "technical_novelty": [
        ("medium", [r"new to (us|our|the)", r"unfamiliar", r"1 is new"]),
        ("high", [r"nobody", r"never (run|used|been)", r"unproven", r"not live yet", r"isn't live"]),
        ("low", [r"standard", r"usual", r"same [\w -]+ (we|as)", r"reuses?"]),
    ],
    "legacy_dependence": [
        ("low", [r"nothing old", r"greenfield", r"fresh build", r"no older", r"0 older", r"retired", r"switched off",
                 r"shut down"]),
        ("medium", [r"\bhalf\b", r"some (members|of)", r"the rest use"]),
        ("high", [r"legacy", r"\b(19[6-9]\d|200\d|201[0-5])\b", r"mainframe", r"old (system|portal|gateway|format)"]),
    ],
    "stakeholder_availability": [
        ("high", [r"\bdaily\b", r"every day", r"5 days a week", r"embedded", r"sits with", r"works with (us|the team)"]),
        ("medium", [r"every two weeks", r"fortnight", r"bi-?weekly", r"2 times a month", r"\bweekly\b"]),
        ("low", [r"quarterly", r"annual", r"once a year", r"at acceptance", r"only (at|join)", r"1 review a year"]),
    ],
    "scope_rigidity": [
        ("medium", [r"budget is fixed but", r"(can|be) swapped", r"swap features", r"budget of hours"]),
        ("high", [r"fixed[- ]price", r"price and features", r"features are fixed", r"fixes price", r"\d+ price and \d+ features"]),
        ("low", [r"re-?plan", r"re-?scop", r"tranche", r"flexible"]),
    ],
}
_COMPILED = {f: [(lvl, [re.compile(p, re.IGNORECASE) for p in pats]) for lvl, pats in rules]
             for f, rules in LEXICON.items()}
_SENTENCES = re.compile(r"[^.!?\n]+[.!?]?")


def lexicon_predict(description: str, names: list[str]) -> dict:
    """{factor: {"level", "evidence"}}: first matching cue in priority order, evidence = its sentence."""
    sentences = [s.strip() for s in _SENTENCES.findall(description) if s.strip()]
    out = {}
    for f in names:
        out[f] = {"level": "not_stated", "evidence": None}
        for level, patterns in _COMPILED.get(f, []):
            hit = next((s for s in sentences for p in patterns if p.search(s)), None)
            if hit:
                out[f] = {"level": level, "evidence": hit}
                break
    return out

