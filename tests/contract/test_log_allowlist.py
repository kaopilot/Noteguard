"""Log allowlist behaves as an allowlist (L8): unknown keys and invalid values are dropped. owner: B0."""

import pytest

from noteguard.contracts import routes as R
from noteguard.contracts.log_allowlist import AUDIT_KEYS, LOG_KEYS, is_allowed, sanitize

pytestmark = [pytest.mark.owner("B0"), pytest.mark.contract]


def test_allowlist_not_denylist():
    assert AUDIT_KEYS <= set(LOG_KEYS)
    rec = sanitize({"route_template": R.ENCOUNTER, "note_text": "Potassium 6.4", "rationale_text": "x",
                    "workspace_token": "secret"})
    assert rec == {"route_template": R.ENCOUNTER}
    assert not is_allowed("route_template", "/api/encounters/0b1c2d3e-real-id")  # raw path, not template
    assert "route_template" not in sanitize({"route_template": "/api/encounters/abc"})
