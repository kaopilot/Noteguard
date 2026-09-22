"""Lesson tests L6-L8, L11, L12, L15, L16, L20, 409 on stale decision, no-store headers. owner: B2."""

import pytest

from noteguard.contracts import routes as R
from noteguard.contracts.types import DecisionRequest
from tests.support.api import A1, login, run_cutoff, url
from tests.support.golden import load
from tests.support.lanes import client, not_implemented, real_app

pytestmark = [pytest.mark.owner("B2"), pytest.mark.api]
G = load("ENC-A1_1130")


def _flag(rule: str) -> dict:
    return next(f for f in G["flags"] if f["rule_id"] == rule)


def _decide(c, h, rule, **body):
    return c.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=_flag(rule)["flag_id"]), headers=h, json=body)


def _setup(staff_key="lim"):
    c = client(real_app())
    h = login(c, staff_key)
    assert run_cutoff(c, h, A1, "ENC-A1_1130").status_code == 200
    return c, h


def test_store_layer_authz_fault_injection():
    """L6/L7: with the route-level dependency removed (fault injection), every store method
    that returns or mutates encounter data still refuses a non-member."""
    real_app()
    not_implemented("B2", "store-layer fault injection over every store read/write method")


def test_audit_allowlist():
    """L8: every audit event and log record carries only log_allowlist.LOG_KEYS keys with valid
    values; the hash chain verifies from GENESIS_AUDIT_HASH."""
    real_app()
    not_implemented("B2", "capture audit events for a login -> run -> decision flow and validate them")


def test_no_unread_config_keys():
    """L11: every configuration key the app defines is read somewhere."""
    real_app()
    not_implemented("B2", "enumerate settings fields and assert each is referenced")


def test_no_env_conditional_security():
    """L12: authz, headers and logging do not change with environment variables."""
    real_app()
    not_implemented("B2", "run the access-control and header checks under differing env values")


def test_decision_requires_reason_code():
    """L15. Mutation: default a missing reason code -> the first request succeeds."""
    c, h = _setup()
    r = _decide(c, h, "DOSE-001", action="dismiss", expected_revision=1)
    assert r.status_code == 422 and r.json() == {"error_code": "reason_code_required"}
    r = _decide(c, h, "DOSE-001", action="dismiss", expected_revision=1, reason_code="dose_entry_current")
    assert r.status_code == 422 and r.json() == {"error_code": "reason_code_not_allowed"}
    r = _decide(c, h, "DOSE-001", action="dismiss", expected_revision=1, reason_code="not_clinically_relevant")
    assert r.status_code == 200


def test_no_bulk_decisions():
    """L15: one flag per decision. Mutation: accept a list body -> 200."""
    c, h = _setup()
    assert "flag_ids" not in DecisionRequest.model_fields
    r = c.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=_flag("DOSE-001")["flag_id"]), headers=h,
               json=[{"action": "accept", "expected_revision": 1}, {"action": "accept", "expected_revision": 1}])
    assert r.status_code == 422 and r.json()["error_code"] in {"bulk_not_supported", "validation_failed"}


def test_role_matrix_staff_prepare_clinician_close():
    """L16: staff prepare, clinicians close. Mutation: allow any member to resolve -> clerk resolves."""
    app = real_app()
    lee = client(app)
    hl = login(lee, "lee")
    assert run_cutoff(lee, hl, A1, "ENC-A1_1130").status_code == 200
    r = _decide(lee, hl, "PEND-001", action="mark_ready_for_clinician", expected_revision=1,
                prepared_check="source_document_checked")
    assert r.status_code == 200
    f = lee.get(url(R.FLAG, encounter_id=A1, flag_id=_flag("PEND-001")["flag_id"]), headers=hl).json()["flag"]
    assert f["ready_for_clinician"] is True and f["state"] == "open"
    r = _decide(lee, hl, "PEND-001", action="resolve", expected_revision=f["revision"],
                reason_code="owner_and_timing_documented")
    assert r.status_code == 403
    c, h = _setup("lim")
    pen = next(e for e in _flag("ALG-001")["evidence"] if e["role_in_flag"] == "counter_claim")
    r = _decide(c, h, "ALG-001", action="resolve", expected_revision=1, reason_code="allergy_entry_confirmed",
                adjudicated_evidence=[{"note_version_id": pen["note_version_id"], "start": pen["start"], "end": pen["end"]}])
    assert r.status_code == 200


def test_validation_error_no_echo():
    """L20. Mutation: FastAPI's default 422 handler -> the marker is echoed."""
    c, h = _setup()
    marker = "ZQX-ECHO-5512"
    r = c.post(url(R.CHECK_RUNS, encounter_id=A1), headers=h, json={"cutoff": marker})
    assert r.status_code == 422 and r.json() == {"error_code": "validation_failed"} and marker not in r.text
    r = _decide(c, h, "DOSE-001", action=marker, expected_revision=1)
    assert r.status_code == 422 and marker not in r.text


def test_concurrent_decision_409():
    """Feedback 10. Mutation: skip the compare-and-swap -> the second decision overwrites."""
    c, h = _setup()
    first = _decide(c, h, "DOSE-001", action="accept", expected_revision=1)
    assert first.status_code == 200
    second = _decide(c, h, "DOSE-001", action="edit", expected_revision=1, edit_field="explanation",
                     rationale_text="second actor")
    assert second.status_code == 409
    body = second.json()
    assert body["error_code"] == "stale_revision" and body["current_revision"] == 2
    assert body["last_decision_action"] == "accept" and body["last_decision_actor_staff_id"]


def test_no_store_headers():
    """Every API response, including errors, is private, no-store."""
    c, h = _setup()
    for r in (c.get(R.HEALTH), c.get(url(R.ENCOUNTER, encounter_id=A1), headers=h),
              c.get(url(R.FLAGS, encounter_id=A1), headers=h), c.get("/api/encounters/nope", headers=h),
              c.post(url(R.CHECK_RUNS, encounter_id=A1), headers=h, json={"cutoff": "x"})):
        cc = r.headers.get("cache-control", "")
        assert "no-store" in cc and "private" in cc, (r.request.url, cc)
