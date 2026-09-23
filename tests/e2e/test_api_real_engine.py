"""I1 API-level runs: the REAL engine behind B2's API with B4's approval gate switched on.
owner: I1 (Section 18.5: API-level runs of the goldens, count integrity, grounding and
critical-observation routing; plus PDF-001 on a failed extraction from B2's handoff).

Every test builds ``gated_app()``, the same wiring as ``noteguard/api/app.py`` after I1 step 4.
Until @k approves v1, every check run is 503 ruleset_unapproved, so these tests fail by design.

Comparisons with the goldens ignore only run-specific values (ids and clocks of this run), and
the test checks those separately: flags link to this run's ids. Closure blocker lists and summary
claims are compared as sets (B2 decision #14; the goldens' order is hand-declared)."""

from __future__ import annotations

import hashlib
import json

import pytest

from noteguard.api.app import create_app
from noteguard.contracts import routes as R
from noteguard.contracts import states
from noteguard.contracts.types import FlagState
from noteguard.engine import get_engine
from noteguard.governance.approval import api_bundle_loader
from tests.api.helpers import decide, session, sources, upload_pdf
from tests.support.api import A1, B1, C1, run_cutoff, url
from tests.support.builders import staff_id
from tests.support.golden import ROOT, claim_key, load

pytestmark = [pytest.mark.owner("I1"), pytest.mark.e2e]

#: The five golden scenarios; the rerun needs its prior run in the same workspace.
SEQUENCES = [("lim", A1, ["ENC-A1_1130", "ENC-A1_1600_rerun"]), ("lim", A1, ["ENC-A1_1600"]),
             ("wong", B1, ["ENC-B1_1600"]), ("lim", C1, ["ENC-C1_1000"])]
#: Values that belong to THIS run (fresh ids and clocks), never to the golden.
RUN_SPECIFIC = frozenset({"run_id", "started_at", "completed_at", "created_at", "first_run_id", "last_run_id",
                          "generated_at", "opened_at"})


#: CCR-05 (approved by @k, 24 Sep 2026, option (a); landing waits for B4's report refresh): the golden's
#: OWN-001 reason is aligned to the ruleset's reason_template. Until it lands, that one field of that rule
#: is expected to equal the template (read from the ruleset, not typed here). A no-op once the golden matches.
CCR05_RULE = "OWN-001"
CCR05_REASON = next(r["reason_template"] for r in json.loads((ROOT / "rulesets" / "v1.json").read_text(encoding="utf-8"))["rules"]
                    if r["rule_id"] == CCR05_RULE)


def gated_app():
    return create_app(engine=get_engine(), bundle_loader=api_bundle_loader())


def _norm(x):
    """Drop run-specific keys at any depth; everything else is compared exactly."""
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items() if k not in RUN_SPECIFIC}
    if isinstance(x, list):
        return [_norm(v) for v in x]
    return x


def _claims(summary: dict) -> set:
    return {(claim_key(c), c["text"]) for c in summary["claims"]}


def _blockers(closure: dict) -> dict:
    return {k: {b["flag_id"]: _norm(b) for b in closure[k]} for k in ("tier1_blockers", "tier2_open")}


def _get(c, h, route, enc, **kw):
    r = c.get(url(route, encounter_id=enc, **kw), headers=h)
    assert r.status_code == 200, (route, r.status_code)
    return r.json()


def _walk(app):
    """Yield (name, golden, client, headers, encounter, check-run body, run ids so far) per scenario."""
    for staff, enc, names in SEQUENCES:
        c, h = session(app, staff)
        run_ids: list[str] = []
        for name in names:
            r = run_cutoff(c, h, enc, name)
            assert r.status_code == 200, (name, r.status_code, r.json())
            body = r.json()
            run_ids.append(body["run"]["run_id"])
            yield name, load(name), c, h, enc, body, list(run_ids)


