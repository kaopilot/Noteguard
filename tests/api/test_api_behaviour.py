"""B2 API behaviour beyond the named skeletons (owner: B2). Each test states the mutation that
should make it fail; the ones actually applied are recorded in docs/decisions/B2.md."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import pytest

from noteguard.api.app import create_app
from noteguard.api.settings import Settings
from noteguard.contracts import ids
from noteguard.contracts import routes as R
from noteguard.contracts.types import EncounterSnapshot, FlagState
from noteguard.engine_stub import StubEngine
from noteguard.intake import pdf as intake_pdf
from tests.api.helpers import (
    REFERRAL,
    SCAN,
    decide,
    gflag,
    make_pdf,
    note,
    session,
    sources,
    upload_pdf,
    version_with_status,
)
from tests.support.api import A1, B1, C1, run_cutoff, url
from tests.support.builders import staff_id
from tests.support.golden import ROOT, load
from tests.support.lanes import client, real_app

pytestmark = [pytest.mark.owner("B2"), pytest.mark.api]
MARKER = "ZQX-MARKER-9048"
FAKE_NRIC = "S0000002G"


# --- golden fixtures served by the REAL API (stub engine behind the seam) ------------------

def _sorted_blockers(closure: dict) -> dict:
    out = dict(closure)
    for key in ("tier1_blockers", "tier2_open"):
        out[key] = sorted(closure[key], key=lambda b: b["flag_id"])  # golden order is hand-declared
    return out


def test_golden_views_through_api():
    """Flags, bubbles, summary and glance equal the goldens exactly; closure equal with blocker
    lists compared as sets. Mutation (applied): count only `open` Tier 1 in closure_view -> fails."""
    app = real_app()
    for staff, enc, names in (("lim", A1, ["ENC-A1_1130", "ENC-A1_1600_rerun"]), ("lim", A1, ["ENC-A1_1600"]),
                              ("wong", B1, ["ENC-B1_1600"]), ("lim", C1, ["ENC-C1_1000"])):
        c, h = session(app, staff)
        for name in names:
            g = load(name)
            r = run_cutoff(c, h, enc, name)
            assert r.status_code == 200 and r.json()["run"] == g["run"] and r.json()["flags"] == g["flags"], name
            assert c.get(url(R.FLAGS, encounter_id=enc), headers=h).json() == g["flags"], name
            b = c.get(url(R.BUBBLES, encounter_id=enc), headers=h).json()
            assert b["bubbles"] == g["bubbles"] and b["cutoff"] == g["cutoff"] and b["ai_status"] == "disabled", name
            assert c.get(url(R.SUMMARY, encounter_id=enc), headers=h).json() == g["summary"], name
            assert c.get(url(R.GLANCE, encounter_id=enc), headers=h).json() == g["glance"], name
            got = c.get(url(R.CLOSURE, encounter_id=enc), headers=h).json()
            assert _sorted_blockers(got) == _sorted_blockers(g["closure"]), name
            assert c.get(url(R.CHECK_RUN_LATEST, encounter_id=enc), headers=h).json()["flags"] == g["flags"]
            for f in g["flags"]:
                d = c.get(url(R.FLAG, encounter_id=enc, flag_id=f["flag_id"]), headers=h).json()
                assert d["flag"] == f and d["revisions"][-1]["revision"] == f["revision"], name


def test_views_before_any_run_are_not_found():
    """No check has run: flags/closure/summary are 404, never an empty 'all clear'."""
    c, h = session(real_app(), "lim")
    for route in (R.FLAGS, R.CLOSURE, R.GLANCE, R.SUMMARY, R.BUBBLES, R.CHECK_RUN_LATEST):
        r = c.get(url(route, encounter_id=A1), headers=h)
        assert r.status_code == 404 and r.json() == {"error_code": "not_found"}, route


# --- intake --------------------------------------------------------------------------

def test_paste_intake_versions_and_idempotency():
    """Mutations: skip the replay check -> duplicate rows; overwrite the version in place ->
    v1 text changes; ignore the client idempotency key -> no 409."""
    c, h = session(real_app(), "lim")
    post = lambda body: c.post(url(R.SOURCES, encounter_id=A1), headers=h, json=body)  # noqa: E731
    before = len(sources(c, h, A1))
    r1 = post(note())
    assert r1.status_code == 201
    v1 = r1.json()
    assert v1["version"] == 1 and v1["extraction_status"] == "not_applicable"
    assert v1["sha256"] == ids.sha256_hex(note()["text"])
    r2 = post(note())
    assert r2.status_code == 200 and r2.json()["note_version_id"] == v1["note_version_id"]  # replay, no new row
    other_author = post(note(author="tan", discipline="nursing"))
    assert other_author.status_code == 201 and other_author.json()["source_id"] != v1["source_id"]
    assert post(note(text="Different text.", idempotency_key="client-key-1")).status_code == 201
    assert post(note(text="Other text.", idempotency_key="client-key-1")).json() == {"error_code": "idempotency_conflict"}
    amended = note(text="Potassium 5.1 mmol/L on repeat. Amended: ECG reviewed.", source_id=v1["source_id"])
    r3 = post(amended)
    assert r3.status_code == 201
    v2 = r3.json()
    assert (v2["version"], v2["supersedes_version_id"], v2["source_id"]) == (2, v1["note_version_id"], v1["source_id"])
    assert post(dict(amended, title="Renamed", text="x")).json() == {"error_code": "validation_failed"}
    assert post(note(author="kaur")).json() == {"error_code": "validation_failed"}  # owner must be on the team
    assert len(sources(c, h, A1)) == before + 4  # r1, other author, new text, v2
    t1 = c.get(url(R.SOURCE_TEXT, encounter_id=A1, source_version_id=v1["note_version_id"]), headers=h).json()
    assert t1["text"] == note()["text"]  # the original version is immutable


def test_pdf_extraction_reproduces_pinned_contract():
    """B2's intake extraction equals the recorded fixture extractions (the pdfplumber contract
    pinned by B0). Mutation (applied): treat empty pages as complete -> fails."""
    snap = EncounterSnapshot.model_validate_json((ROOT / "fixtures/encounters/ENC-A1.json").read_text(encoding="utf-8"))
    recorded = {v.sha256: next(e for e in snap.extractions if e.source_version_id == v.source_version_id)
                for v in snap.versions if v.media_type == "application/pdf"}
    for path in (SCAN, REFERRAL):
        data = path.read_bytes()
        got = intake_pdf.extract(data, max_pages=50, timeout_s=30)
        want = recorded[ids.sha256_hex(data)]
        assert (got.text, got.pages, got.status) == (want.text, want.pages, want.status), path.name
    partial = intake_pdf.extract(make_pdf(["Page one text", ""]), max_pages=50, timeout_s=30)
    assert partial.status.value == "partial" and [p.char_count for p in partial.pages][1] == 0
    assert "2" in partial.note


def test_pdf_intake_boundaries():
    """Not a PDF is refused (not retained); an unparseable PDF is RETAINED as failed; a selectable
    PDF is complete with page offsets; the original bytes are checksummed."""
    c, h = session(real_app(), "ravi")
    before = len(sources(c, h, A1))
    r = upload_pdf(c, h, A1, b"GIF89a not a pdf", author="ravi")
    assert r.status_code == 415 and r.json() == {"error_code": "pdf_not_a_pdf"}
    assert len(sources(c, h, A1)) == before
    broken = b"%PDF-1.4\nthis is not really a pdf"
    r = upload_pdf(c, h, A1, broken, author="ravi")
    assert r.status_code == 201 and r.json()["extraction_status"] == "failed" and r.json()["extraction_note"]
    assert r.json()["sha256"] == ids.sha256_hex(broken)
    pdf = make_pdf(["Troponin pending, owner Dr Lim, by 18:00", "Second page"])
    r = upload_pdf(c, h, A1, pdf, author="ravi")
    assert r.status_code == 201 and r.json()["extraction_status"] == "complete" and r.json()["page_count"] == 2
    t = c.get(url(R.SOURCE_TEXT, encounter_id=A1, source_version_id=r.json()["note_version_id"]), headers=h).json()
    assert t["text"].startswith("Troponin pending") and t["pages"][1]["start"] == t["pages"][0]["end"] + 1
    assert len(sources(c, h, A1)) == before + 2
    again = upload_pdf(c, h, A1, pdf, author="ravi")
    assert again.status_code == 200 and again.json()["note_version_id"] == r.json()["note_version_id"]  # replay


def test_document_token_single_use_bound_and_scoped():
    """Mutations: do not consume the token -> second read 200; skip the staff binding -> Nurse
    Tan reads Dr Lim's token."""
    app = real_app()
    c, h = session(app, "lim")
    scan = version_with_status(c, h, A1, "no_text_layer")
    tok = c.post(url(R.DOCUMENT_TOKEN, encounter_id=A1, source_version_id=scan), headers=h).json()
    assert tok["single_use"] is True
    assert datetime.fromisoformat(tok["expires_at"]) <= datetime.now(timezone.utc) + timedelta(seconds=61)
    r = c.get(url(R.DOCUMENT, document_token=tok["document_token"]))
    assert r.status_code == 200 and r.content == SCAN.read_bytes() and r.headers["content-type"] == "application/pdf"
    assert "no-store" in r.headers["cache-control"]
    r = c.get(url(R.DOCUMENT, document_token=tok["document_token"]))
    assert r.status_code == 404 and r.json() == {"error_code": "document_token_invalid"}
    text_vid = version_with_status(c, h, A1, "not_applicable")
    assert c.post(url(R.DOCUMENT_TOKEN, encounter_id=A1, source_version_id=text_vid), headers=h).status_code == 404
    k, kh = session(app, "kaur")
    assert k.post(url(R.DOCUMENT_TOKEN, encounter_id=A1, source_version_id=scan), headers=kh).status_code == 404
    tok2 = c.post(url(R.DOCUMENT_TOKEN, encounter_id=A1, source_version_id=scan), headers=h).json()["document_token"]
    t, _ = session(app, "tan")
    assert t.get(url(R.DOCUMENT, document_token=tok2)).json() == {"error_code": "document_token_invalid"}
    assert c.get(url(R.DOCUMENT, document_token=tok2)).status_code == 404  # presented once: burnt
    assert client(app).get(url(R.DOCUMENT, document_token="anything")).status_code == 401


