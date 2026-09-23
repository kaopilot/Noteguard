"""L13, protected floor, aggregate, AI gate. owner: B4. Interfaces inside noteguard/governance are
B4's to design; bodies marked not_implemented carry the specification in their docstring."""

import re

import pytest

from noteguard.contracts import routes as R
from tests.support.api import login
from tests.support.lanes import client, lane_module, not_implemented, real_app

pytestmark = [pytest.mark.owner("B4"), pytest.mark.governance]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def _approved_copy(tmp_path, **overrides):
    """A temporary rulesets dir holding the REAL v1 files and an approval record with their real
    hashes (status approved unless overridden). Never touches rulesets/."""
    import json
    import shutil

    from noteguard.contracts import ids
    from tests.support.golden import ROOT

    for name in ("v1.json", "registry_v1.json"):
        shutil.copy(ROOT / "rulesets" / name, tmp_path / name)
    rec = {"ruleset_version": "v1", "ruleset_sha256": ids.sha256_hex((tmp_path / "v1.json").read_bytes()),
           "registry_version": "v1", "registry_sha256": ids.sha256_hex((tmp_path / "registry_v1.json").read_bytes()),
           "evaluation_report_sha256": "e" * 64, "approver_role": "clinical_governance",
           "approver_label": "test approver", "approved_on": "2026-09-23", "status": "approved"} | overrides
    (tmp_path / "APPROVAL_v1.md").write_text(f"# test record\n\n```json\n{json.dumps(rec)}\n```\n", encoding="utf-8")
    return tmp_path