def test_golden_scenarios_through_real_api():
    """All five goldens through the gated real API: exact flag set (no missing, no extra), every flag
    field, must-not-flag, bubbles, glance, summary (claims as a set), closure (blockers as sets).
    Mutation (applied, I1 #20): PEND-001 removed from the engine's rule table -> missing-flag assertion fails."""
    for name, g, c, h, enc, body, run_ids in _walk(gated_app()):
        assert _norm(body["run"]) == _norm(g["run"]), name
        got = {f["flag_id"]: f for f in body["flags"]}
        exp = {f["flag_id"]: f for f in g["flags"]}
        missing = sorted(exp[k]["rule_id"] for k in exp.keys() - got.keys())
        extra = sorted(got[k]["rule_id"] for k in got.keys() - exp.keys())
        assert not missing and not extra, (name, "missing", missing, "extra", extra)
        for fid, f in exp.items():
            if f["rule_id"] == CCR05_RULE:
                f = dict(f, reason=CCR05_REASON)
            diff = sorted(k for k in set(f) | set(got[fid]) if _norm({k: f.get(k)}) != _norm({k: got[fid].get(k)}))
            assert not diff, (name, f["rule_id"], "fields differ", diff)
            assert got[fid]["last_run_id"] == run_ids[-1] and got[fid]["first_run_id"] in run_ids, (name, f["rule_id"])
        for m in g["must_not_flag"]:
            hits = [f["rule_id"] for f in body["flags"] if m["rule_id"] in ("*", f["rule_id"])
                    and m["subject_key"] in ("*", "encounter", f["subject_key"])]
            assert not hits, (name, "must-not-flag", m["rule_id"], m["subject_key"])
        assert _get(c, h, R.FLAGS, enc) == body["flags"], name
        bubbles = _get(c, h, R.BUBBLES, enc)
        assert _norm(bubbles["bubbles"]) == _norm(g["bubbles"]) and bubbles["cutoff"] == g["cutoff"], name
        assert _norm(_get(c, h, R.GLANCE, enc)) == _norm(g["glance"]), name
        summary = _get(c, h, R.SUMMARY, enc)
        assert _norm({k: v for k, v in summary.items() if k != "claims"}) == \
            _norm({k: v for k, v in g["summary"].items() if k != "claims"}), name
        assert _claims(summary) == _claims(g["summary"]), name
        closure = _get(c, h, R.CLOSURE, enc)
        assert closure["status"] == g["closure"]["status"], name
        assert _blockers(closure) == _blockers(g["closure"]), name
        assert closure["tier3_open_count"] == g["closure"]["tier3_open_count"], name


def _counts_agree(c, h, enc, label):
    flags = _get(c, h, R.FLAGS, enc)
    glance, closure, summary = (_get(c, h, r, enc) for r in (R.GLANCE, R.CLOSURE, R.SUMMARY))
    open_ = [f for f in flags if states.is_unresolved(f["tier"], FlagState(f["state"]))]
    tier = {t: [f for f in open_ if f["tier"] == t] for t in (1, 2, 3)}
    claims = [x["params"]["tier"] for x in summary["claims"] if x["template"] == "open_priority"]
    assert glance["open_tier1"] == len(tier[1]) == len(closure["tier1_blockers"]) == claims.count(1), label
    assert glance["open_tier2"] == len(tier[2]) == len(closure["tier2_open"]) == claims.count(2), label
    assert glance["open_tier3"] == len(tier[3]) == closure["tier3_open_count"], label
    assert set(glance["tier1_owner_ids"]) == {f["owner_staff_id"] for f in tier[1]}, label
    assert glance["closure_status"] == closure["status"] == summary["closure_status"], label
    return glance


def test_open_count_integrity_real_api():
    """L14 end to end on the real engine (B0 ran it on the stub only), and AFTER a human decision,
    which the stub cannot serve. Mutation (applied, I1 #20): the glance counts only `open` Tier 1
    (accepted treated as closed) -> the post-accept agreement fails."""
    app = gated_app()
    for name, _g, c, h, enc, _body, _ids in _walk(app):
        _counts_agree(c, h, enc, name)
    c, h = session(app, "lim", "ENC-A1_1600")
    before = _counts_agree(c, h, A1, "before decision")
    t1 = next(f for f in _get(c, h, R.FLAGS, A1) if f["rule_id"] == "ALG-001" and f["state"] == "open")
    r = decide(c, h, A1, t1["flag_id"], action="accept", expected_revision=t1["revision"])
    assert r.status_code in (200, 201), r.status_code
    after = _counts_agree(c, h, A1, "after accept")
    assert after["open_tier1"] == before["open_tier1"], "accepted is not done (OPEN-6)"
    t1 = next(f for f in _get(c, h, R.FLAGS, A1) if f["flag_id"] == t1["flag_id"])
    pen = next(e for e in t1["evidence"] if e["role_in_flag"] == "counter_claim")  # as B2's L16 test adjudicates
    r = decide(c, h, A1, t1["flag_id"], action="resolve", expected_revision=t1["revision"],
               reason_code="allergy_entry_confirmed",
               adjudicated_evidence=[{"note_version_id": pen["note_version_id"], "start": pen["start"], "end": pen["end"]}])
    assert r.status_code in (200, 201), r.status_code
    after = _counts_agree(c, h, A1, "after resolve")
    assert after["open_tier1"] == before["open_tier1"] - 1


