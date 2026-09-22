"""End-to-end smoke (Section 12.4). owner: I1 (B0 skeleton). One Playwright walk of the main path,
asserting text unique to each card (L9):
  1. multidisciplinary intake (paste a note + upload the scanned PDF)
  2. conflict flag: ALG-001 card shows "Which allergy entry is correct?"
  3. critical flag: CRIT-001 with evidence "Potassium 6.4 mmol/L" and owner "Dr Lim"
  4. human decision and its effect on closure (Tier 1 blocker disappears only after resolve)
  5. summary shows the human-review statement
  6. an out-of-scope encounter is refused (Dr Kaur)"""

import pytest

from tests.support.lanes import not_implemented

pytestmark = [pytest.mark.owner("I1"), pytest.mark.e2e]


def test_e2e_smoke():
    not_implemented("I1", "Playwright main-path walk against the real API and built frontend")