# --- closure and decisions -----------------------------------------------------------

def test_closure_attempt_and_decision_effect():
    """Closure: responsible clinician only; blocked by Tier 1, by stale sources and by a cutoff
    that does not cover every source. Mutation (applied): drop the coverage check -> the 11:30
    close succeeds with 16:00 notes unchecked."""
    app = real_app()
    w, wh = session(app, "wong", "ENC-B1_1600")
    assert w.post(url(R.CLOSURE, encounter_id=B1), headers=wh).status_code == 200
    assert w.post(url(R.SOURCES, encounter_id=B1), headers=wh,
                  json=note(author="wong", text="Late entry: reviewed.")).status_code == 201
    r = w.post(url(R.CLOSURE, encounter_id=B1), headers=wh)
    assert r.status_code == 409 and r.json() == {"error_code": "closure_blocked"}  # sources changed since the run
    assert w.get(url(R.SUMMARY, encounter_id=B1), headers=wh).json()["stale_after_source_change"] is True

    c, h = session(app, "lim", "ENC-A1_1130")
    assert c.post(url(R.CLOSURE, encounter_id=A1), headers=h).json() == {"error_code": "closure_blocked"}
    t, th = session(app, "tan", "ENC-A1_1130")
    assert t.post(url(R.CLOSURE, encounter_id=A1), headers=th).json() == {"error_code": "forbidden_role"}
    alg = gflag("ENC-A1_1130", "ALG-001")
    pen = next(e for e in alg["evidence"] if e["role_in_flag"] == "counter_claim")
    ref = [{"note_version_id": pen["note_version_id"], "start": pen["start"], "end": pen["end"]}]
    assert decide(c, h, A1, alg["flag_id"], action="resolve", expected_revision=1, reason_code="allergy_entry_confirmed",
                  adjudicated_evidence=ref).status_code == 200
    cl = c.get(url(R.CLOSURE, encounter_id=A1), headers=h).json()
    assert [b["flag_id"] for b in cl["tier1_blockers"]] == [gflag("ENC-A1_1130", "CRIT-001")["flag_id"]]
    crit = gflag("ENC-A1_1130", "CRIT-001")["flag_id"]
    assert decide(c, h, A1, crit, action="dismiss", expected_revision=1,
                  reason_code="not_clinically_relevant").status_code == 200
    cl = c.get(url(R.CLOSURE, encounter_id=A1), headers=h).json()
    assert cl["status"] == "clear_with_open_tier2" and len(cl["decisions"]) == 2
    r = c.post(url(R.CLOSURE, encounter_id=A1), headers=h)
    assert r.json() == {"error_code": "closure_blocked"}  # 11:30 cutoff does not cover the 16:00 notes
    r = c.get(url(R.GLANCE, encounter_id=A1), headers=h)
    assert r.status_code == 501 and r.json() == {"error_code": "not_implemented"}  # stub engine: explicit, not stale