def test_no_runtime_rule_mutation(tmp_path):
    """L13: no route, config or feedback path changes a rule, threshold or weight at runtime;
    the loaded bundle is immutable and its sha256 equals the approved record's.

    Applied input: the real app with the real engine and the approval-checked loader; run checks,
    decide (accept + dismiss), send usefulness feedback repeatedly, rerun. Observed: the ruleset
    files, every bundle object handed to the engine, and the flags the rules produce are unchanged.
    Mutations (applied, decisions/B4.md): (a) make the feedback route edit
    ``load_bundle().registry.cues`` in place -> the spy's content hash differs; (b) make the loader
    cache its bundle and a feedback path disable a rule -> the rerun flag set differs."""
    import ast

    from noteguard.api.app import create_app
    from noteguard.contracts import ids
    from noteguard.engine import get_engine
    from noteguard.governance import approval
    from tests.support.api import A1, run_cutoff, url
    from tests.support.golden import ROOT

    d = _approved_copy(tmp_path)
    files_before = {p.name: ids.sha256_hex(p.read_bytes()) for p in d.glob("*.json")}
    record = approval.parse_approval_record(d / "APPROVAL_v1.md")
    reference = approval.bundle_content_sha256(approval.load_pinned("v1", d))
    handed_out = []
    real_loader = approval.api_bundle_loader("v1", d)

    def spy():
        b = real_loader()
        handed_out.append(b)
        return b

    app = create_app(engine=get_engine(), bundle_loader=spy)
    c = client(app)
    h = login(c, "lim")

    def rule_view():
        return sorted((f["rule_id"], f["subject_key"], f["tier"]) for f in c.get(url(R.FLAGS, encounter_id=A1), headers=h).json())

    assert run_cutoff(c, h, A1, "ENC-A1_1130").status_code == 200
    before = rule_view()
    assert before, "the engine raised no flags: the test would observe nothing"
    flags = {f["rule_id"]: f for f in c.get(url(R.FLAGS, encounter_id=A1), headers=h).json()}
    dec = url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=flags["DOSE-001"]["flag_id"])
    assert c.post(dec, headers=h, json={"action": "accept", "expected_revision": flags["DOSE-001"]["revision"]}).status_code == 200
    dec = url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=flags["PEND-001"]["flag_id"])
    assert c.post(dec, headers=h, json={"action": "dismiss", "reason_code": "not_clinically_relevant",
                                        "expected_revision": flags["PEND-001"]["revision"]}).status_code == 200
    for usefulness in ("not_useful", "not_useful", "wrong_owner", "stale_wording", "not_useful"):
        for rule in ("DOSE-001", "PEND-001"):
            r = c.post(url(R.FEEDBACK, encounter_id=A1), headers=h,
                       json={"flag_id": flags[rule]["flag_id"], "usefulness": usefulness, "time_on_screen_ms": 300})
            assert r.status_code == 201, r.status_code
    assert run_cutoff(c, h, A1, "ENC-A1_1130").status_code == 200

    assert rule_view() == before  # feedback changed no rule behaviour
    assert {p.name: ids.sha256_hex(p.read_bytes()) for p in d.glob("*.json")} == files_before
    assert len(handed_out) >= 2
    for b in handed_out:  # no path edited a bundle in place
        assert approval.bundle_content_sha256(b) == reference
        assert (b.ruleset_sha256, b.registry_sha256) == (record.ruleset_sha256, record.registry_sha256)
    # Feedback is consumed offline only: the API never imports the proposal or evaluation tools.
    for p in (ROOT / "noteguard" / "api").rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                names = [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                continue
            assert not any(n.startswith(("noteguard.governance.propose", "noteguard.governance.evaluate"))
                           for n in names), p.name


def test_unapproved_ruleset_refused(tmp_path):
    """L13: a ruleset whose file hashes do not match an `approved` APPROVAL_*.md record is refused
    at load (rulesets/APPROVAL_v1.md is currently `draft`, so it must be refused today).

    Each refusal reason is isolated on a copy of the real files (exact code set), with a positive
    control so a loader that refuses everything fails. Through the API a refusal is a 503
    ``ruleset_unapproved`` and no flag is produced.
    Mutation (applied): drop the status check in approval.refusal_codes -> the draft case loads."""
    import json

    from noteguard.api.app import create_app
    from noteguard.engine import get_engine
    from noteguard.governance import approval as ap
    from tests.support.api import A1, run_cutoff
    from tests.support.golden import ROOT

    def codes(d):
        with pytest.raises(ap.RulesetRefused) as e:
            ap.load_pinned("v1", d)
        return set(e.value.codes)

    def fresh(name, **kw):
        sub = tmp_path / name
        sub.mkdir()
        return _approved_copy(sub, **kw)

    ok = ap.load_pinned("v1", fresh("ok"))  # positive control
    assert ok.ruleset.ruleset_version == "v1" and ok.ruleset.rules
    assert codes(fresh("draft", status="draft")) == {ap.NOT_APPROVED}
    assert codes(fresh("retired", status="retired")) == {ap.NOT_APPROVED}
    assert codes(fresh("noreport", evaluation_report_sha256=None)) == {ap.EVALUATION_REPORT_MISSING}
    d = fresh("rs_edit")
    rs = json.loads((d / "v1.json").read_text(encoding="utf-8"))
    next(r for r in rs["rules"] if r["rule_id"] == "CRIT-001")["enabled"] = False  # an unapproved edit
    (d / "v1.json").write_text(json.dumps(rs), encoding="utf-8")
    assert codes(d) == {ap.RULESET_HASH_MISMATCH}
    d = fresh("reg_edit")
    (d / "registry_v1.json").write_bytes((d / "registry_v1.json").read_bytes() + b"\n")
    assert codes(d) == {ap.REGISTRY_HASH_MISMATCH}
    assert codes(fresh("ver", ruleset_version="v9")) == {ap.VERSION_MISMATCH}
    d = fresh("twoblocks")
    (d / "APPROVAL_v1.md").write_text((d / "APPROVAL_v1.md").read_text() * 2, encoding="utf-8")
    assert codes(d) == {ap.APPROVAL_RECORD_INVALID}
    assert codes(tmp_path / "ok" / "missing") == {ap.APPROVAL_RECORD_MISSING}
    with pytest.raises(ap.RulesetRefused) as e:  # the pinned-version parameter is read (L11)
        ap.load_pinned("v2", tmp_path / "ok")
    assert e.value.codes == (ap.APPROVAL_RECORD_MISSING,)

    # The REAL pinned record: loadable iff approved, with a report hash and matching hashes
    # (today: draft, so refused; after @k's CP2 approval: loads). Oracle computed independently.
    real = ap.parse_approval_record(ROOT / "rulesets" / "APPROVAL_v1.md")
    from noteguard.contracts import ids
    authorised = (real.status.value == "approved" and real.evaluation_report_sha256 is not None
                  and ids.sha256_hex((ROOT / "rulesets" / "v1.json").read_bytes()) == real.ruleset_sha256
                  and ids.sha256_hex((ROOT / "rulesets" / "registry_v1.json").read_bytes()) == real.registry_sha256)
    if authorised:
        assert ap.load_pinned().ruleset_sha256 == real.ruleset_sha256
    else:
        codes(ROOT / "rulesets")  # refused

    # Through the API: refused ruleset -> 503 ruleset_unapproved, and no flags exist afterwards.
    app = create_app(engine=get_engine(), bundle_loader=ap.api_bundle_loader("v1", tmp_path / "draft"))
    c = client(app)
    h = login(c, "lim")
    r = run_cutoff(c, h, A1, "ENC-A1_1130")
    assert (r.status_code, r.json()) == (503, {"error_code": "ruleset_unapproved"})
    assert c.get(R.FLAGS.format(encounter_id=A1), headers=h).status_code == 404  # no run was committed


def _feedback(rule: str, n_flags: int, action: str, reason: str | None = None, *, usefulness=None, ms=None):
    """n_flags distinct flags of one rule, one decision event each (+ optional usefulness event)."""
    from datetime import datetime, timedelta, timezone

    from noteguard.contracts import ids
    from noteguard.contracts.types import FeedbackEvent

    t0 = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)
    out = []
    for i in range(n_flags):
        fid = ids.flag_id(rule, f"enc-{action}-{i}", f"subject-{rule}")  # distinct flag per call and index
        base = dict(flag_id=fid, rule_id=rule, rule_version=1, ruleset_version="v1", action=action,
                    reason_code=reason, actor_role="clinician")
        out.append(FeedbackEvent(feedback_id=f"fb-{rule}-{action}-{i}-d", at=t0 + timedelta(minutes=i), **base))
        if usefulness:
            out.append(FeedbackEvent(feedback_id=f"fb-{rule}-{action}-{i}-u", at=t0 + timedelta(minutes=i, seconds=30),
                                     usefulness=usefulness, time_on_screen_ms=ms, **base))
    return out


