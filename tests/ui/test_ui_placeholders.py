"""B3-owned UI checks (Section 18.5). The real tests live in frontend/ (vitest/Playwright); when a
frontend test covers one of these, B3 replaces the placeholder with a check that runs it and
records that in docs/decisions/B3.md. owner: B3."""

from pathlib import Path

import pytest

from tests.support.golden import ROOT
from tests.support.lanes import not_implemented

pytestmark = [pytest.mark.owner("B3"), pytest.mark.ui]
FRONTEND = ROOT / "frontend"


def _frontend() -> Path:
    if not (FRONTEND / "package.json").exists():
        not_implemented("B3", "frontend/ does not exist yet")
    return FRONTEND


def test_sw_never_caches_api():
    """The service worker caches only the app shell; any /api/ request bypasses the cache."""
    _frontend()
    not_implemented("B3", "assert the SW fetch handler never calls cache.put for /api/")


def test_offset_conversion_utf16():
    """Code-point offsets -> JS string indices; sliced text equals `quote` for the 16:00 social-work
    note (Chinese, POJ combining mark, astral emoji precede the span)."""
    _frontend()
    not_implemented("B3", "vitest over fixtures/expected/ENC-A1_1600.json evidence")


def test_no_clinical_data_in_browser_storage():
    """No clinical data in localStorage, sessionStorage or IndexedDB; workspace token in JS memory only."""
    _frontend()
    not_implemented("B3", "Playwright: walk the main path, then inspect all browser storage")


def test_tier_labels_not_colour_only():
    """Tier is shown as a text label + icon, never colour alone."""
    _frontend()
    not_implemented("B3", "render a flag card per tier and assert the text label")


def test_no_dangerously_set_inner_html():
    """B3 exit criterion: no dangerouslySetInnerHTML anywhere in frontend/src."""
    src = _frontend() / "src"
    hits = [str(p) for p in src.rglob("*") if p.suffix in {".ts", ".tsx", ".js", ".jsx"}
            and "dangerouslySetInnerHTML" in p.read_text(encoding="utf-8")]
    assert not hits, hits