def test_decision_field_rules():
    """8.7 / L15 field rules. Mutations: accept any reassign target -> Dr Kaur becomes owner;
    skip the adjudication evidence check -> resolve without naming the correct entry succeeds."""
    app = real_app()
    c, h = session(app, "lim", "ENC-A1_1130")
    dose, alg, pend = (gflag("ENC-A1_1130", r)["flag_id"] for r in ("DOSE-001", "ALG-001", "PEND-001"))

    def err(fid, **body):
        return decide(c, h, A1, fid, expected_revision=body.pop("rev", 1), **body).json().get("error_code")

    assert err(dose, action="reassign", new_owner_staff_id=staff_id("ong")) == "rationale_required"
    assert err(dose, action="reassign", new_owner_staff_id=staff_id("kaur"), rationale_text="r") == "reassign_target_invalid"
    assert err(alg, action="reassign", new_owner_staff_id=staff_id("tan"), rationale_text="r") == "reassign_target_invalid"
    assert err(dose, action="mark_ready_for_clinician") == "validation_failed"
    assert err(dose, action="accept", reason_code="not_clinically_relevant") == "reason_code_not_allowed"
    assert err(dose, action="resolve", reason_code="owner_and_timing_documented") == "reason_code_not_allowed"
    assert err(alg, action="resolve", reason_code="allergy_entry_confirmed") == "adjudication_required"
    assert err(alg, action="resolve", reason_code="allergy_entry_confirmed",
               adjudicated_evidence=[{"note_version_id": ids.new_id(), "start": 0, "end": 4}]) == "validation_failed"
    assert err(dose, action="dismiss", reason_code="duplicate_of") == "validation_failed"
    assert err(dose, action="edit", rationale_text="r") == "validation_failed"  # edit needs edit_field
    r = decide(c, h, A1, dose, action="reassign", expected_revision=1, new_owner_staff_id=staff_id("ong"),
               rationale_text="pharmacy to reconcile")
    assert r.status_code == 200
    f = r.json()["flag"]
    assert (f["owner_staff_id"], f["state"], f["revision"]) == (staff_id("ong"), "edited", 2)
    assert r.json()["revisions"][-1]["decision_id"] == r.json()["decisions"][-1]["decision_id"]
    assert decide(c, h, A1, pend, action="dismiss", expected_revision=1,
                  reason_code="not_clinically_relevant").status_code == 200
    assert err(pend, action="accept", rev=2) == "invalid_transition"
    stale = decide(c, h, A1, pend, action="accept", expected_revision=1).json()
    assert stale["error_code"] == "stale_revision" and stale["last_decision_at"] and stale["current_state"] == "dismissed"
    rejected = [e for e in app.state.audit.events() if e.action.value == "decision_rejected"]
    assert len(rejected) >= 11 and all(e.target_id in (dose, alg, pend) for e in rejected)
    o, oh = session(app, "ong", "ENC-A1_1130")  # own workspace: Ong is a member, not the owner, not the RC
    assert decide(o, oh, A1, dose, action="resolve", expected_revision=1,
                  reason_code="dose_entry_current").json() == {"error_code": "forbidden_role"}


