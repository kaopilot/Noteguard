"""B3-owned UI checks (Section 18.5). owner: B3.

Each check runs the named Vitest cases in frontend/tests (one Vitest run per pytest session, JSON
reporter) and asserts that every named case RAN and PASSED, so a deleted or renamed frontend test
fails here instead of silently disappearing. Only case names and statuses are reported; Vitest's
failure text is not echoed (it can contain synthetic note text). Mutation spot-checks for every case
are recorded in docs/decisions/B3.md.

The real-browser walk at 375 px and 1440 px (frontend/e2e/walk.spec.ts, `npm run e2e`) needs a
browser and two servers, so it is not part of `make test`; its results are recorded in the handoff.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.golden import ROOT

pytestmark = [pytest.mark.owner("B3"), pytest.mark.ui]
FRONTEND = ROOT / "frontend"


@pytest.fixture(scope="session")
def vitest(tmp_path_factory) -> dict[tuple[str, str], str]:
    if not (FRONTEND / "node_modules" / ".bin" / "vitest").exists() or shutil.which("npx") is None:
        pytest.fail("frontend dependencies missing: run `make setup` (npm ci in frontend/)")
    report = tmp_path_factory.mktemp("vitest") / "report.json"
    proc = subprocess.run(["npx", "vitest", "run", "--reporter=json", f"--outputFile={report}"],
                          cwd=FRONTEND, capture_output=True, text=True, timeout=600)
    if not report.exists():
        pytest.fail(f"vitest wrote no report (exit code {proc.returncode})")
    data = json.loads(report.read_text(encoding="utf-8"))
    return {(Path(f["name"]).name, a["fullName"]): a["status"]
            for f in data["testResults"] for a in f["assertionResults"]}


def _passed(results: dict[tuple[str, str], str], file: str, *cases: str) -> None:
    for case in cases:
        status = results.get((file, case))
        assert status is not None, f"{file}: case {case!r} did not run"
        assert status == "passed", f"{file}: case {case!r} is {status}"


def test_sw_never_caches_api(vitest):
    """The service worker caches only the app shell; any /api/ request bypasses the cache."""
    _passed(vitest, "sw.test.ts",
            "requests under /api/ are never answered from or written to the cache",
            "install precaches only the listed shell, never an /api/ path, and nothing writes at runtime",
            "an offline navigation gets the static offline page")


def test_offset_conversion_utf16(vitest):
    """Code-point offsets -> JS string indices; sliced text equals `quote` for every golden span,
    including the 16:00 social-work note (Chinese, POJ combining mark, astral emoji before the span)."""
    _passed(vitest, "offsets.test.ts",
            "every golden evidence span converts to UTF-16 and matches its quote",
            "the 16:00 social-work span sits after an astral emoji: naive slicing is wrong, conversion is right",
            "a mismatching or out-of-range span is refused and never highlighted")


def test_no_clinical_data_in_browser_storage(vitest):
    """No clinical data in localStorage, sessionStorage, IndexedDB or Cache Storage after the main
    path; the workspace token lives in JS memory and travels only in its header."""
    _passed(vitest, "storage.test.tsx", "main path leaves nothing clinical in browser storage and keeps the token in memory")
    _passed(vitest, "static.test.ts", "no browser persistence API is referenced in frontend/src")


def test_tier_labels_not_colour_only(vitest):
    """Tier is shown as a text label + a distinct shape, never colour alone."""
    _passed(vitest, "tier.test.tsx",
            "each tier badge shows its tier as visible text with a distinct shape",
            "flag cards carry the tier label in their header for every tier")


def test_no_dangerously_set_inner_html(vitest):
    """B3 exit criterion: no dangerouslySetInnerHTML (or other raw HTML injection) in frontend/src."""
    src = FRONTEND / "src"
    hits = [str(p) for p in src.rglob("*") if p.suffix in {".ts", ".tsx", ".js", ".jsx"}
            and "dangerouslySetInnerHTML" in p.read_text(encoding="utf-8")]
    assert not hits, hits
    _passed(vitest, "static.test.ts", "no raw HTML injection anywhere in frontend/src")


def test_frontend_suite_all_green(vitest):
    """Every Vitest case passes (includes the stale-decision 409 case and the no-console guard)."""
    assert len(vitest) >= 13
    bad = sorted(f"{f}: {c} -> {s}" for (f, c), s in vitest.items() if s != "passed")
    assert not bad, bad