def test_protected_floor_refused():
    """propose.py refuses lower_tier / disable_rule / narrow_rule on protected_floor rules.

    Applied inputs: every reducing kind for every protected rule in the BASELINE ruleset (Tier 1 and
    DOSE-001/002, PDF-001), with positive controls on unprotected rules (a checker that refuses
    everything fails), and the feedback-driven path with noisy protected and noisy Tier 3 rules plus
    an unrelated quiet rule (shape adequacy, 12.1).
    Mutation (applied): make propose.is_protected return False -> fails."""
    from noteguard.contracts.types import ProposalKind as K
    from noteguard.contracts.types import RuleId
    from noteguard.governance import propose as pr
    from tests.support.golden import bundle

    b = bundle()
    rs, reg = b.ruleset, b.registry
    protected = [r.rule_id for r in rs.rules if r.protected_floor or r.default_tier == 1]
    assert {RuleId.CRIT_001, RuleId.ALG_001, RuleId.DOSE_002} <= set(protected)
    reducing = (K.LOWER_TIER, K.DISABLE_RULE, K.NARROW_RULE, K.RETIRE_TIER3_RULE, K.ADJUST_TIER3_THRESHOLD)
    subs = [pr.make_proposal(k, r, "v2", {}, "test", {"n": 1}) for r in protected for k in reducing]
    ok, refused = pr.submit(subs, rs, reg)
    assert not ok and {x.code for x in refused} == {pr.PROTECTED_FLOOR} and len(refused) == len(subs)

    # Positive controls: the same kinds on unprotected rules proceed to evaluation.
    controls = [pr.make_proposal(K.RETIRE_TIER3_RULE, RuleId.DIFF_001, "v2", {}, "test", {"n": 1}),
                pr.make_proposal(K.LOWER_TIER, RuleId.PEND_001, "v2", {}, "test", {"n": 1}),
                pr.make_proposal(K.ADD_SYNONYM, None, "v2", {"term_key": "drug:amlodipine", "synonym": "amlo"}, "t", {}),
                pr.make_proposal(K.ADD_SYNONYM, None, "v2", {"cue_kind": "pending", "phrase": "outstanding"}, "t", {}),
                pr.make_proposal(K.ADD_QUESTION_TEMPLATE, None, "v2", {"template_id": "q_new"}, "t", {})]
    ok, refused = pr.submit(controls, rs, reg)
    assert len(ok) == len(controls), [r.code for r in refused]
    # Other refusals: suppressing cue (shared with protected rules), same version, wrong tier, unknown term.
    others = {pr.NARROWS_SHARED_REGISTRY: pr.make_proposal(K.ADD_SYNONYM, None, "v2", {"cue_kind": "negation", "phrase": "nil"}, "t", {}),
              pr.SAME_VERSION: pr.make_proposal(K.RETIRE_TIER3_RULE, RuleId.DIFF_001, "v1", {}, "t", {}),
              pr.NOT_TIER3: pr.make_proposal(K.RETIRE_TIER3_RULE, RuleId.PEND_001, "v2", {}, "t", {}),
              pr.UNKNOWN_TERM: pr.make_proposal(K.ADD_SYNONYM, None, "v2", {"term_key": "drug:zzz", "synonym": "z"}, "t", {})}
    for code, p in others.items():
        assert pr.refusal_code(p, rs, reg) == code

    # Feedback-driven: ALG-001 (protected) and DIFF-001 (Tier 3) both dismissed 9/10; PEND-001 quiet.
    events = (_feedback("ALG-001", 9, "dismiss", "not_clinically_relevant", usefulness="not_useful", ms=900)
              + _feedback("ALG-001", 1, "accept") + _feedback("DIFF-001", 9, "dismiss", "extraction_error")
              + _feedback("DIFF-001", 1, "accept") + _feedback("PEND-001", 10, "accept", usefulness="useful", ms=8000))
    batch = pr.propose_from_feedback(events, rs, "v2", registry=reg)
    assert [(p.kind, p.rule_id) for p in batch.accepted] == [(K.RETIRE_TIER3_RULE, RuleId.DIFF_001)]
    assert [(r.proposal.kind, r.proposal.rule_id, r.code) for r in batch.refused] == [
        (K.NARROW_RULE, RuleId.ALG_001, pr.PROTECTED_FLOOR)]
    m = {x.rule_id: x for x in batch.metrics}
    alg = m[RuleId.ALG_001]  # dispositions per FLAG (usefulness events do not double-count)
    assert (alg.surfaced, alg.surfaced_basis, alg.dismissed, alg.rates["dismissal"]) == (10, "flags_with_feedback", 9, "9/10")
    assert (alg.rates["fast_decision_share"], m[RuleId.PEND_001].rates["fast_decision_share"]) == ("9/9", "0/10")
    # Denominator supplied (surfaced flags, incl. undecided ones) changes the rate and the outcome.
    batch = pr.propose_from_feedback(events, rs, "v2", surfaced={RuleId.DIFF_001: 40, RuleId.ALG_001: 10}, registry=reg)
    assert m[RuleId.DIFF_001].rates["dismissal"] == "9/10"
    assert {x.rule_id: x.rates["dismissal"] for x in batch.metrics}[RuleId.DIFF_001] == "9/40" and not batch.accepted
    # The threshold is read: above the sample size nothing is proposed or refused.
    batch = pr.propose_from_feedback(events, rs, "v2", min_surfaced=11, registry=reg)
    assert not batch.accepted and not batch.refused
    batch = pr.propose_from_feedback(events, rs, "v2", noisy_dismissal_rate=0.95, registry=reg)  # 9/10 < 0.95
    assert not batch.accepted and not batch.refused
    fast = {x.rule_id: x.rates["fast_decision_share"] for x in pr.rule_metrics(events, reading_floor_ms=500)}
    assert fast[RuleId.ALG_001] == "0/9"  # 900 ms is not below a 500 ms floor