def test_cutoff_moves_forward_only():
    c, h = session(real_app(), "lim", "ENC-A1_1600")
    assert run_cutoff(c, h, A1, "ENC-A1_1130").json() == {"error_code": "validation_failed"}
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert c.post(url(R.CHECK_RUNS, encounter_id=A1), headers=h, json={"cutoff": future}).status_code == 422


class _AutoClosingEngine(StubEngine):
    def run_checks(self, snapshot, bundle, cutoff, *, run_id, evaluated_at):
        r = super().run_checks(snapshot, bundle, cutoff, run_id=run_id, evaluated_at=evaluated_at)
        return r.model_copy(update={"flags": tuple(f.model_copy(update={"state": FlagState.DISMISSED})
                                                   if f.rule_id.value == "ALG-001" else f for f in r.flags)})


class _DroppingEngine(StubEngine):
    def run_checks(self, snapshot, bundle, cutoff, *, run_id, evaluated_at):
        r = super().run_checks(snapshot, bundle, cutoff, run_id=run_id, evaluated_at=evaluated_at)
        return r.model_copy(update={"flags": r.flags[1:]}) if snapshot.prior_flags else r


def test_engine_contract_guard():
    """No Tier 1 closes automatically, even if an engine tried: the API refuses to commit a run that
    moves a flag into a human-only state or silently drops a known flag. Mutation (applied):
    remove _guard_engine_result -> the auto-dismissed ALG-001 is committed."""
    c, h = session(create_app(engine=_AutoClosingEngine(), bundle_loader=lambda: None), "lim")
    assert run_cutoff(c, h, A1, "ENC-A1_1130").json() == {"error_code": "internal_error"}
    assert c.get(url(R.FLAGS, encounter_id=A1), headers=h).status_code == 404  # nothing committed
    c, h = session(create_app(engine=_DroppingEngine(), bundle_loader=lambda: None), "lim", "ENC-A1_1130")
    assert run_cutoff(c, h, A1, "ENC-A1_1600_rerun").json() == {"error_code": "internal_error"}
    assert len(c.get(url(R.FLAGS, encounter_id=A1), headers=h).json()) == 4
    c, h = session(create_app(engine=StubEngine()), "lim")  # real engine without the B4 loader: explicit 501
    assert run_cutoff(c, h, A1, "ENC-A1_1130").json() == {"error_code": "not_implemented"}


