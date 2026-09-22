"""API contract: registered routes, exported OpenAPI, error body shape, and (while the stub is
in place) that the stub serves the goldens exactly. owner: B0."""

import json

import pytest

from noteguard.contracts import routes as R
from tests.support import golden
from tests.support.api import A1, B1, login, run_cutoff, url
from tests.support.golden import ROOT
from tests.support.lanes import any_app, client

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]


def _registered(app):
    return {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/") and r.path != "/api/openapi.json"}


def test_registered_routes_equal_contract():
    assert _registered(any_app()) == set(R.ROUTE_TEMPLATES)


def test_openapi_export_in_sync():
    on_disk = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(any_app().openapi())), "run `make openapi`"


def test_error_bodies_are_error_code_only():
    c = client(any_app())
    r = c.get(R.ENCOUNTERS)
    assert r.status_code == 401 and r.json() == {"error_code": "unauthenticated"}
    h = login(c, "lim")
    r = c.post(url(R.CHECK_RUNS, encounter_id=A1), headers=h, json={"cutoff": "ZQX-NOT-A-DATE"})
    assert r.status_code == 422 and r.json() == {"error_code": "validation_failed"}
    r = c.get(url(R.ENCOUNTER, encounter_id="no-such-encounter"), headers=h)
    assert r.status_code == 404 and r.json() == {"error_code": "not_found"}


def _check_views(c, h, enc, name):
    g = golden.load(name)
    r = run_cutoff(c, h, enc, name)
    assert r.status_code == 200 and r.headers.get(R.STUB_HEADER) == "1"
    golden.assert_same([golden.flag_key(f) for f in r.json()["flags"]], [golden.flag_key(f) for f in g["flags"]], name)
    got = c.get(url(R.BUBBLES, encounter_id=enc), headers=h).json()["bubbles"]
    golden.assert_same([golden.bubble_key(x) for x in got], [golden.bubble_key(x) for x in g["bubbles"]], name)
    for route, key in ((R.SUMMARY, "summary"), (R.CLOSURE, "closure"), (R.GLANCE, "glance")):
        assert c.get(url(route, encounter_id=enc), headers=h).json() == g[key], f"{name} {key}"


def test_stub_serves_goldens():
    app = any_app()
    if not getattr(app.state, "is_stub", False):
        pytest.skip("real API in place: the stub-only check is retired (docs/decisions/B0.md)")
    c = client(app)
    h = login(c, "lim")
    _check_views(c, h, A1, "ENC-A1_1130")
    _check_views(c, h, A1, "ENC-A1_1600_rerun")  # same workspace: prior flags present
    _check_views(c, login(c, "lim"), A1, "ENC-A1_1600")  # fresh workspace
    _check_views(c, login(c, "wong"), B1, "ENC-B1_1600")
    r = c.post(url(R.FLAG_DECISIONS, encounter_id=A1, flag_id="flg_" + "0" * 24), headers=h, json={})
    assert r.status_code == 501 and r.json() == {"error_code": "not_implemented"}