def test_aggregate_no_content_or_ids():
    """Aggregate view: role-gated, no content, no patient/encounter ids, small cells '<5'.

    B4 strengthened the B0 body (all original assertions kept): the view is POPULATED by real check
    runs (an empty view would pass the content checks vacuously), first with one workspace (every
    cell "<5"), then with six (the Tier 1/2 cells become exact integers >= 5).
    Mutations (applied, decisions/B4.md): show small counts as integers -> fails; remove the
    store-layer role check in store.aggregate_rows (B2's second layer) -> fails; shift an age-bucket
    boundary -> fails."""
    from noteguard.api.errors import ApiError
    from noteguard.contracts.types import Staff
    from tests.support.api import A1, run_cutoff
    from tests.support.builders import AUTHOR

    app = real_app()
    koh = client(app)
    h = login(koh, "koh")  # quality & risk
    r = koh.get(R.AGGREGATE, headers=h)
    assert r.status_code == 200
    assert not UUID.search(r.text) and "flg_" not in r.text and "Potassium" not in r.text
    for cell in r.json()["cells"]:
        assert cell["count"] == "<5" or int(cell["count"]) >= 5
    lim = client(app)
    hl = login(lim, "lim")
    assert lim.get(R.AGGREGATE, headers=hl).status_code == 403
    assert client(app).get(R.AGGREGATE).status_code == 401

    # Populate: one clinician workspace with the 11:30 run -> every cell is a small cell.
    assert run_cutoff(lim, hl, A1, "ENC-A1_1130").status_code == 200
    r = koh.get(R.AGGREGATE, headers=h)
    body = r.json()
    assert r.status_code == 200 and "no-store" in r.headers.get("cache-control", "")
    assert body["cells"] and all(c["count"] == "<5" for c in body["cells"])
    assert body["ruleset_version"] == "v1" and body["small_cell_threshold"] == 5
    assert not UUID.search(r.text) and "flg_" not in r.text and "Potassium" not in r.text and "penicillin" not in r.text.lower()
    assert {tuple(sorted(c)) for c in body["cells"]} == {("age_bucket", "count", "rule_id", "state", "tier")}
    # Five more workspaces with the same run -> 6 copies per cell -> exact counts appear.
    for _ in range(5):
        c = client(app)
        hc = login(c, "lim")
        assert run_cutoff(c, hc, A1, "ENC-A1_1130").status_code == 200
    r = koh.get(R.AGGREGATE, headers=h)
    body = r.json()
    counts = {(c["rule_id"], c["state"]): c["count"] for c in body["cells"]}
    assert counts[("ALG-001", "open")] == "6" and counts[("CRIT-001", "open")] == "6"
    for cell in body["cells"]:
        assert cell["count"] == "<5" or int(cell["count"]) >= 5
    assert not UUID.search(r.text) and "flg_" not in r.text
    for key in ("mrn", "nric", "encounter_id", "patient", "staff_id", "quote", "reason", "title"):
        assert key not in r.text.lower()
    # The small-cell threshold is read (L11): six copies are "6" at 5 and "<7" at 7.
    from types import SimpleNamespace

    from noteguard.contracts.types import FlagState, RuleId, Tier
    from noteguard.governance.aggregate import build_view
    # Age buckets at their boundaries (upper bounds exclusive).
    from datetime import datetime, timedelta, timezone

    from noteguard.governance.aggregate import age_bucket
    t = datetime(2026, 9, 21, tzinfo=timezone.utc)
    assert [age_bucket(t, t + timedelta(hours=x)) for x in (0, 3.99, 4, 23.99, 24, 90)] == [
        "<4h", "<4h", "4-24h", "4-24h", ">24h", ">24h"]
    rows = [SimpleNamespace(rule_id=RuleId.ALG_001, tier=Tier.T1, state=FlagState.OPEN, created_at=t)] * 6
    assert [c.count for c in build_view(rows, now=t, ruleset_version="v1").cells] == ["6"]
    assert [c.count for c in build_view(rows, now=t, ruleset_version="v1", threshold=7).cells] == ["<7"]
    # Store layer refuses a clinician even with the route guard bypassed (second layer, B2's seam).
    lim_staff = Staff.model_validate(AUTHOR.staff_record("lim"))
    with pytest.raises(ApiError):
        app.state.store.aggregate_rows(lim_staff)


