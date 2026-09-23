"""End-to-end smoke (Section 12.4). owner: I1 (B0 skeleton). One Playwright walk of the main path,
asserting text unique to each card (L9):
  1. multidisciplinary intake (paste a note + upload the scanned PDF)
  2. conflict flag: the ALG-001 card (Tier 1) and its question bubble "Which allergy entry is correct?"
     (the flag's own question is null; the text is a bubble: decisions/I1.md #23)
  3. critical flag: CRIT-001 with evidence "Potassium 6.4 mmol/L" and owner "Dr Lim"
  4. human decision and its effect on closure (Tier 1 blocker disappears only after resolve)
  5. summary shows the human-review statement
  6. an out-of-scope encounter is refused (Dr Kaur)

The walk is tests/e2e/smoke.spec.ts with tests/e2e/playwright.config.ts: it starts the REAL app
(`noteguard.api.app:app`, real engine + approval gate) and the BUILT frontend, and never reuses a
running server. Needs `make setup` and `cd frontend && npx playwright install chromium`. Playwright's
output goes to frontend/test-results/i1-smoke/playwright.log (git-ignored), never into this report."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.owner("I1"), pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("playwright.config.ts")


def test_e2e_smoke():
    """Mutations (applied, decisions/I1.md #30): approval record back to draft (gate refuses) -> fails at the run
    step; an accepted Tier 1 no longer blocks closure -> fails at the blocker count."""
    frontend = ROOT / "frontend"
    assert (frontend / "node_modules" / "@playwright" / "test").is_dir(), "run `make setup` first (npm ci in frontend/)"
    env = dict(os.environ, NODE_PATH=str(frontend / "node_modules"))
    r = subprocess.run(["npx", "playwright", "test", "--config", str(CONFIG)], cwd=frontend, env=env,
                       capture_output=True, text=True, timeout=900)
    log = frontend / "test-results" / "i1-smoke" / "playwright.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(r.stdout + r.stderr, encoding="utf-8")
    assert r.returncode == 0, (f"Playwright smoke failed (exit {r.returncode}); see {log.relative_to(ROOT)}. "
                               "If the browser is missing: cd frontend && npx playwright install chromium")
