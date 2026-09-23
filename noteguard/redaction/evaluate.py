"""Redaction accuracy on the labelled set, measured BOTH ways: identifiers left unredacted and
over-redacted clinical strings (Section 10.4). Counts only; no text is printed or logged."""

from __future__ import annotations

import json
from pathlib import Path

from .redact import DeterministicRedactor

EVAL_SET = Path(__file__).resolve().parent / "eval_set" / "labelled_v1.json"


def evaluate(path: Path = EVAL_SET) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    red = DeterministicRedactor(data["roster"])
    out = dict(items=0, identifiers=0, not_redacted=0, keep=0, over_redacted=0, egress_refused=0)
    for item in data["items"]:
        report = red.redact(item["text"])
        out["items"] += 1
        out["identifiers"] += len(item["identifiers"])
        out["not_redacted"] += sum(1 for s in item["identifiers"] if s in report.redacted_text)
        out["keep"] += len(item["keep"])
        out["over_redacted"] += sum(1 for s in item["keep"] if s not in report.redacted_text)
        out["egress_refused"] += 0 if report.remote_egress_allowed else 1
    return out
