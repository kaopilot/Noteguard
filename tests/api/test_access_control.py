"""Required test 5. owner: B2."""

import pytest

from noteguard.contracts import routes as R
from tests.support.api import A1, login, run_cutoff, url
from tests.support.golden import load
from tests.support.lanes import client, not_implemented, real_app

pytestmark = [pytest.mark.owner("B2"), pytest.mark.api]
NOT_FOUND = {"error_code": "not_found"}


def test_access_control():
    """Mutations: drop the membership check in the store -> Dr Kaur reads ENC-A1; check role
    only at the route -> the fault-injection step reads through."""
    app = real_app()
    kaur = client(app)
    hk = login(kaur, "kaur")  # same clinic, on no care team
    for path in (url(R.ENCOUNTER, encounter_id=A1), url(R.FLAGS, encounter_id=A1), url(R.SUMMARY, encounter_id=A1)):
        r = kaur.get(path, headers=hk)
        assert r.status_code == 404 and r.json() == NOT_FOUND, path  # out of scope looks like absent
    assert A1 not in [e["encounter_id"] for e in kaur.get(R.ENCOUNTERS, headers=hk).json()]

    tan = client(app)
    ht = login(tan, "tan")
    assert run_cutoff(tan, ht, A1, "ENC-A1_1130").status_code == 200
    alg = next(f for f in load("ENC-A1_1130")["flags"] if f["rule_id"] == "ALG-001")
    r = tan.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=alg["flag_id"]), headers=ht,
                 json={"action": "dismiss", "expected_revision": 1, "reason_code": "not_clinically_relevant"})
    assert r.status_code == 403 and r.json() == {"error_code": "forbidden_role"}  # nurse cannot dismiss Tier 1

    siti = client(app)
    hs = login(siti, "siti")  # clinic admin: not a clinical superuser
    assert siti.get(url(R.ENCOUNTER, encounter_id=A1), headers=hs).status_code == 404
    assert A1 not in [e["encounter_id"] for e in siti.get(R.ENCOUNTERS, headers=hs).json()]

    not_implemented("B2", "fault-inject: call the store read for ENC-A1 as Dr Kaur with the route dependency "
                          "bypassed and assert the store refuses (L6/L7); replace this line")
