"""The ONLY place identifiers and version strings are computed (Section 18.3)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def new_id() -> str:
    """Opaque random identifier (UUIDv4 string)."""
    return str(uuid.uuid4())


def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace, UTF-8 (not ASCII-escaped)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _stable(prefix: str, parts: list[str]) -> str:
    return prefix + sha256_hex(canonical_json(parts))[:24]


def flag_id(rule_id: str, encounter_id: str, normalized_subject_key: str) -> str:
    """Stable flag identity (Section 8.4). Rule version and evidence are NOT part of it."""
    return _stable("flg_", [str(rule_id), encounter_id, normalized_subject_key])


def bubble_id(question_template_id: str, encounter_id: str, subject_key: str) -> str:
    return _stable("bbl_", [question_template_id, encounter_id, subject_key])


def quote_sha256(quote: str) -> str:
    return sha256_hex(quote)


def check_version(ruleset_version: str, rule_id: str, rule_version: int, registry_version: str) -> str:
    """e.g. 'ruleset@v1;rule@CRIT-001.1;registry@v1'."""
    return f"ruleset@{ruleset_version};rule@{rule_id}.{rule_version};registry@{registry_version}"


def idempotency_key(namespace: str, external_id: str, version: int, sha256: str) -> str:
    return f"{namespace}|{external_id}|{version}|{sha256}"


def source_set_hash(version_sha256s: list[str]) -> str:
    """Hash over the sorted sha256 values of the in-scope source versions."""
    return sha256_hex(canonical_json(sorted(version_sha256s)))


GENESIS_AUDIT_HASH = "0" * 64


def audit_event_hash(prev_event_hash: str, event_fields: dict[str, Any]) -> str:
    """Hash chain link: sha256(prev_hash + canonical(allowlisted fields without event_hash))."""
    return sha256_hex(prev_event_hash + canonical_json(event_fields))
