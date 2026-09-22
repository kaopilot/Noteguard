"""Build small synthetic EncounterSnapshots for rule tests (B0). Uses the fictional
ENC-A1 clinic and staff. IDs are deterministic from labels."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from noteguard.contracts import ids
from noteguard.contracts.types import EncounterSnapshot

from .golden import ROOT

_spec = importlib.util.spec_from_file_location("author_fixtures", ROOT / "fixtures" / "author_fixtures.py")
AUTHOR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AUTHOR)  # type: ignore[union-attr]

fid = AUTHOR.fid
staff_id = AUTHOR.staff_id
SGT = timezone(timedelta(hours=8))


def at(hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(*AUTHOR.DAY, h, m, tzinfo=SGT).astimezone(timezone.utc)


@dataclass(frozen=True)
class Note:
    key: str  # unique per snapshot
    time: str  # "HH:MM" SGT source_time
    author: str  # staff key, e.g. "lim"
    text: str
    status: str = "not_applicable"  # or complete/partial/no_text_layer for PDFs
    version_time: str | None = None  # defaults to time
    version: int = 1


def build_snapshot(notes: list[Note], *, ref: str = "ENC-T1", rc: str | None = "lim",
                   team: list[tuple[str, str]] | None = None, prior_flags=(), decisions=()) -> EncounterSnapshot:
    team = team or AUTHOR.ENC_A1_TEAM
    enc_id = fid(f"encounter/{ref}")
    patient = {"patient_id": fid(f"patient/{ref}"), "patient_ref": fid(f"patient_ref/{ref}"),
               "display_label": f"Synthetic patient {ref}"}
    encounter = {"encounter_id": enc_id, "encounter_ref": ref, "clinic_id": AUTHOR.CLINIC["clinic_id"],
                 "patient_id": patient["patient_id"], "setting": "medical ward", "started_at": at("08:00"),
                 "responsible_clinician_id": staff_id(rc) if rc else None,
                 "attending_clinician_id": staff_id(rc or "lim")}
    memberships = [{"encounter_id": enc_id, "staff_id": staff_id(k), "team_role": r, "valid_from": at("07:00")}
                   for k, r in team]
    sources, versions, extractions, prev = {}, [], [], {}
    for n in notes:
        src_id = fid(f"{ref}/source/{n.key}")
        is_pdf = n.status != "not_applicable"
        if src_id not in sources:
            sources[src_id] = {"source_id": src_id, "encounter_id": enc_id, "source_system": "test",
                               "identifier_namespace": "urn:test", "external_id": f"{ref}-{n.key}",
                               "source_type": "pdf" if is_pdf else "pasted_text", "author_staff_id": staff_id(n.author),
                               "discipline": AUTHOR.STAFF[n.author][1], "title": n.key, "source_time": at(n.time)}
        vid = fid(f"{ref}/source/{n.key}/v{n.version}")
        sha = ids.sha256_hex(n.text)
        versions.append({"source_version_id": vid, "source_id": src_id, "version": n.version,
                         "version_time": at(n.version_time or n.time), "received_at": at(n.version_time or n.time),
                         "sha256": sha, "byte_length": len(n.text.encode()),
                         "media_type": "application/pdf" if is_pdf else "text/plain; charset=utf-8",
                         "idempotency_key": ids.idempotency_key("urn:test", f"{ref}-{n.key}", n.version, sha),
                         "supersedes_version_id": prev.get(src_id)})
        pages = [{"page": 1, "start": 0, "end": len(n.text), "char_count": len(n.text)}] if is_pdf else []
        extractions.append({"source_version_id": vid, "status": n.status, "text": n.text, "pages": pages,
                            "extractor": "pdfplumber@0.11.7" if is_pdf else "paste@1"})
        prev[src_id] = vid
    staff = [AUTHOR.staff_record(k) for k in sorted({k for k, _ in team} | {n.author for n in notes})]
    return EncounterSnapshot.model_validate({
        "clinic": AUTHOR.CLINIC, "patient": patient, "encounter": encounter, "staff": staff,
        "memberships": memberships, "sources": list(sources.values()), "versions": versions,
        "extractions": extractions, "prior_flags": list(prior_flags), "decisions": list(decisions)})


def run_synthetic(eng, snap: EncounterSnapshot, cutoff_hhmm: str = "23:00"):
    from .golden import bundle

    return eng.run_checks(snap, bundle(), at(cutoff_hhmm), run_id=fid(f"run/{snap.encounter.encounter_ref}"),
                          evaluated_at=at(cutoff_hhmm) + timedelta(minutes=1))
