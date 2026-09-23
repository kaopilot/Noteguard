"""Ruleset pinning and the approval check at load (B4; Section 11 step 5, L13).

The runtime reads ONLY a pinned ruleset whose approval record (``rulesets/APPROVAL_<v>.md``) is
``approved``, names the evaluation report it was approved on, and whose file hashes equal the bytes
on disk. Rollback = re-pin the previous approved version. Nothing here writes a ruleset.

Every call re-reads and re-verifies the files. The bundle is not cached: ``TermRegistry.cues`` and
``dose_unit_canonical`` are dicts inside frozen models, so an object handed out could be edited in
place; re-verifying per call means such an edit can never reach the next check run.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from noteguard.contracts import ids
from noteguard.contracts.types import ApprovalRecord, Ruleset, RulesetBundle, RulesetStatus, TermRegistry

ROOT = Path(__file__).resolve().parents[2]
RULESETS_DIR = ROOT / "rulesets"
#: The pinned ruleset version. Changing it is a release (or a rollback), never a runtime event.
PINNED_VERSION = "v1"

# Refusal codes (machine codes only; never content).
APPROVAL_RECORD_MISSING = "approval_record_missing"
APPROVAL_RECORD_INVALID = "approval_record_invalid"
NOT_APPROVED = "not_approved"
EVALUATION_REPORT_MISSING = "evaluation_report_missing"
RULESET_HASH_MISMATCH = "ruleset_hash_mismatch"
REGISTRY_HASH_MISMATCH = "registry_hash_mismatch"
VERSION_MISMATCH = "version_mismatch"
RULESET_FILE_INVALID = "ruleset_file_invalid"

_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


class RulesetRefused(Exception):
    """The ruleset may not be pinned. ``codes`` lists every reason found (sorted, content-free)."""

    def __init__(self, codes: set[str]) -> None:
        self.codes = tuple(sorted(codes))
        super().__init__(",".join(self.codes))


@dataclass(frozen=True)
class PinnedPaths:
    approval: Path
    ruleset: Path
    registry: Path


def parse_approval_record(path: Path) -> ApprovalRecord:
    """The record is the single fenced ```json block in the Markdown file."""
    if not path.is_file():
        raise RulesetRefused({APPROVAL_RECORD_MISSING})
    blocks = _JSON_BLOCK.findall(path.read_text(encoding="utf-8"))
    if len(blocks) != 1:
        raise RulesetRefused({APPROVAL_RECORD_INVALID})
    try:
        return ApprovalRecord.model_validate(json.loads(blocks[0]))
    except (ValueError, ValidationError):
        raise RulesetRefused({APPROVAL_RECORD_INVALID}) from None


def pinned_paths(version: str = PINNED_VERSION, rulesets_dir: Path = RULESETS_DIR) -> PinnedPaths:
    """The approval record names the registry version; the record is the authority."""
    approval = rulesets_dir / f"APPROVAL_{version}.md"
    record = parse_approval_record(approval)
    return PinnedPaths(approval=approval, ruleset=rulesets_dir / f"{version}.json",
                       registry=rulesets_dir / f"registry_{record.registry_version}.json")


def refusal_codes(record: ApprovalRecord, ruleset_bytes: bytes, registry_bytes: bytes) -> set[str]:
    """Every reason this record does not authorise these exact bytes (empty set = authorised)."""
    codes: set[str] = set()
    if record.status is not RulesetStatus.APPROVED:
        codes.add(NOT_APPROVED)
    if record.evaluation_report_sha256 is None:
        codes.add(EVALUATION_REPORT_MISSING)
    if ids.sha256_hex(ruleset_bytes) != record.ruleset_sha256:
        codes.add(RULESET_HASH_MISMATCH)
    if ids.sha256_hex(registry_bytes) != record.registry_sha256:
        codes.add(REGISTRY_HASH_MISMATCH)
    return codes


def load_approved_bundle(paths: PinnedPaths) -> RulesetBundle:
    """Verify, then parse. Raises RulesetRefused listing every reason; never returns a bundle the
    record does not authorise."""
    record = parse_approval_record(paths.approval)
    try:
        ruleset_bytes, registry_bytes = paths.ruleset.read_bytes(), paths.registry.read_bytes()
    except OSError:
        raise RulesetRefused({RULESET_FILE_INVALID}) from None
    codes = refusal_codes(record, ruleset_bytes, registry_bytes)
    try:
        ruleset = Ruleset.model_validate_json(ruleset_bytes)
        registry = TermRegistry.model_validate_json(registry_bytes)
    except ValidationError:
        raise RulesetRefused(codes | {RULESET_FILE_INVALID}) from None
    if (ruleset.ruleset_version != record.ruleset_version or registry.registry_version != record.registry_version
            or ruleset.registry_version != registry.registry_version):
        codes.add(VERSION_MISMATCH)
    if codes:
        raise RulesetRefused(codes)
    return RulesetBundle(ruleset=ruleset, registry=registry, ruleset_sha256=record.ruleset_sha256,
                         registry_sha256=record.registry_sha256)


def load_pinned(version: str = PINNED_VERSION, rulesets_dir: Path = RULESETS_DIR) -> RulesetBundle:
    return load_approved_bundle(pinned_paths(version, rulesets_dir))


def approved_bundle_loader(version: str = PINNED_VERSION,
                           rulesets_dir: Path = RULESETS_DIR) -> Callable[[], RulesetBundle]:
    """For offline tools: every call re-reads and re-verifies (raises RulesetRefused)."""

    def load() -> RulesetBundle:
        return load_pinned(version, rulesets_dir)

    return load


def api_bundle_loader(version: str = PINNED_VERSION, rulesets_dir: Path = RULESETS_DIR) -> Callable[[], RulesetBundle]:
    """For I1: ``create_app(engine=get_engine(), bundle_loader=api_bundle_loader())``.

    A refusal becomes B2's ``ApiError(RULESET_UNAPPROVED)`` (503, error code only), so the API
    reports "ruleset not approved" instead of a 500 and never runs checks on unapproved rules."""
    from noteguard.api.errors import ApiError
    from noteguard.contracts.errors import ErrorCode

    def load() -> RulesetBundle:
        try:
            return load_pinned(version, rulesets_dir)
        except RulesetRefused:
            raise ApiError(ErrorCode.RULESET_UNAPPROVED) from None

    return load


def bundle_content_sha256(bundle: RulesetBundle) -> str:
    """Hash of the parsed content (not the files): detects in-place edits of a loaded bundle."""
    return ids.sha256_hex(bundle.model_dump_json(by_alias=True))
