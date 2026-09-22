"""L13, protected floor, aggregate, AI gate. owner: B4. Interfaces inside noteguard/governance are
B4's to design; bodies marked not_implemented carry the specification in their docstring."""

import re

import pytest

from noteguard.contracts import routes as R
from tests.support.api import login
from tests.support.lanes import client, lane_module, not_implemented, real_app

pytestmark = [pytest.mark.owner("B4"), pytest.mark.governance]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def test_no_runtime_rule_mutation():
    """L13: no route, config or feedback path changes a rule, threshold or weight at runtime;
    the loaded bundle is immutable and its sha256 equals the approved record's."""
    lane_module("noteguard.governance", "B4")
    not_implemented("B4", "load the pinned bundle, apply feedback events, assert bundle hashes unchanged")


def test_unapproved_ruleset_refused():
    """L13: a ruleset whose file hashes do not match an `approved` APPROVAL_*.md record is refused
    at load (rulesets/APPROVAL_v1.md is currently `draft`, so it must be refused today)."""
    lane_module("noteguard.governance", "B4")
    not_implemented("B4", "assert the loader refuses the draft v1 record and a hash-mismatched copy")


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
