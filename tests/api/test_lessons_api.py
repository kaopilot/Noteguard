"""Lesson tests L6-L8, L11, L12, L15, L16, L20, 409 on stale decision, no-store headers. owner: B2."""

import ast
import dataclasses
import inspect
import json
import logging
import re
from datetime import datetime, timezone

import pytest

from noteguard.api.app import create_app
from noteguard.api.audit import verify_chain
from noteguard.api.errors import ApiError
from noteguard.api.settings import Settings
from noteguard.api.store import WorkspaceStore
from noteguard.contracts import log_allowlist
from noteguard.contracts import routes as R
from noteguard.contracts.api_models import AddPdfSourceForm, AddTextSourceRequest, FeedbackRequest
from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.types import AuditOutcome, DecisionRequest
from tests.api.helpers import SCAN, ctx_of, decide, note, session, upload_pdf, version_with_status
from tests.support.api import A1, login, run_cutoff, url
from tests.support.builders import staff_id
from tests.support.golden import ROOT, load
from tests.support.lanes import client, real_app

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
    that returns or mutates encounter data still refuses a non-member.
    Mutation (applied, see decisions/B2.md): drop the membership check in WorkspaceStore._gate -> fails."""
    app = real_app()
    store: WorkspaceStore = app.state.store
    lim, lh = session(app, "lim", "ENC-A1_1130")
    alg, scan_vid = _flag("ALG-001")["flag_id"], version_with_status(lim, lh, A1, "no_text_layer")
    cutoff = datetime.fromisoformat(load("ENC-A1_1600")["cutoff"])
    calls = {
        "get_encounter": lambda s, x: s.get_encounter(x, A1),
        "get_source_text": lambda s, x: s.get_source_text(x, A1, scan_vid),
        "add_text_source": lambda s, x: s.add_text_source(x, A1, AddTextSourceRequest.model_validate(note())),
        "add_pdf_source": lambda s, x: s.add_pdf_source(x, A1, AddPdfSourceForm.model_validate(
            dict(title="t", discipline="other", author_staff_id=staff_id("lim"), source_time="2026-09-21T04:30:00Z")),
            SCAN.read_bytes()),
        "run_checks": lambda s, x: s.run_checks(x, A1, cutoff),
        "latest_run": lambda s, x: s.latest_run(x, A1),
        "list_flags": lambda s, x: s.list_flags(x, A1),
        "get_flag": lambda s, x: s.get_flag(x, A1, alg),
        "decide": lambda s, x: s.decide(x, A1, alg, DecisionRequest(action="accept", expected_revision=1)),
        "bubbles": lambda s, x: s.bubbles(x, A1),
        "summary": lambda s, x: s.summary(x, A1),
        "closure": lambda s, x: s.closure(x, A1),
        "glance": lambda s, x: s.glance(x, A1),
        "attempt_close": lambda s, x: s.attempt_close(x, A1),
        "issue_document_token": lambda s, x: s.issue_document_token(x, A1, scan_vid),
        "record_feedback": lambda s, x: s.record_feedback(x, A1, FeedbackRequest(flag_id=alg, usefulness="useful")),
        "feedback_events": lambda s, x: s.feedback_events(x, A1),
    }
    # No encounter data (identity / own workspace / filtered list / token-bound), each asserted below.
    exempt = {"login", "staff_for_session", "logout", "create_workspace", "resolve_workspace", "reset_workspace",
              "list_encounters", "read_document"}
    public = {n for n, _ in inspect.getmembers(WorkspaceStore, inspect.isfunction) if not n.startswith("_")}
    assert public == set(calls) | exempt, "classify every new store method here"
    lim_ctx = ctx_of(app, lim, lh)
    for key in ("kaur", "siti", "rao"):  # same clinic, no care team / clinic admin / medical director
        c, h = session(app, key)
        ctx = ctx_of(app, c, h)
        for name, call in calls.items():
            with pytest.raises(ApiError) as exc:
                call(store, ctx)
            assert exc.value.code is ErrorCode.NOT_FOUND, (key, name)
        assert A1 not in [e.encounter_id for e in store.list_encounters(ctx)]
        forged = dataclasses.replace(lim_ctx, staff=ctx.staff)  # someone else's workspace hash
        for name, call in calls.items():
            with pytest.raises(ApiError) as exc:
                call(store, forged)
            assert exc.value.code is ErrorCode.WORKSPACE_REQUIRED, (key, name)
        with pytest.raises(ApiError):
            store.reset_workspace(forged)
    token = store.issue_document_token(lim_ctx, A1, scan_vid).document_token
    with pytest.raises(ApiError) as exc:
        store.read_document(store.staff_for_session(client(app).post(R.SESSION, json={"staff_id": staff_id("kaur")})
                                                    .cookies.get(R.SESSION_COOKIE)), token)
    assert exc.value.code is ErrorCode.DOCUMENT_TOKEN_INVALID
    # In scope, wrong role: refused at the store with no route in front of it.
    tan, th = session(app, "tan", "ENC-A1_1130")
    for call in (lambda s, x: s.attempt_close(x, A1),
                 lambda s, x: s.decide(x, A1, alg, DecisionRequest(action="dismiss", expected_revision=1,
                                                                    reason_code="not_clinically_relevant"))):
        with pytest.raises(ApiError) as exc:
            call(store, ctx_of(app, tan, th))
        assert exc.value.code is ErrorCode.FORBIDDEN_ROLE


def test_audit_allowlist(caplog):
    """L8: every audit event and log record carries only log_allowlist.LOG_KEYS keys with valid
    values; the hash chain verifies from GENESIS_AUDIT_HASH.
    Mutations (applied): skip sanitize() in log_event -> None-valued keys reach the log -> fails;
    drop prev_event_hash from the hashed fields -> tamper step passes -> fails."""
    app = real_app()
    caplog.set_level(logging.DEBUG)
    c, h = session(app, "lim", "ENC-A1_1130")
    assert _decide(c, h, "DOSE-001", action="accept", expected_revision=1).status_code == 200
    assert _decide(c, h, "DOSE-001", action="accept", expected_revision=1).status_code == 409
    assert c.post(url(R.FEEDBACK, encounter_id=A1), headers=h,
                  json={"flag_id": _flag("DOSE-001")["flag_id"], "usefulness": "useful"}).status_code == 201
    vid = upload_pdf(c, h, A1, SCAN.read_bytes()).json()["note_version_id"]
    tok = c.post(url(R.DOCUMENT_TOKEN, encounter_id=A1, source_version_id=vid), headers=h).json()["document_token"]
    assert c.get(url(R.DOCUMENT, document_token=tok)).status_code == 200
    k, kh = session(app, "kaur")
    assert k.get(url(R.ENCOUNTER, encounter_id=A1), headers=kh).status_code == 404
    events = app.state.audit.events()
    actions = {e.action.value for e in events}
    assert {"session_start", "workspace_create", "check_run", "flag_raised", "decision_recorded", "decision_rejected",
            "source_version_added", "document_token_issued", "document_read", "access_denied"} <= actions
    for e in events:
        d = e.model_dump(mode="json")
        assert set(d) <= log_allowlist.AUDIT_KEYS
        for key, value in d.items():
            assert value is None or log_allowlist.is_allowed(key, value), key
    assert verify_chain(events)
    assert not verify_chain(events[:3] + events[4:])  # dropped event
    assert not verify_chain(events[:5] + (events[5].model_copy(update={"outcome": AuditOutcome.DENIED}),) + events[6:])
    records = [json.loads(r.getMessage()) for r in caplog.records if r.name == "noteguard"]
    assert {r["event"] for r in records} >= {"http_request", "audit", "check_run", "decision", "intake"}
    for rec in records:
        assert set(rec) <= set(log_allowlist.LOG_KEYS)
        assert all(log_allowlist.is_allowed(key, value) for key, value in rec.items()), rec


def test_no_unread_config_keys():
    """L11: every configuration key the app defines is read somewhere, and has a behaviour test
    (test_api_behaviour.CONFIG_EFFECTS). Mutation (applied): add an unread key -> fails."""
    real_app()
    from tests.api.test_api_behaviour import CONFIG_EFFECTS

    names = {f.name for f in dataclasses.fields(Settings)}
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "noteguard").rglob("*.py") if p.name != "settings.py")
    unread = [n for n in names if not re.search(r"settings\." + n + r"\b", src)]
    assert not unread, unread
    assert set(CONFIG_EFFECTS) == names


def test_no_env_conditional_security(monkeypatch):
    """L12: authz, headers and logging do not change with environment variables.
    Mutation (applied): `if os.getenv("NOTEGUARD_ENV") == "development": return ctx` in the route
    guard -> the AST scan fails."""
    real_app()
    for pkg in ("api", "intake", "redaction"):
        for p in (ROOT / "noteguard" / pkg).rglob("*.py"):
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                hit = (isinstance(node, ast.Attribute) and node.attr in {"environ", "environb", "getenv"}) or \
                      (isinstance(node, ast.Name) and node.id in {"environ", "getenv"}) or \
                      (isinstance(node, ast.ImportFrom) and node.module == "os")
                assert not hit, f"{p.relative_to(ROOT)}:{getattr(node, 'lineno', '?')} reads the environment"
    envs = ({}, {"NOTEGUARD_ENV": "development", "ENV": "dev", "DEBUG": "1", "TESTING": "true",
                 "NOTEGUARD_AUTH": "off", "NOTEGUARD_DEBUG": "1", "PYTHONDEVMODE": "1"})
    for env in envs:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        app = create_app()
        k, kh = session(app, "kaur")
        r = k.get(url(R.ENCOUNTER, encounter_id=A1), headers=kh)
        assert r.status_code == 404 and "no-store" in r.headers["cache-control"], env
        t, th = session(app, "tan", "ENC-A1_1130")
        r = t.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=_flag("ALG-001")["flag_id"]), headers=th,
                   json={"action": "dismiss", "expected_revision": 1, "reason_code": "not_clinically_relevant"})
        assert r.status_code == 403, env
        r = t.post(url(R.CHECK_RUNS, encounter_id=A1), headers=th, json={"cutoff": "ZQX-ENV-1"})
        assert r.status_code == 422 and "ZQX-ENV-1" not in r.text, env


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
