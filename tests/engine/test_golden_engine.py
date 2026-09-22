"""B1 exit check: engine output equals the golden fixtures (exact set equality). owner: B1."""

import pytest

from tests.support import golden
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]


@pytest.mark.parametrize("name", golden.SCENARIOS)
def test_golden_engine(name):
    golden.assert_scenario(engine(), name)
