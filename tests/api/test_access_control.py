"""Required test 5. owner: B2."""

import pytest

from noteguard.api import authz
from noteguard.api.errors import ApiError
from noteguard.contracts import routes as R
from noteguard.contracts.errors import ErrorCode
from tests.support.api import A1, login, run_cutoff, url
from tests.support.golden import load
from tests.support.lanes import client, real_app

pytestmark = [pytest.mark.owner("B2"), pytest.mark.api]
NOT_FOUND = {"error_code": "not_found"}


def test_access_control(monkeypatch):
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

    # Fault injection (L6/L7): the STORE refuses Dr Kaur with the route layer bypassed entirely.
    store = app.state.store
    kaur_ctx = store.resolve_workspace(store.staff_for_session(kaur.cookies.get(R.SESSION_COOKIE)), hk[R.WORKSPACE_HEADER])
    with pytest.raises(ApiError) as exc:
        store.get_encounter(kaur_ctx, A1)
    assert exc.value.code is ErrorCode.NOT_FOUND
    # ...and over HTTP, with the route guard and the decision pre-check removed:
    app.dependency_overrides[authz.encounter_route_guard] = _route_guard_removed
    monkeypatch.setattr(authz, "decision_route_check", lambda *a, **k: None)
    for path in (url(R.ENCOUNTER, encounter_id=A1), url(R.FLAGS, encounter_id=A1), url(R.SUMMARY, encounter_id=A1)):
        r = kaur.get(path, headers=hk)
        assert r.status_code == 404 and r.json() == NOT_FOUND, path
    assert siti.get(url(R.ENCOUNTER, encounter_id=A1), headers=hs).status_code == 404
    r = tan.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id=alg["flag_id"]), headers=ht,
                 json={"action": "dismiss", "expected_revision": 1, "reason_code": "not_clinically_relevant"})
    assert r.status_code == 403 and r.json() == {"error_code": "forbidden_role"}  # tier/owner rule lives in the store


def _route_guard_removed(ctx: authz.AuthContext = authz.Depends(authz.auth_context)) -> authz.AuthContext:
    return ctx  # fault injection: authenticated, but NO route-level scope or role check