def test_ai_disabled_by_default():
    """L10 / OPEN-5: AI drafting is off unless configured; the UI copy says so."""
    c = client(real_app())
    login(c, "lim")
    r = c.get(R.AI_STATUS)
    assert r.status_code == 200 and r.json() == {"status": "disabled", "detail": "AI drafting disabled"}


class _Provider:
    """Test double at the provider boundary: honours the contract (assert_qualified first) and records
    what it received. It never reports a result it did not produce."""

    def __init__(self, reply="", exc=None, gate=None):
        self.reply, self.exc, self.gate, self.calls = reply, exc, gate, []

    def draft(self, payload, *, timeout_s):
        payload.assert_qualified()
        self.calls.append(payload.text)
        if self.gate is not None:
            self.gate.wait(3)
        if self.exc is not None:
            raise self.exc
        return self.reply


def _ai_fixture():
    from noteguard.contracts.types import Flag
    from noteguard.governance import ai_drafting as ai
    from tests.support.golden import bundle, load

    flags = {f["rule_id"]: Flag.model_validate(f) for f in load("ENC-A1_1130")["flags"]}
    return ai, flags, bundle().registry


def _with_quote(flag, match, new_quote):
    from noteguard.contracts import ids

    ev = tuple(e.model_copy(update={"quote": new_quote, "quote_sha256": ids.quote_sha256(new_quote)})
               if match in e.quote.lower() else e for e in flag.evidence)
    return flag.model_copy(update={"evidence": ev})


def _ids(ai, flag, *needles):
    cl = ai.build_cluster(flag)
    return [next(e.evidence_id for e in cl if n in e.quote.lower()) for n in needles]


def test_ai_timeout_falls_back():
    """Section 9: a provider that exceeds the timeout (or raises 5xx) yields the deterministic rule
    text labelled 'AI drafting unavailable; showing rule explanation'; the workflow is not blocked.

    Also: off by default (no provider call, no egress); enabled requires a real provider; only a
    QualifiedRedactedText reaches the provider (a synthetic NRIC in a quote never does); the breaker
    opens after consecutive failures and closes after the cooldown; a valid draft is VALIDATED
    (positive control). Mutation (applied): call future.result() without the timeout -> fails."""
    import json
    import threading
    import time as _t

    ai, flags, reg = _ai_fixture()
    alg = flags["ALG-001"]
    nkda, pen = _ids(ai, alg, "nkda", "penicillin")
    good = json.dumps({"sentences": [{"text": "One source records NKDA and another records a penicillin allergy.",
                                      "evidence_ids": [nkda, pen]}]})
    egress_calls = []

    def spy_factory(names):
        from noteguard.redaction import get_redactor
        egress_calls.append(tuple(names))
        return get_redactor(names)

    # Off by default: nothing is sent anywhere, the rule text is shown, status says disabled.
    prov = _Provider(reply=good)
    d = ai.Drafter(provider=prov, redactor_factory=spy_factory)
    r = d.draft(alg, reg)
    assert (r.status.value, r.text, r.detail) == ("disabled", alg.reason, "AI drafting disabled")
    assert prov.calls == [] and egress_calls == []
    assert ai.Drafter().status_view().model_dump(mode="json") == {"status": "disabled", "detail": "AI drafting disabled"}
    with pytest.raises(ValueError):
        ai.Drafter(config=ai.AIConfig(enabled=True))  # never a stand-in provider

    # Positive control + egress: validated, and the provider saw only redacted, qualified text.
    marked = _with_quote(alg, "penicillin", "Penicillin allergy - rash (per GP records) NRIC S0000001Z")
    prov = _Provider(reply=good)
    d = ai.Drafter(config=ai.AIConfig(enabled=True), provider=prov, redactor_factory=spy_factory)
    r = d.draft(marked, reg, known_names=["Pharmacist Ong"])
    assert r.status.value == "validated" and set(r.cited_evidence_ids) == {nkda, pen}
    assert len(prov.calls) == 1 and "S0000001Z" not in prov.calls[0] and "[NRIC_FIN_1]" in prov.calls[0]
    assert egress_calls[-1] == ("Pharmacist Ong",)

    # Timeout: bounded wait, rule text, exact label; the workflow is not blocked.
    gate = threading.Event()
    slow = _Provider(reply=good, gate=gate)
    d = ai.Drafter(config=ai.AIConfig(enabled=True, timeout_s=0.1), provider=slow)
    t0 = _t.perf_counter()
    r = d.draft(alg, reg)
    elapsed = _t.perf_counter() - t0
    gate.set()
    assert (r.status.value, r.text, r.detail, r.code) == (
        "unavailable_fallback", alg.reason, "AI drafting unavailable; showing rule explanation", ai.TIMEOUT)
    assert elapsed < 1.0, elapsed
    # 5xx / any provider exception.
    d = ai.Drafter(config=ai.AIConfig(enabled=True), provider=_Provider(exc=RuntimeError("503")))
    r = d.draft(alg, reg)
    assert (r.status.value, r.text, r.code) == ("unavailable_fallback", alg.reason, ai.PROVIDER_ERROR)

    # Circuit breaker: two failures open it; the provider is not called while open; cooldown closes it.
    now = [1000.0]
    failing = _Provider(exc=RuntimeError("502"))
    d = ai.Drafter(config=ai.AIConfig(enabled=True, breaker_failures=2, breaker_cooldown_s=60), provider=failing,
                   clock=lambda: now[0])
    assert [d.draft(alg, reg).code for _ in range(3)] == [ai.PROVIDER_ERROR, ai.PROVIDER_ERROR, ai.CIRCUIT_OPEN]
    assert len(failing.calls) == 2 and d.status_view().status.value == "unavailable_fallback"
    now[0] += 61
    d.provider = _Provider(reply=good)
    assert d.draft(alg, reg).status.value == "validated" and d.status_view().status.value == "validated"