def test_feedback_capture():
    """FeedbackEvent (B4 consumes): one per decision, plus usefulness feedback on a decided flag."""
    app = real_app()
    c, h = session(app, "lim", "ENC-A1_1130")
    dose = gflag("ENC-A1_1130", "DOSE-001")["flag_id"]
    fb = lambda **b: c.post(url(R.FEEDBACK, encounter_id=A1), headers=h, json=dict(flag_id=dose, **b))  # noqa: E731
    assert fb(usefulness="useful").json() == {"error_code": "invalid_transition"}  # nothing decided yet
    assert decide(c, h, A1, dose, action="accept", expected_revision=1).status_code == 200
    r = fb(usefulness="wrong_owner", time_on_screen_ms=4200, corrected_owner_staff_id=staff_id("ong"))
    assert r.status_code == 201
    ev = r.json()
    assert (ev["action"], ev["rule_id"], ev["rule_version"], ev["ruleset_version"]) == ("accept", "DOSE-001", 1, "v1")
    assert fb(usefulness="useful", corrected_owner_staff_id=staff_id("kaur")).json() == {"error_code": "reassign_target_invalid"}
    from tests.api.helpers import ctx_of
    events = app.state.store.feedback_events(ctx_of(app, c, h), A1)
    assert [getattr(e.usefulness, "value", None) for e in events] == [None, "wrong_owner"]
    assert [e.action.value for e in events] == ["accept", "accept"]


