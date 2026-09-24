"""Evaluation corpus for ``evaluate.py`` (B4). Offline only; never imported by the API.

Two parts, reported separately:
- ``b4_labelled``: fixtures/labelled_eval/cases.json, hand-written and hand-labelled by B4 from the
  rule catalog, committed before the engine was run on it (independent of engine development).
- ``golden``: the B0 golden scenarios (fixtures/expected), hand-written and signed off by @kaopilot at CP0.
  B1 developed the engine against them, so they are NOT independent evidence of generalisation.
Known-limit cases are built too, but the report keeps them out of the release gate (declared).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from noteguard.contracts import ids
from noteguard.contracts.types import EncounterSnapshot, RuleId, Tier

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "fixtures" / "labelled_eval" / "cases.json"
EXPECTED = ROOT / "fixtures" / "expected"
ENCOUNTERS = ROOT / "fixtures" / "encounters"
GOLDEN_SCENARIOS = ("ENC-A1_1130", "ENC-A1_1600", "ENC-A1_1600_rerun", "ENC-B1_1600", "ENC-C1_1000")
SGT = timezone(timedelta(hours=8))
_SRC = re.compile(r"\{src:([A-Za-z0-9_\-]+)\}")


@dataclass(frozen=True)
class Label:
    rule_id: RuleId
    subject: str  # exact subject key, or a prefix ending in '*'
    tier: Tier

    def matches(self, rule_id: RuleId, subject_key: str) -> bool:
        if rule_id is not self.rule_id:
            return False
        return subject_key.startswith(self.subject[:-1]) if self.subject.endswith("*") else subject_key == self.subject


@dataclass(frozen=True)
class Case:
    part: str  # "b4_labelled" | "golden" | "known_limit"
    case_id: str
    snapshot: EncounterSnapshot
    cutoff: datetime
    evaluated_at: datetime
    run_id: str
    expected: tuple[Label, ...]


def _fid(label: str) -> str:
    return str(uuid.UUID(bytes=hashlib.sha256(label.encode()).digest()[:16], version=4))


def _at(day: str, hhmm: str) -> datetime:
    y, m, d = map(int, day.split("-"))
    h, mi = map(int, hhmm.split(":"))
    return datetime(y, m, d, h, mi, tzinfo=SGT).astimezone(timezone.utc)


def _case_snapshot(doc: dict, c: dict) -> tuple[EncounterSnapshot, dict[str, str]]:
    day, ref, roster = doc["day"], c["case_id"], doc["staff"]
    clinic = {"clinic_id": _fid(f"clinic/{doc['clinic']['key']}"), "display_name": doc["clinic"]["display_name"]}
    sid = {k: _fid(f"labelled/staff/{k}") for k in roster}
    enc_id = _fid(f"labelled/encounter/{ref}")
    patient = {"patient_id": _fid(f"labelled/patient/{ref}"), "patient_ref": _fid(f"labelled/patient_ref/{ref}"),
               "display_label": f"Synthetic patient {ref}"}
    rc = c.get("rc")
    encounter = {"encounter_id": enc_id, "encounter_ref": ref, "clinic_id": clinic["clinic_id"],
                 "patient_id": patient["patient_id"], "setting": "medical ward", "started_at": _at(day, "07:30"),
                 "responsible_clinician_id": sid[rc] if rc else None,
                 "attending_clinician_id": sid[c.get("attending") or rc]}
    team = sorted({n["author"] for n in c["notes"]} | {k for k in (rc, c.get("attending")) if k})
    memberships = [{"encounter_id": enc_id, "staff_id": sid[k], "valid_from": _at(day, "07:00"),
                    "team_role": ("responsible_clinician" if k == rc else "attending" if k == c.get("attending")
                                  else "member")} for k in team]
    staff = [{"staff_id": sid[k], "clinic_id": clinic["clinic_id"], **roster[k]} for k in team]
    sources, versions, extractions, src_of = [], [], [], {}
    for n in c["notes"]:
        is_pdf = n.get("status", "not_applicable") != "not_applicable"
        src_id, vid = _fid(f"labelled/{ref}/source/{n['key']}"), _fid(f"labelled/{ref}/source/{n['key']}/v1")
        src_of[n["key"]] = src_id
        t, text = _at(day, n["time"]), n["text"]
        sha = ids.sha256_hex(text)
        sources.append({"source_id": src_id, "encounter_id": enc_id, "source_system": "labelled-eval",
                        "identifier_namespace": "urn:labelled-eval", "external_id": f"{ref}-{n['key']}",
                        "source_type": "pdf" if is_pdf else "pasted_text", "author_staff_id": sid[n["author"]],
                        "discipline": roster[n["author"]]["discipline"], "title": n["key"], "source_time": t})
        versions.append(dict(source_version_id=vid, source_id=src_id, version=1, version_time=t, received_at=t,
                             sha256=sha, byte_length=len(text.encode()),
                             media_type="application/pdf" if is_pdf else "text/plain; charset=utf-8",
                             idempotency_key=ids.idempotency_key("urn:labelled-eval", f"{ref}-{n['key']}", 1, sha),
                             supersedes_version_id=None))
        extractions.append({"source_version_id": vid, "status": n.get("status", "not_applicable"), "text": text,
                            "pages": [{"page": 1, "start": 0, "end": len(text), "char_count": len(text)}] if is_pdf else [],
                            "extractor": "pdfplumber@0.11.7" if is_pdf else "paste@1"})
    snap = EncounterSnapshot.model_validate({
        "clinic": clinic, "patient": patient, "encounter": encounter, "staff": staff, "memberships": memberships,
        "sources": sources, "versions": versions, "extractions": extractions})
    return snap, src_of


def _labels(items: list[dict], src_of: dict[str, str]) -> tuple[Label, ...]:
    return tuple(Label(RuleId(x["rule_id"]), _SRC.sub(lambda m: src_of[m.group(1)], x["subject"]), Tier(x["tier"]))
                 for x in items)


def load_cases(path: Path = CASES) -> tuple[Case, ...]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for part, key in (("b4_labelled", "cases"), ("known_limit", "known_limits")):
        for c in doc.get(key, []):
            snap, src_of = _case_snapshot(doc, c)
            cutoff = _at(doc["day"], c.get("cutoff", "23:00"))
            out.append(Case(part, c["case_id"], snap, cutoff, cutoff + timedelta(minutes=1),
                            _fid(f"labelled/run/{c['case_id']}"), _labels(c["expected"], src_of)))
    return tuple(out)


def _utc(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_golden(expected_dir: Path = EXPECTED, encounters_dir: Path = ENCOUNTERS) -> tuple[Case, ...]:
    out = []
    for name in GOLDEN_SCENARIOS:
        g = json.loads((expected_dir / f"{name}.json").read_text(encoding="utf-8"))
        raw = json.loads((encounters_dir / f"{g['encounter_ref']}.json").read_text(encoding="utf-8"))
        if g["prior_scenario"]:
            raw["prior_flags"] = json.loads((expected_dir / f"{g['prior_scenario']}.json").read_text(encoding="utf-8"))["flags"]
        labels = tuple(Label(RuleId(f["rule_id"]), f["subject_key"], Tier(f["tier"])) for f in g["flags"])
        out.append(Case("golden", name, EncounterSnapshot.model_validate(raw), _utc(g["cutoff"]),
                        _utc(g["evaluated_at"]), g["run_id"], labels))
    return tuple(out)


def corpus_sha256(paths: tuple[Path, ...] | None = None) -> str:
    """Hash of every corpus input file (cases + goldens + encounters), so a report pins its corpus."""
    paths = paths or (CASES, *(EXPECTED / f"{n}.json" for n in GOLDEN_SCENARIOS), *sorted(ENCOUNTERS.glob("ENC-*.json")))
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()