def test_grounding_through_real_api():
    """Every note-span evidence on flags, bubbles and summary claims equals the source text at its
    offsets (code points), and its quote hash matches. Mutation (applied, I1 #20): the store serves the
    source text shifted by one code point -> quote mismatch."""
    checked = 0
    for name, _g, c, h, enc, body, _ids in _walk(gated_app()):
        texts: dict[str, str] = {}
        evidence = [e for f in body["flags"] for e in f["evidence"]]
        evidence += [e for b in _get(c, h, R.BUBBLES, enc)["bubbles"] for e in b["evidence"]]
        evidence += [e for x in _get(c, h, R.SUMMARY, enc)["claims"] for e in x["evidence"]]
        for e in evidence:
            if e.get("record_field"):
                continue  # OWN-001 cites a structured encounter field, not a note span
            vid = e["note_version_id"]
            if vid not in texts:
                texts[vid] = _get(c, h, R.SOURCE_TEXT, enc, source_version_id=vid)["text"]
            assert texts[vid][e["start"]:e["end"]] == e["quote"], (name, vid, e["start"], e["end"])
            assert hashlib.sha256(e["quote"].encode("utf-8")).hexdigest() == e["quote_sha256"], (name, vid)
            checked += 1
    assert checked > 0


def test_critical_observation_routing_real_api():
    """CRIT-001 at API level: raised at 11:30 as Tier 1, owned by the responsible clinician (never
    unassigned); not raised at 16:00 once a later clinician response exists. Mutation (applied, I1 #20):
    Tier 1 owner routing returns no owner -> the run or the owner assertion fails."""
    app = gated_app()
    c, h = session(app, "lim", "ENC-A1_1130")
    crit = [f for f in _get(c, h, R.FLAGS, A1) if f["rule_id"] == "CRIT-001"]
    assert len(crit) == 1 and crit[0]["tier"] == 1 and crit[0]["state"] == "open"
    assert crit[0]["owner_staff_id"] == staff_id("lim")
    assert crit[0]["flag_id"] in {b["flag_id"] for b in _get(c, h, R.CLOSURE, A1)["tier1_blockers"]}
    c, h = session(app, "lim", "ENC-A1_1600")
    assert not [f for f in _get(c, h, R.FLAGS, A1) if f["rule_id"] == "CRIT-001"]


@pytest.mark.xfail(strict=True, reason="FINDING I1 #19 (B1 via @k): no PDF-001 on a failed extraction without a page "
                   "table; strict, so it fails loudly once the engine is fixed and this marker must go")
def test_pdf001_on_failed_extraction_without_page_table():
    """B2 handoff: a PDF whose extraction FAILED has no page table; the real engine still raises
    PDF-001 on it, and no absence answer claims 'not documented'. Mutation to apply: skip sources
    with an empty page table in PDF-001 -> no flag for the failed version."""
    c, h = session(gated_app(), "lim")
    r = upload_pdf(c, h, A1, b"%PDF-1.4\nthis is not really a pdf", author="ravi")
    assert r.status_code == 201 and r.json()["extraction_status"] == "failed"
    vid = r.json()["note_version_id"]
    t = _get(c, h, R.SOURCE_TEXT, A1, source_version_id=vid)
    assert t["extraction_status"] == "failed" and t["text"] == "" and not t.get("pages")
    assert run_cutoff(c, h, A1, "ENC-A1_1600").status_code == 200
    pdf = [f for f in _get(c, h, R.FLAGS, A1) if f["rule_id"] == "PDF-001"
           and vid in {e["note_version_id"] for e in f["evidence"]}]
    assert len(pdf) == 1 and pdf[0]["tier"] == 2
    owner = next(s for s in sources(c, h, A1) if s["note_version_id"] == vid)["author_staff_id"]
    assert pdf[0]["owner_staff_id"] == owner == staff_id("ravi")
    for b in _get(c, h, R.BUBBLES, A1)["bubbles"]:
        assert b["status"] != "not_documented_in_supplied_sources", b["question_template_id"]