def test_ai_output_validator_rejects_new_entity():
    """Section 9: output naming a registry entity absent from the evidence cluster, lacking evidence
    ids, raising certainty, containing a forbidden phrase, or carrying tier/owner/state is discarded.

    Each failure mode is applied alone next to a passing control on the same cluster, and one goes
    through the Drafter end to end (REJECTED_FALLBACK with the rule text).
    Mutations (applied): drop the entity check -> fails; drop the certainty check -> fails."""
    import json

    ai, flags, reg = _ai_fixture()
    alg, dose = flags["ALG-001"], flags["DOSE-001"]
    nkda, pen = _ids(ai, alg, "nkda", "penicillin")
    cl = ai.build_cluster(alg)

    def out(*items, **top):
        return json.dumps({"sentences": [{"text": t, "evidence_ids": e} for t, e in items]} | top)

    def code(raw, cluster=cl):
        return ai.validate_output(raw, cluster, reg)[1]

    assert code(out(("One source records NKDA and another records a penicillin allergy.", [nkda, pen]))) is None
    cases = {
        ai.ENTITY_NOT_IN_EVIDENCE: out(("The patient also takes metformin.", [nkda])),
        ai.MISSING_EVIDENCE_IDS: out(("Another source records a penicillin allergy.", [])),
        ai.UNKNOWN_EVIDENCE_ID: out(("Another source records a penicillin allergy.", ["E9"])),
        ai.FORBIDDEN_PHRASE: out(("The allergy check was not done.", [pen])),
        ai.POLARITY_UNSUPPORTED: out(("There is no penicillin allergy.", [pen])),
        ai.SCHEMA_INVALID: "Penicillin allergy recorded.",
    }
    for field in ("tier", "owner_staff_id", "state"):
        assert code(out(("A penicillin allergy is recorded.", [pen]), **{field: "x"})) == ai.EXTRA_FIELD, field
    assert code(json.dumps({"sentences": [{"text": "A penicillin allergy is recorded.", "evidence_ids": [pen],
                                           "owner": "x"}]})) == ai.EXTRA_FIELD
    for expected, raw in cases.items():
        assert code(raw) == expected, expected
    # Certainty: a hedged source cannot become a plain statement; a hedged draft passes.
    hedged = _with_quote(alg, "penicillin", "Query penicillin allergy - rash")
    hcl = ai.build_cluster(hedged)
    hpen = next(e.evidence_id for e in hcl if "penicillin" in e.quote.lower())
    assert code(out(("A penicillin allergy with rash is recorded.", [hpen])), hcl) == ai.CERTAINTY_RAISED
    assert code(out(("A possible penicillin allergy is recorded.", [hpen])), hcl) is None
    # Doses must appear in the cited evidence.
    dcl = ai.build_cluster(dose)
    both = [e.evidence_id for e in dcl]
    assert code(out(("Amlodipine 5 mg and 10 mg are recorded in different sources.", both)), dcl) is None
    assert code(out(("Amlodipine 20 mg is recorded.", both)), dcl) == ai.DOSE_NOT_IN_EVIDENCE
    # A tampered quote (hash mismatch) is not a verified cluster.
    bad = alg.model_copy(update={"evidence": tuple(e.model_copy(update={"quote": e.quote + " x"}) for e in alg.evidence)})
    with pytest.raises(ValueError):
        ai.build_cluster(bad)

    # End to end: the provider outputs a drug not in the cluster -> discarded, rule text shown.
    d = ai.Drafter(config=ai.AIConfig(enabled=True), provider=_Provider(reply=cases[ai.ENTITY_NOT_IN_EVIDENCE]))
    r = d.draft(alg, reg)
    assert (r.status.value, r.text, r.code) == ("rejected_fallback", alg.reason, ai.ENTITY_NOT_IN_EVIDENCE)
    assert d.status_view().status.value == "rejected_fallback"


