"""Required test 4. owner: B2 (extraction status + issue). The bubble-downgrade half is in
tests/engine/test_question_bubble_grounding.py (B1). Assumes each new workspace is seeded with
the synthetic ENC-A1/ENC-B1 case (OPEN-3 default, DECISIONS.md)."""

import pytest

from noteguard.contracts import ids
from noteguard.contracts import routes as R
from noteguard.contracts.api_models import PDF_FILE_FIELD, SourceView
from tests.support.api import A1, login, run_cutoff, url
from tests.support.builders import staff_id
from tests.support.golden import ROOT
from tests.support.lanes import client, real_app

pytestmark = [pytest.mark.owner("B2"), pytest.mark.api]
SCAN = ROOT / "fixtures" / "pdfs" / "ENC-A1_outside_lab_report_scanned.pdf"


def test_pdf_extraction_boundary():
    """Mutation: treat an empty text layer as 'complete' -> status and PDF-001 assertions fail."""
    app = real_app()
    c = client(app)
    h = login(c, "ravi")
    pdf = SCAN.read_bytes()
    r = c.post(url(R.SOURCES_PDF, encounter_id=A1), headers=h,
               files={PDF_FILE_FIELD: ("scan.pdf", pdf, "application/pdf")},
               data={"title": "Re-uploaded scan", "discipline": "other", "author_staff_id": staff_id("ravi"),
                     "source_time": "2026-09-21T04:30:00Z"})
    assert r.status_code in (200, 201), r.status_code
    sv = SourceView.model_validate(r.json())
    assert sv.extraction_status.value == "no_text_layer"
    assert sv.sha256 == ids.sha256_hex(pdf) and sv.page_count == 1  # original retained, checksummed
    t = c.get(url(R.SOURCE_TEXT, encounter_id=A1, source_version_id=sv.source_version_id), headers=h)
    assert t.status_code == 200 and t.json()["extraction_status"] == "no_text_layer" and t.json()["text"] == ""
    h2 = login(c, "lim")  # fresh seeded workspace
    run = run_cutoff(c, h2, A1, "ENC-A1_1600")
    assert run.status_code == 200
    pdf_flags = [f for f in run.json()["flags"] if f["rule_id"] == "PDF-001"]
    assert len(pdf_flags) == 1 and pdf_flags[0]["tier"] == 2
    ev = pdf_flags[0]["evidence"]
    assert [e["role_in_flag"] for e in ev] == ["extraction_gap"] and ev[0]["page"] == 1 and ev[0]["quote"] == ""
