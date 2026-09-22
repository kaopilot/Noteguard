"""Held-out ENC-A2 (never given to B1 chats). owner: B0 / I1. Skipped until the integrator
installs the package into fixtures/heldout/ (or sets NOTEGUARD_HELDOUT_DIR); see
docs/decisions/B0.md. An engine that special-cases ENC-A1 passes the goldens and fails here."""

import pytest

from tests.support import golden
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("I1"), pytest.mark.engine]
HELD = golden.heldout_scenarios()


@pytest.mark.skipif(not HELD, reason="held-out ENC-A2 not installed (I1 installs it; decisions/B0.md)")
@pytest.mark.parametrize("name", HELD or ("not-installed",))
def test_heldout_golden(name):
    golden.assert_scenario(engine(), name, heldout=True)
