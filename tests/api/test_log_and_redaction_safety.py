"""Required test 6. owner: B2. Marker test (Section 10.3) + redaction + egress gate."""

import logging

import pytest

from noteguard.contracts import routes as R
from noteguard.contracts.egress import QualifiedRedactedText
from tests.support.api import A1, login, run_cutoff, url
from tests.support.builders import staff_id
from tests.support.lanes import client, lane_module, real_app

pytestmark = [pytest.mark.owner("B2"), pytest.mark.api]
MARKER = "ZQX-MARKER-7731"
FAKE_NRIC = "S0000001I"  # synthetic, checksum-shaped only


def test_log_and_redaction_safety(caplog, capsys):
    """Mutations: log the request body on error -> MARKER in logs; redact in place -> original changes;
    skip the report checks in from_report -> an unqualified payload passes."""
    app = real_app()
    c = client(app)
    h = login(c, "lim")
    caplog.set_level(logging.DEBUG)
    body = {"title": f"Note {MARKER}", "discipline": "clinician", "author_staff_id": staff_id("lim"),
            "source_time": "2026-09-21T05:00:00Z", "text": f"Review {MARKER}. NRIC {FAKE_NRIC}. Potassium 6.4 mmol/L."}
    c.post(url(R.SOURCES, encounter_id=A1), headers=h, json=body)
    run_cutoff(c, h, A1, "ENC-A1_1130")
    c.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id="flg_" + "0" * 24), headers=h,
           json={"action": "edit", "expected_revision": 1, "edit_field": "explanation", "rationale_text": MARKER})
    c.get(f"/api/encounters/{MARKER}", headers=h)
    c.post(url(R.CHECK_RUNS, encounter_id=A1), headers=h, json={"cutoff": MARKER})
    out = capsys.readouterr()
    logged = "\n".join(f"{rec.getMessage()} {rec.__dict__!r}" for rec in caplog.records) + out.out + out.err
    assert MARKER not in logged and FAKE_NRIC not in logged

    red = lane_module("noteguard.redaction", "B2").get_redactor()
    original = f"Seen with daughter, NRIC {FAKE_NRIC}, phone 9123 4567."
    before = str(original)
    report = red.redact(original)
    assert original == before, "redaction must not mutate the original"
    assert FAKE_NRIC not in report.redacted_text and any(s.kind.value == "nric_fin" for s in report.spans)
    for s in report.spans:
        assert report.redacted_text[s.redacted_start:s.redacted_end] == s.token
        assert original[s.original_start:s.original_end] not in report.redacted_text
    with pytest.raises(ValueError):
        QualifiedRedactedText.from_report(report.model_copy(update={"residual_scan_passed": False}))
    forged = object.__new__(QualifiedRedactedText)
    object.__setattr__(forged, "text", original)
    object.__setattr__(forged, "sha256", "0" * 64)
    with pytest.raises(ValueError):
        forged.assert_qualified()  # a non-qualified payload is refused at the provider boundary