def test_concurrent_decisions_have_one_winner(monkeypatch):
    """Six simultaneous accepts with the same expected_revision: exactly one 200, five 409s,
    one decision recorded. The transition lookup (inside the critical section, between the
    revision check and the write) is slowed so a missing lock reliably double-applies: without
    this widening, removing the lock was caught 0/5 times in B2.2's check; with it, 5/5.
    Mutation (applied): drop the store lock around decide() -> several 200s."""
    import threading
    import time

    from noteguard.contracts import states

    real_target = states.decision_target

    def slow_target(action, state):
        time.sleep(0.01)
        return real_target(action, state)

    monkeypatch.setattr(states, "decision_target", slow_target)
    for _ in range(3):
        c, h = session(real_app(), "lim", "ENC-A1_1130")
        fid = gflag("ENC-A1_1130", "DOSE-001")["flag_id"]
        barrier, codes = threading.Barrier(6), []

        def go():
            barrier.wait()
            codes.append(decide(c, h, A1, fid, action="accept", expected_revision=1).status_code)

        threads = [threading.Thread(target=go) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(codes) == [200, 409, 409, 409, 409, 409]
        d = c.get(url(R.FLAG, encounter_id=A1, flag_id=fid), headers=h).json()
        assert d["flag"]["revision"] == 2 and len(d["decisions"]) == 1


def test_unhandled_exception_is_bare_500(caplog, capsys):
    """An unexpected exception (whose message may carry content) ends as a bare 500 with no-store;
    no traceback, message or input reaches a log. Mutation (applied): re-raise in
    request_middleware -> the exception escapes."""
    app = real_app()
    caplog.set_level(logging.DEBUG)
    c, h = session(app, "lim")

    def boom(*args, **kwargs):
        raise ValueError(f"note text {MARKER}")

    app.state.store.list_encounters = boom
    r = c.get(R.ENCOUNTERS, headers=h)
    assert r.status_code == 500 and r.json() == {"error_code": "internal_error"}
    assert "no-store" in r.headers["cache-control"]
    out = capsys.readouterr()
    logged = "\n".join(f"{rec.getMessage()} {rec.exc_info!r}" for rec in caplog.records) + out.out + out.err
    assert MARKER not in logged and "Traceback" not in logged


# --- sessions, workspaces, aggregate hand-off -------------------------------------------

def test_session_and_workspace_isolation():
    """Mutations: use the staff id as the session cookie (the B0 stub scheme) -> forged cookie
    works; skip the workspace owner check -> Nurse Tan uses Dr Lim's workspace."""
    app = real_app()
    c = client(app)
    r = c.post(R.SESSION, json={"staff_id": staff_id("lim")})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/api" in cookie
    token = re.search(r"ng_session=([^;]+)", r.headers["set-cookie"]).group(1)
    assert token != staff_id("lim")
    forged = client(app).get(R.SESSION, headers={"cookie": f"ng_session={staff_id('lim')}"})
    assert forged.json() == {"error_code": "unauthenticated"}
    ws = c.post(R.WORKSPACES).json()
    assert set(ws["encounter_ids"]) == {A1, C1} and ws["single_process_store"] is True
    assert "x-workspace-token" not in {k.lower() for k in c.cookies.keys()}
    h = {R.WORKSPACE_HEADER: ws["workspace_token"]}
    assert c.get(R.ENCOUNTERS).json() == {"error_code": "workspace_required"}
    t, th = session(app, "tan")
    assert t.get(R.ENCOUNTERS, headers=h).json() == {"error_code": "workspace_required"}  # not Tan's workspace
    assert set(session(app, "kaur")[0].post(R.WORKSPACES).json()["encounter_ids"]) == set()
    assert set(session(app, "wong")[0].post(R.WORKSPACES).json()["encounter_ids"]) == {B1}
    assert t.delete(R.WORKSPACE_CURRENT, headers=th).status_code == 204
    assert t.get(R.ENCOUNTERS, headers=th).json() == {"error_code": "workspace_required"}
    s, sh = session(app, "siti")
    assert s.delete(R.WORKSPACE_CURRENT, headers=sh).json() == {"error_code": "forbidden_role"}  # matrix: members only
    assert c.delete(R.SESSION).status_code == 204
    assert client(app).get(R.SESSION, headers={"cookie": f"ng_session={token}"}).status_code == 401  # revoked server-side
    assert client(app).post(R.SESSION, json={"staff_id": "no-such-staff"}).status_code == 401


def test_aggregate_rows_seam_for_b4():
    """B4's data seam: aggregate roles only (store layer), no ids of any kind, no text.
    Mutation (applied): drop the role check in aggregate_rows -> Dr Lim gets rows."""
    import dataclasses

    from noteguard.api.errors import ApiError
    from noteguard.contracts.errors import ErrorCode

    app = real_app()
    store = app.state.store
    c, h = session(app, "lim", "ENC-A1_1130")
    assert decide(c, h, A1, gflag("ENC-A1_1130", "DOSE-001")["flag_id"], action="accept",
                  expected_revision=1).status_code == 200
    staff = {k: store.staff_for_session(session(app, k)[0].cookies.get(R.SESSION_COOKIE)) for k in ("rao", "lim", "siti")}
    for k in ("lim", "siti"):
        with pytest.raises(ApiError) as exc:
            store.aggregate_rows(staff[k])
        assert exc.value.code is ErrorCode.FORBIDDEN_ROLE, k
    rows = store.aggregate_rows(staff["rao"])
    assert sorted(r.rule_id.value for r in rows) == sorted(f["rule_id"] for f in load("ENC-A1_1130")["flags"])
    dose = next(r for r in rows if r.rule_id.value == "DOSE-001")
    assert dose.disposition.value == "accept" and dose.first_decision_at is not None and dose.owner_role.value == "clinician"
    dumped = json.dumps([dataclasses.asdict(r) for r in rows], default=str)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-|flg_|bbl_", dumped)  # no staff, flag, encounter or patient ids
    assert set(dataclasses.asdict(rows[0])) == {"rule_id", "tier", "state", "created_at", "owner_role",
                                                "first_decision_at", "disposition"}
    reads = [e for e in app.state.audit.events() if e.action.value == "aggregate_read"]
    assert [e.outcome.value for e in reads] == ["denied", "denied", "success"]


def test_aggregate_route_is_b4_placeholder_behind_b2_authz():
    app = real_app()
    assert client(app).get(R.AGGREGATE).status_code == 401
    assert session(app, "lim")[0].get(R.AGGREGATE).json() == {"error_code": "forbidden_role"}
    r = session(app, "rao")[0].get(R.AGGREGATE)
    assert r.status_code == 501 and r.json() == {"error_code": "not_implemented"}
    assert client(app).get(R.AI_STATUS).json() == {"status": "disabled", "detail": "AI drafting disabled"}


# --- logs, markers, redaction (Section 10.3, 10.4) ----------------------------------------

def test_marker_never_logged_or_echoed(caplog, capsys):
    """Markers in body, header, query string, path, cookie, a malformed request, a login, a
    decision rationale and a PDF (text layer, title, filename). None may reach a log record,
    stdout/stderr, an error body or an audit event. Mutation (applied): log the raw request path
    in request_middleware -> fails."""
    app = real_app()
    caplog.set_level(logging.DEBUG)
    c, h = session(app, "lim", "ENC-A1_1130")
    hx = {**h, "X-Debug-Note": MARKER}
    c.cookies.set("trace", MARKER)
    rs = [
        c.post(url(R.SOURCES, encounter_id=A1), headers=hx, params={"q": MARKER},
               json=note(text=f"Review {MARKER}. NRIC {FAKE_NRIC}. Potassium 6.4 mmol/L.")),
        c.post(url(R.SOURCES, encounter_id=A1), headers={**h, "content-type": "application/json"},
               content=b'{"text": "' + MARKER.encode() + b'", '),
        c.get(f"/api/encounters/{MARKER}/flags", headers=h),
        c.get(url(R.FLAG, encounter_id=A1, flag_id=MARKER), headers=h),
        c.post(url(R.CHECK_RUNS, encounter_id=A1), headers=h, json={"cutoff": MARKER}),
        decide(c, h, A1, gflag("ENC-A1_1130", "DOSE-001")["flag_id"], action="edit", expected_revision=1,
               edit_field="explanation", rationale_text=f"{MARKER} {FAKE_NRIC}"),
        decide(c, h, A1, gflag("ENC-A1_1130", "ALG-001")["flag_id"], action=MARKER, expected_revision=1),
        client(app).post(R.SESSION, json={"staff_id": MARKER}),
        upload_pdf(c, h, A1, make_pdf([f"Lab ref {MARKER} NRIC {FAKE_NRIC}"]), title=f"Scan {MARKER}",
                   filename=f"{MARKER}.pdf"),
        upload_pdf(c, h, A1, MARKER.encode(), filename=f"{MARKER}.pdf"),
    ]
    assert [r.status_code for r in rs] == [201, 422, 404, 404, 422, 200, 422, 401, 201, 415]
    pdf_text = c.get(url(R.SOURCE_TEXT, encounter_id=A1, source_version_id=rs[8].json()["note_version_id"]), headers=h)
    assert MARKER in pdf_text.json()["text"]  # the marker really went through extraction
    errors = [r.text for r in rs if r.status_code >= 400]
    out = capsys.readouterr()
    logged = "\n".join(f"{rec.getMessage()} {rec.__dict__!r}" for rec in caplog.records) + out.out + out.err
    audit = json.dumps([e.model_dump(mode="json") for e in app.state.audit.events()])
    for secret in (MARKER, FAKE_NRIC):
        assert secret not in logged and secret not in audit and not any(secret in e for e in errors), secret


def test_request_log_uses_route_template_and_access_log_is_off(caplog):
    app = real_app()
    caplog.set_level(logging.DEBUG)
    c, h = session(app, "lim")
    c.get(url(R.ENCOUNTER, encounter_id=A1), headers=h, params={"x": "1"})
    recs = [json.loads(r.getMessage()) for r in caplog.records if r.name == "noteguard"]
    req = [r for r in recs if r["event"] == "http_request" and r.get("route_template") == R.ENCOUNTER]
    assert req and req[-1]["status_code"] == 200 and req[-1]["actor_id"] == staff_id("lim") and "workspace_hash" in req[-1]
    assert logging.getLogger("uvicorn.access").disabled
    assert all(logging.getLogger(n).getEffectiveLevel() >= logging.WARNING for n in ("httpx", "pdfminer", "python_multipart"))


def test_redaction_offsets_residual_scan_and_eval():
    """Offsets are code points into the ORIGINAL (CJK, emoji, diacritics); unknown long digit runs
    fail closed; eval set measured both ways. Mutation (applied): disable the residual scan ->
    the accession-number case is qualified for egress."""
    from noteguard.redaction import get_redactor, prepare_egress
    from noteguard.redaction.evaluate import evaluate

    red = get_redactor(["Siti Aminah"])
    text = "病人 😀 Puan siti aminah (anak), ñ Dr Lim, NRIC S0000001I, tel +65 9123 4567, a@b.sg."
    report = red.redact(text)
    kinds = sorted(s.kind.value for s in report.spans)
    assert kinds == ["email", "nric_fin", "person_name", "person_name", "phone"]
    for s in report.spans:
        assert report.redacted_text[s.redacted_start:s.redacted_end] == s.token
    assert [text[s.original_start:s.original_end] for s in report.spans] == [
        "siti aminah", "Dr Lim", "S0000001I", "+65 9123 4567", "a@b.sg"]
    assert report.original_sha256 == ids.sha256_hex(text) and "病人 😀" in report.redacted_text
    assert prepare_egress(text, redactor=red).text == report.redacted_text
    residual = red.redact("Accession 20260921001 pending review.")
    assert residual.status == "failed" and not residual.remote_egress_allowed
    with pytest.raises(ValueError):
        prepare_egress("Accession 20260921001 pending review.", redactor=red)
    assert red.redact("Potassium 6.4 mmol/L.").status == "nothing_to_redact"
    # Measured on a SELF-WRITTEN 10-item set (not independent evidence); the two known failures are
    # labelled in the set: lower-case "dr lim" (not redacted) and "Nurse Led Clinic" (over-redacted).
    assert evaluate() == dict(items=10, identifiers=19, not_redacted=1, keep=19, over_redacted=1, egress_refused=0)


# --- L11: every config key changes behaviour ----------------------------------------------

def _session_effect(app) -> int:
    r = client(app).post(R.SESSION, json={"staff_id": staff_id("lim")})
    token = re.search(r"ng_session=([^;]+)", r.headers["set-cookie"]).group(1)
    return client(app).get(R.SESSION, headers={"cookie": f"ng_session={token}"}).status_code


def _workspace_effect(app) -> int:
    c, h = session(app, "lim")
    return c.get(R.ENCOUNTERS, headers=h).status_code


def _scan_upload_effect(app) -> int:
    c, h = session(app, "lim")
    return upload_pdf(c, h, A1, SCAN.read_bytes()).status_code


#: 45 text pages: extraction takes far longer than a zero timeout, so the race is not close
#: (a 1-page scan lost it 1 time in 60 during B2.2's stress check).
SLOW_PDF = make_pdf([f"Page {n} potassium 5.1 mmol/L reviewed" for n in range(1, 46)])


def _timeout_effect(app) -> tuple[int, str]:
    c, h = session(app, "lim")
    r = upload_pdf(c, h, A1, SLOW_PDF, title="Timed scan")
    kept = [s for s in sources(c, h, A1) if s["title"] == "Timed scan"]
    return r.status_code, kept[0]["extraction_status"] if kept else "not retained"


def _document_effect(app) -> int:
    c, h = session(app, "lim")
    scan = version_with_status(c, h, A1, "no_text_layer")
    tok = c.post(url(R.DOCUMENT_TOKEN, encounter_id=A1, source_version_id=scan), headers=h).json()["document_token"]
    return c.get(url(R.DOCUMENT, document_token=tok)).status_code


#: key -> (changed value, observation, default outcome, changed outcome)
CONFIG_EFFECTS = {
    "session_ttl_s": (0, _session_effect, 200, 401),
    "workspace_ttl_s": (0, _workspace_effect, 200, 410),
    "pdf_max_bytes": (100, _scan_upload_effect, 201, 413),
    "pdf_max_pages": (0, _scan_upload_effect, 201, 422),
    "pdf_extraction_timeout_s": (0.0, _timeout_effect, (201, "complete"), (422, "failed")),
    "document_token_ttl_s": (0, _document_effect, 200, 404),
}


@pytest.mark.parametrize("key", sorted(CONFIG_EFFECTS))
def test_config_key_changes_behaviour(key):
    """L11. Mutation (applied): hard-code the workspace TTL in the store -> the 410 step fails."""
    value, observe, default_out, changed_out = CONFIG_EFFECTS[key]
    assert observe(create_app()) == default_out
    assert observe(create_app(settings=Settings(**{key: value}))) == changed_out