def test_eval_report_tier1_recall_gate():
    """evaluate.py reports per-rule counts with denominators and fails the gate if Tier 1 recall
    on the labelled fixtures drops below 1.0.

    Applied inputs (real engine, fixtures/labelled_eval + golden scenarios): v1 vs v1; a benign
    candidate (positive control); an engine wrapper that drops CRIT-001 for the candidate only (recall
    reasons isolated from the static floor); a candidate lowering ALG-001's tier; a candidate that
    disables CRIT-001; a candidate extending a suppressing cue (floor only).
    Mutations (applied, decisions/B4.md): drop the tier comparison in evaluate._tier1 -> the ALG-001
    case passes the gate; drop the suppressing-cue floor check -> the negation case passes."""
    from noteguard.contracts.types import CueKind, RuleId, Tier
    from noteguard.governance import evaluate as ev
    from noteguard.governance import labelled

    v1 = ev.bundle_from_files(ev.ROOT / "rulesets" / "v1.json", ev.ROOT / "rulesets" / "registry_v1.json")
    cases = labelled.load_cases() + labelled.load_golden()
    assert {c.part for c in cases} == {"b4_labelled", "golden", "known_limit"}

    def with_rule(rule_id, **upd):
        rules = tuple(r.model_copy(update=upd) if r.rule_id is rule_id else r for r in v1.ruleset.rules)
        return v1.model_copy(update={"ruleset": v1.ruleset.model_copy(update={"rules": rules})})

    def with_cue(kind, phrase):
        cues = dict(v1.registry.cues) | {kind: tuple(v1.registry.cues.get(kind, ())) + (phrase,)}
        return v1.model_copy(update={"registry": v1.registry.model_copy(update={"cues": cues})})

    base = ev.evaluate(v1, v1, cases=cases)
    assert base["gate"] == {"passed": True, "reasons": []}
    t1 = base["candidate"]["tier1_recall"]
    n, d = map(int, t1.split("/"))
    assert n == d >= 10, t1  # Tier 1 recall 1.0 on at least ten Tier 1 labels
    rows = {r["rule_id"]: r for r in base["candidate"]["per_rule"]["b4_labelled"]}
    for rid in ("CRIT-001", "ALG-001", "DET-001", "OWN-001"):
        r = rows[rid]
        assert r["labelled"] >= 1 and r["recall"] == f"{r['tp']}/{r['labelled']}" and r["precision"] == f"{r['tp']}/{r['raised']}"
        assert r["tp"] + r["fn"] == r["labelled"] and r["tp"] + r["fp"] == r["raised"]
    # The declared precision probe and the known limit are visible, and the limit is not gated.
    kinds = {(x["case"], x["kind"]) for x in base["candidate"]["disagreements"]}
    assert ("L18_response_paraphrase_precision", "false_positive") in kinds
    assert [(x["case"], x["kind"]) for x in base["candidate"]["known_limits"]] == [("K01_allergen_outside_registry", "false_negative")]
    assert ev.report_sha256(base) == ev.report_sha256(ev.evaluate(v1, v1, cases=cases))  # deterministic

    # Positive control: a widening change (new pending cue) passes.
    assert ev.evaluate(v1, with_cue(CueKind.PENDING, "outstanding"), cases=cases)["gate"]["passed"]

    # Recall reasons isolated: the candidate ruleset is benign, the candidate's ENGINE drops CRIT-001.
    from noteguard.engine import get_engine

    real, benign = get_engine(), with_cue(CueKind.PENDING, "outstanding")

    class DropCrit:
        def run_checks(self, snap, bundle, cutoff, **kw):
            r = real.run_checks(snap, bundle, cutoff, **kw)
            if bundle is benign:
                r = r.model_copy(update={"flags": tuple(f for f in r.flags if f.rule_id is not RuleId.CRIT_001)})
            return r

    g = ev.evaluate(v1, benign, engine=DropCrit(), cases=cases)["gate"]
    assert g == {"passed": False, "reasons": ["tier1_recall_below_1", "tier1_recall_decreased", "new_protected_miss"]}

    # Tier lowered on a protected rule: raised at Tier 2 is not a Tier 1 catch, and the floor refuses it.
    g = ev.evaluate(v1, with_rule(RuleId.ALG_001, default_tier=Tier.T2), cases=cases)["gate"]
    assert g == {"passed": False, "reasons": ["tier1_recall_below_1", "tier1_recall_decreased",
                                              "floor:tier_lowered:ALG-001"]}
    # Disabled protected rule.
    g = ev.evaluate(v1, with_rule(RuleId.CRIT_001, enabled=False), cases=cases)["gate"]
    assert not g["passed"] and {"tier1_recall_below_1", "new_protected_miss", "floor:rule_disabled:CRIT-001"} <= set(g["reasons"])
    # Floor only: extending a suppressing cue is refused even where this corpus shows no recall loss.
    g = ev.evaluate(v1, with_cue(CueKind.NEGATION, "clear"), cases=cases)["gate"]
    assert g == {"passed": False, "reasons": ["floor:suppressing_cue_extended:negation"]}


