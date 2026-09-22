"""Statement-span convention (contracts/spans.py) and the code-point offset rule. owner: B0."""

import json

import pytest

from noteguard.contracts.spans import statement_spans
from tests.support.golden import ENCOUNTERS

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]


def _quotes(text):
    return [text[a:b] for a, b in statement_spans(text)]


def test_statement_spans_convention():
    assert _quotes("1. Amlodipine 5 mg OD.\n2) Metformin 500 mg BD") == ["Amlodipine 5 mg OD", "Metformin 500 mg BD"]
    assert _quotes("Potassium 6.4 mmol/L. Sodium 138.") == ["Potassium 6.4 mmol/L", "Sodium 138"]
    assert _quotes("Allergies: nil?  Query ?penicillin.") == ["Allergies: nil?", "Query ?penicillin"]
    assert _quotes("A.\r\nB!") == ["A", "B"]
    assert _quotes("Repeat K sent; Dr Lim to review by 18:00.") == ["Repeat K sent; Dr Lim to review by 18:00"]


def test_offsets_are_code_points_not_utf16():
    """The 16:00 note puts Chinese, a POJ combining mark and an astral emoji before the evidence
    span, so JS (UTF-16) indices differ from the contract's code-point offsets (B3 converts)."""
    snap = json.loads((ENCOUNTERS / "ENC-A1.json").read_text(encoding="utf-8"))
    text = next(e["text"] for e in snap["extractions"] if "Discharge planning" in e["text"])
    start = text.index("Patient stable")
    assert (start, start + 14) in statement_spans(text)
    assert len(text[:start].encode("utf-16-le")) // 2 == start + 1  # one astral char before the span
    assert "\u030d" in text[:start] and "\u5973" in text[:start]
