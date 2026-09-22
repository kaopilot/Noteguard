"""Forbidden-phrase lint (Section 8.8, 13, 17). owner: B0 (B3 keeps UI strings passing).
Scans backend string literals (not docstrings), rulesets, golden human-facing text and
frontend source strings. 'Not documented in the supplied sources' is allowed."""

from __future__ import annotations

import ast
import json
import re

import pytest

from noteguard.contracts.forbidden_phrases import ABSENCE_EVENT_PHRASES, VERDICT_TONE_PHRASES, find_forbidden
from tests.support.golden import ROOT

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]
GOLDEN_TEXT_KEYS = {"reason", "question", "uncertainty_note", "text", "title", "why", "human_review_statement",
                    "must_not_suppress_note"}


def _python_strings(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                doc_ids.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            yield node.lineno, node.value


def _json_strings(obj, keys=None, key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _json_strings(v, keys, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _json_strings(v, keys, key)
    elif isinstance(obj, str) and (keys is None or key in keys):
        yield obj


def test_forbidden_phrase_lint():
    """Mutation: put 'was not done' in a rule reason template or a UI string -> fails."""
    bad = []
    for p in (ROOT / "noteguard").rglob("*.py"):
        if p.name == "forbidden_phrases.py":
            continue
        for line, s in _python_strings(p):
            if (hit := find_forbidden(s)):
                bad.append(f"{p.relative_to(ROOT)}:{line} {hit!r}")
    for p in (ROOT / "rulesets").glob("*.json"):
        for s in _json_strings(json.loads(p.read_text(encoding="utf-8"))):
            if (hit := find_forbidden(s)):
                bad.append(f"{p.relative_to(ROOT)} {hit!r} in {s[:60]!r}")
    for p in (ROOT / "fixtures" / "expected").glob("*.json"):
        for s in _json_strings(json.loads(p.read_text(encoding="utf-8")), GOLDEN_TEXT_KEYS):
            if (hit := find_forbidden(s)):
                bad.append(f"{p.relative_to(ROOT)} {hit!r} in {s[:60]!r}")
    for sub in ("src", "public"):
        d = ROOT / "frontend" / sub
        if d.is_dir():
            for p in d.rglob("*"):
                if (p.suffix in {".ts", ".tsx", ".js", ".jsx", ".html", ".json"} and ".test." not in p.name
                        and not p.name.endswith(".gen.ts")):  # generated from linted backend sources
                    for m in re.finditer(r"""(["'`])((?:(?!\1).)+)\1""", p.read_text(encoding="utf-8")):
                        if (hit := find_forbidden(m.group(2))):
                            bad.append(f"{p.relative_to(ROOT)} {hit!r}")
    assert not bad, "\n".join(bad)


def test_lint_detects_every_phrase_and_allows_scoped_absence():
    for p in ABSENCE_EVENT_PHRASES + VERDICT_TONE_PHRASES:
        assert find_forbidden(f"The ECG {p} today.") == p or find_forbidden(f"The ECG {p} today.")
    assert find_forbidden("DID  NOT\nHAPPEN") == "did not happen"
    assert find_forbidden("Not documented in the supplied sources.") is None
    assert find_forbidden("Dismissed as duplicate") is None  # 'missed' only as a whole word
