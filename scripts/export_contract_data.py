"""Export contract DATA the UI needs but OpenAPI cannot express (B0; rerun via `make types`).

Route templates, header names, error-code → HTTP status, decision rules (reason codes per
action and per rule, transitions, required fields) and the permission matrix. B3 uses these
to label, order and HIDE controls only; the server stays the authority (Section 18.4 rule 4).
Output: docs/contract_data.json (deterministic, sorted keys).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from noteguard.contracts import permissions as P  # noqa: E402
from noteguard.contracts import routes as R  # noqa: E402
from noteguard.contracts import states as S  # noqa: E402
from noteguard.contracts.errors import HTTP_STATUS  # noqa: E402
from noteguard.contracts.types import CONTRACT_VERSION, HUMAN_REVIEW_STATEMENT  # noqa: E402


def plain(x):
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, (set, frozenset)):
        return sorted((plain(v) for v in x), key=str)
    if isinstance(x, (list, tuple)) and not hasattr(x, "_asdict"):
        return [plain(v) for v in x]
    if isinstance(x, dict):
        return {str(plain(k)): plain(v) for k, v in x.items()}
    if dataclasses.is_dataclass(x):
        return {f.name: plain(getattr(x, f.name)) for f in dataclasses.fields(x)}
    if hasattr(x, "_asdict"):
        return {k: plain(v) for k, v in x._asdict().items()}
    return x


def contract_data() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "routes": {k: v for k, v in sorted(vars(R).items()) if k.isupper() and v in R.ROUTE_TEMPLATES},
        "workspace_header": R.WORKSPACE_HEADER,
        "session_cookie": R.SESSION_COOKIE,
        "stub_header": R.STUB_HEADER,
        "error_http_status": plain(HTTP_STATUS),
        "human_review_statement": HUMAN_REVIEW_STATEMENT,
        "decisions": {
            "max_flags_per_decision": P.MAX_FLAGS_PER_DECISION,
            "transitions": plain(S.DECISION_TRANSITIONS),
            "reason_required": plain(S.REASON_REQUIRED),
            "rationale_required": plain(S.RATIONALE_REQUIRED),
            "reasons_by_action": plain(P.REASONS_BY_ACTION),
            "resolve_reasons_by_rule": plain(P.RESOLVE_REASONS_BY_RULE),
            "adjudication_reasons": plain(P.ADJUDICATION_REASONS),
            "reassign_target_roles": plain(P.REASSIGN_TARGET_ROLES),
        },
        "permissions": plain(P.PERMISSION_RULES),
    }


def main() -> None:
    out = ROOT / "docs" / "contract_data.json"
    out.write_text(json.dumps(contract_data(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
