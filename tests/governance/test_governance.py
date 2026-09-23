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


def test_protected_floor_refused():
    """propose.py refuses lower_tier / disable_rule / narrow_rule on protected_floor rules."""
    lane_module("noteguard.governance.propose", "B4")
    not_implemented("B4", "submit each protected proposal kind for CRIT-001 and ALG-001; all refused")


def test_aggregate_no_content_or_ids():
    """Aggregate view: role-gated, no content, no patient/encounter ids, small cells '<5'."""
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


def test_ai_disabled_by_default():
    """L10 / OPEN-5: AI drafting is off unless configured; the UI copy says so."""
    c = client(real_app())
    login(c, "lim")
    r = c.get(R.AI_STATUS)
    assert r.status_code == 200 and r.json() == {"status": "disabled", "detail": "AI drafting disabled"}


def test_ai_timeout_falls_back():
    """Section 9: a provider that exceeds the timeout (or raises 5xx) yields the deterministic rule
    text labelled 'AI drafting unavailable; showing rule explanation'; the workflow is not blocked."""
    lane_module("noteguard.governance.ai_drafting", "B4")
    not_implemented("B4", "slow fake provider -> status unavailable_fallback and rule text returned")


def test_ai_output_validator_rejects_new_entity():
    """Section 9: output naming a registry entity absent from the evidence cluster, lacking evidence
    ids, raising certainty, containing a forbidden phrase, or carrying tier/owner/state is discarded."""
    lane_module("noteguard.governance.ai_drafting", "B4")
    not_implemented("B4", "fake provider outputs a drug not in the cluster -> rejected_fallback")


def test_eval_report_tier1_recall_gate():
    """evaluate.py reports per-rule counts with denominators and fails the gate if Tier 1 recall
    on the labelled fixtures drops below 1.0."""
    lane_module("noteguard.governance.evaluate", "B4")
    not_implemented("B4", "run evaluate on fixtures/labelled_eval and check the gate")
