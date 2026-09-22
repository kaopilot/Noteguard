"""Shared-definition seam test (Section 18.4 rule 4, L5 across builders). owner: B0.

Fails if any product module outside noteguard/contracts/ defines its own Enum, or a literal
collection holding two or more values of one contract vocabulary (roles, reason codes, flag
states, bubble statuses, decision actions, extraction statuses, disciplines, rule ids, log
keys, registry terms). Generated TypeScript (*.gen.ts) is exempt."""

from __future__ import annotations

import ast
import json
import re

import pytest

from noteguard.contracts.log_allowlist import LOG_KEYS
from noteguard.contracts.types import (
    BubbleStatus,
    DecisionAction,
    Discipline,
    ExtractionStatus,
    FlagCategory,
    FlagState,
    ReasonCode,
    Role,
    RuleId,
)
from tests.support.golden import ROOT

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]
ENUM_BASES = {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}


def _registry_terms() -> set[str]:
    reg = json.loads((ROOT / "rulesets" / "registry_v1.json").read_text(encoding="utf-8"))
    out = {s for t in reg["terms"] for s in t["synonyms"]} | {t["key"] for t in reg["terms"]}
    out |= {d["phrase"] for d in reg["allergy_denials"]} | {f["phrase"] for f in reg["frequencies"]}
    out |= {c for cues in reg["cues"].values() for c in cues if len(c) >= 4}
    return out


VOCAB: dict[str, set[str]] = {
    "role": {x.value for x in Role}, "reason_code": {x.value for x in ReasonCode},
    "flag_state": {x.value for x in FlagState}, "bubble_status": {x.value for x in BubbleStatus},
    "decision_action": {x.value for x in DecisionAction}, "extraction_status": {x.value for x in ExtractionStatus},
    "discipline": {x.value for x in Discipline}, "rule_id": {x.value for x in RuleId},
    "flag_category": {x.value for x in FlagCategory}, "log_key": set(LOG_KEYS), "registry_term": _registry_terms(),
}


def _hits(values: list[str]) -> list[str]:
    return [cat for cat, vocab in VOCAB.items() if sum(1 for v in set(values) if v in vocab) >= 2]


def python_violations(source: str, filename: str) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(source, filename)):
        if isinstance(node, ast.ClassDef):
            bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
            if bases & ENUM_BASES:
                out.append(f"{filename}:{node.lineno} defines Enum {node.name}")
        elts = None
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elts = node.elts
        elif isinstance(node, ast.Dict):
            elts = [k for k in node.keys if k is not None]
        if elts:
            strs = [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            for cat in _hits(strs):
                out.append(f"{filename}:{node.lineno} literal collection duplicates contract vocabulary '{cat}'")
    return out


_TS_STR = re.compile(r"""(["'`])((?:(?!\1).){1,80})\1""")


def ts_violations(source: str, filename: str) -> list[str]:
    out = []
    for n, line in enumerate(source.splitlines(), 1):
        for cat in _hits([m.group(2) for m in _TS_STR.finditer(line)]):
            out.append(f"{filename}:{n} duplicates contract vocabulary '{cat}' (import the generated types)")
    return out


def test_no_duplicate_definitions_outside_contracts():
    """Mutation: add `ROLES = ["clinician", "nurse"]` to any engine or API module -> fails."""
    bad = []
    for p in (ROOT / "noteguard").rglob("*.py"):
        if "contracts" in p.relative_to(ROOT / "noteguard").parts:
            continue
        bad += python_violations(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT)))
    src = ROOT / "frontend" / "src"
    if src.is_dir():
        for p in src.rglob("*"):
            if p.suffix in {".ts", ".tsx", ".js", ".jsx"} and not p.name.endswith(".gen.ts"):
                bad += ts_violations(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT)))
    assert not bad, "\n".join(bad)


def test_seam_scanner_detects_violations():
    """Self-test: the scanner itself must catch each kind of duplication."""
    assert python_violations("from enum import Enum\nclass S(Enum):\n    A = 1\n", "x.py")
    assert python_violations('ROLES = ["clinician", "nurse"]\n', "x.py")
    assert python_violations('CODES = {"extraction_error", "wrong_encounter"}\n', "x.py")
    assert python_violations('LOG = {"route_template": 1, "flag_id": 2}\n', "x.py")
    assert python_violations('CUES = ("awaiting", "pending")\n', "x.py")
    assert ts_violations("type S = 'open' | 'accepted';", "x.ts")
    assert not python_violations('x = ["a", "clinician"]\n', "x.py")