def test_approval_verify_and_offline_clis(tmp_path):
    """CP2 guard: an APPROVED record must be backed by the committed report AND a fresh rerun of the
    evaluation that passes the gate (evaluate.verify_approval / --verify). Each problem is isolated on
    a copy; the real record is checked whenever it is approved (today it is a draft). Both offline
    CLIs run end to end on files (they are the tools @k and I1 use).
    Mutation (applied): drop the fresh-rerun comparison in verify_approval -> fails."""
    import json
    import shutil

    from noteguard.contracts import ids
    from noteguard.governance import approval as ap
    from noteguard.governance import evaluate as ev
    from noteguard.governance import propose as pr
    from tests.support.golden import ROOT

    report = ROOT / "fixtures" / "labelled_eval" / "reports" / "EVAL_v1_vs_v1.json"
    committed = ev.report_sha256(json.loads(report.read_text(encoding="utf-8")))
    for sub in ("a", "b", "c"):
        (tmp_path / sub).mkdir()
    d = _approved_copy(tmp_path / "a", evaluation_report_sha256=committed)
    assert ev.verify_approval(d / "APPROVAL_v1.md", report) == []  # positive control
    wrong = _approved_copy(tmp_path / "b")  # report hash "e" * 64
    assert ev.verify_approval(wrong / "APPROVAL_v1.md", report) == ["report_file_does_not_match_record",
                                                                      "report_not_reproducible"]
    # Files changed and re-hashed, but the evaluation was not rerun: the old report cannot vouch for them.
    c = _approved_copy(tmp_path / "c", evaluation_report_sha256=committed)
    rs = json.loads((c / "v1.json").read_text(encoding="utf-8"))
    next(r for r in rs["rules"] if r["rule_id"] == "CRIT-001")["enabled"] = False
    (c / "v1.json").write_text(json.dumps(rs), encoding="utf-8")
    rec = json.loads((c / "APPROVAL_v1.md").read_text().split("```json\n")[1].split("\n```")[0])
    rec["ruleset_sha256"] = ids.sha256_hex((c / "v1.json").read_bytes())
    (c / "APPROVAL_v1.md").write_text(f"```json\n{json.dumps(rec)}\n```\n", encoding="utf-8")
    assert ev.verify_approval(c / "APPROVAL_v1.md", report) == ["report_not_reproducible", "gate_refused"]
    # The real record: whenever it is approved, it must verify clean.
    real = ap.parse_approval_record(ROOT / "rulesets" / "APPROVAL_v1.md")
    if real.status.value == "approved":
        assert ev.verify_approval(ROOT / "rulesets" / "APPROVAL_v1.md", report) == []

    # CLIs on files: propose (exported feedback) and evaluate (a candidate file that disables CRIT-001).
    fb = tmp_path / "feedback.json"
    fb.write_text(json.dumps([e.model_dump(mode="json") for e in
                              _feedback("DIFF-001", 10, "dismiss", "extraction_error")
                              + _feedback("ALG-001", 10, "dismiss", "not_clinically_relevant")]), encoding="utf-8")
    assert pr.main(["--feedback", str(fb), "--target", "v2", "--out", str(tmp_path / "p.json")]) == 0
    out = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    assert [(x["kind"], x["rule_id"]) for x in out["accepted"]] == [("retire_tier3_rule", "DIFF-001")]
    assert [(x["proposal"]["rule_id"], x["code"]) for x in out["refused"]] == [("ALG-001", "protected_floor")]
    assert ev.main(["--baseline", "v1", "--candidate", "v2bad", "--candidate-ruleset", str(c / "v1.json"),
                    "--out-dir", str(tmp_path / "r")]) == 1
    assert json.loads((tmp_path / "r" / "EVAL_v1_vs_v2bad.json").read_text())["gate"]["passed"] is False
    assert ev.main(["--baseline", "v1", "--candidate", "v1", "--out-dir", str(tmp_path / "r")]) == 0
