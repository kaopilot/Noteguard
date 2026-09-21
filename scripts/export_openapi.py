"""Export the API contract to docs/openapi.json (B0; rerun by B2 when routes land).

Run: `uv run python scripts/export_openapi.py` (or `make openapi`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from noteguard.api.app import create_app  # noqa: E402


def openapi_document() -> dict:
    return create_app().openapi()


def main() -> None:
    out = ROOT / "docs" / "openapi.json"
    out.write_text(json.dumps(openapi_document(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", out.relative_to(ROOT), len(openapi_document()["paths"]), "paths")


if __name__ == "__main__":
    main()
