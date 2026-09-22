"""Golden fixtures are in sync with the hand-written declarations and valid under the contract. owner: B0."""

from __future__ import annotations

import importlib.util
import json

import pytest

from noteguard.contracts import ids, states
from noteguard.contracts.types import BubbleStatus, EncounterSnapshot, Flag, QuestionBubble, Summary
from tests.support import golden
from tests.support.builders import AUTHOR
from tests.support.golden import ENCOUNTERS, EXPECTED, ROOT

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]


def _materializer():
    spec = importlib.util.spec_from_file_location("materialize_goldens", EXPECTED / "materialize.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_goldens_match_declarations():
    """The JSON is never hand-edited: a fresh materialisation must equal the committed files."""
    mat = _materializer()
    built = mat.build_all()
    assert set(built) == set(golden.SCENARIOS)
    for name, g in built.items():
        on_disk = json.loads((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))
        assert on_disk == json.loads(json.dumps(g, ensure_ascii=False)), f"{name}.json differs; run `make goldens`"
    assert (EXPECTED / "REVIEW_SHEET.md").read_text(encoding="utf-8") == mat.review_sheet(built)


def test_golden_invariants():
    for name in golden.SCENARIOS:
        g = golden.load(name)
        snap = golden.snapshot(name)
        for f in map(Flag.model_validate, g["flags"]):
            assert f.state not in states.ENGINE_FORBIDDEN_TARGETS
            assert f.flag_id == ids.flag_id(f.rule_id.value, snap.encounter.encounter_id, f.subject_key)
            if int(f.tier) == 1:  # never unassigned: RC, else the attending (8.6)
                e = snap.encounter
                assert f.owner_staff_id == (e.responsible_clinician_id or e.attending_clinician_id)
        for b in map(QuestionBubble.model_validate, g["bubbles"]):
            assert b.status in set(BubbleStatus)
        Summary.model_validate(g["summary"])
    assert golden.load("ENC-B1_1600")["flags"] == []


def test_fixture_pdfs_extract_as_recorded():
    """Pins the pdfplumber extraction B2's intake must reproduce for the fixture PDFs."""
    by_sha = {ids.sha256_hex(p.read_bytes()): p for p in (ROOT / "fixtures" / "pdfs").glob("*.pdf")}
    seen = 0
    for p in ENCOUNTERS.glob("ENC-*.json"):
        snap = EncounterSnapshot.model_validate_json(p.read_text(encoding="utf-8"))
        ext = {e.source_version_id: e for e in snap.extractions}
        for v in snap.versions:
            if v.media_type != "application/pdf":
                continue
            data = by_sha[v.sha256].read_bytes()
            text, pages, status = AUTHOR.extract_pdf(data)
            e = ext[v.source_version_id]
            assert (text, status) == (e.text, e.status.value)
            assert pages == [pg.model_dump() for pg in e.pages]
            seen += 1
    assert seen == 2
