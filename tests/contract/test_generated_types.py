"""Generated frontend types are current (B0). Fails if docs/openapi.json or contracts changed
and `make types` was not rerun, so a contract change surfaces as a B3 compile error, not drift."""

import hashlib
import importlib.util
import json

import pytest

from tests.support.golden import ROOT

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]
API = ROOT / "frontend" / "src" / "api"


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_contract_data_export_in_sync():
    spec = importlib.util.spec_from_file_location("export_contract_data", ROOT / "scripts" / "export_contract_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    on_disk = json.loads((ROOT / "docs" / "contract_data.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(mod.contract_data())), "run `make types`"


def test_generated_ts_matches_inputs():
    for gen, src in (("schema.gen.ts", "docs/openapi.json"), ("contract-data.gen.ts", "docs/contract_data.json")):
        first = (API / gen).read_text(encoding="utf-8").splitlines()[0]
        assert f"sha256={_sha(ROOT / src)}" in first, f"{gen} is stale; run `make types`"
    body = (API / "contract-data.gen.ts").read_text(encoding="utf-8").split("export const CONTRACT = ", 1)[1]
    assert json.loads(body.rsplit(" as const;", 1)[0]) == json.loads((ROOT / "docs" / "contract_data.json").read_text())
