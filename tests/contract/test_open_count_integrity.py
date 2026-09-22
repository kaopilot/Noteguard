"""L14 count integrity end to end: glance, closure, summary and the flag list agree on every
open count. owner: B0 / I1. Runs against whatever app is in place (stub now, real after B2/I1)."""

import pytest

from noteguard.contracts import routes as R
from noteguard.contracts import states
from noteguard.contracts.types import FlagState
from tests.support.api import A1, B1, C1, login, run_cutoff, url
from tests.support.lanes import any_app, client

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract, pytest.mark.api]
SEQUENCES = [("lim", A1, ["ENC-A1_1130", "ENC-A1_1600_rerun"]), ("lim", A1, ["ENC-A1_1600"]), ("wong", B1, ["ENC-B1_1600"]),
             ("lim", C1, ["ENC-C1_1000"])]


def test_open_count_integrity():
    """Mutation: count superseded Tier 1 as closed in one view only -> the rerun step fails."""
    app = any_app()
    for staff, enc, scenarios in SEQUENCES:
        c = client(app)
        h = login(c, staff)
        for name in scenarios:
            assert run_cutoff(c, h, enc, name).status_code == 200, name
            flags = c.get(url(R.FLAGS, encounter_id=enc), headers=h).json()
            glance = c.get(url(R.GLANCE, encounter_id=enc), headers=h).json()
            closure = c.get(url(R.CLOSURE, encounter_id=enc), headers=h).json()
            summary = c.get(url(R.SUMMARY, encounter_id=enc), headers=h).json()
            open_ = [f for f in flags if states.is_unresolved(f["tier"], FlagState(f["state"]))]
            tier = {t: [f for f in open_ if f["tier"] == t] for t in (1, 2, 3)}
            claims = [x["params"]["tier"] for x in summary["claims"] if x["template"] == "open_priority"]
            assert glance["open_tier1"] == len(tier[1]) == len(closure["tier1_blockers"]) == claims.count(1), name
            assert glance["open_tier2"] == len(tier[2]) == len(closure["tier2_open"]) == claims.count(2), name
            assert glance["open_tier3"] == len(tier[3]) == closure["tier3_open_count"], name
            assert set(glance["tier1_owner_ids"]) == {f["owner_staff_id"] for f in tier[1]}, name
            assert glance["closure_status"] == closure["status"] == summary["closure_status"], name
