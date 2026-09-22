"""Generate the frontend's contract types (B0; `make types`). Never edit the outputs by hand.

frontend/src/api/schema.gen.ts         wire types from docs/openapi.json (openapi-typescript, pinned)
frontend/src/api/contract-data.gen.ts  CONTRACT constant from docs/contract_data.json
Each file's first line records the sha256 of its input; tests/contract/test_generated_types.py
fails when an input changed and the TS was not regenerated (no Node needed to check).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "api"
OPENAPI = ROOT / "docs" / "openapi.json"
DATA = ROOT / "docs" / "contract_data.json"
OPENAPI_TS = "openapi-typescript@7.13.0"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def header(src: Path) -> str:
    return (f"// GENERATED from {src.relative_to(ROOT)} sha256={sha(src)} by scripts/gen_ts_types.py. "
            "Do not edit; run `make types`.\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    schema = OUT / "schema.gen.ts"
    subprocess.run(["npx", "--yes", OPENAPI_TS, str(OPENAPI), "-o", str(schema), "--enum-values"], check=True,
                   cwd=ROOT, capture_output=True)
    schema.write_text(header(OPENAPI) + schema.read_text(encoding="utf-8"), encoding="utf-8")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    (OUT / "contract-data.gen.ts").write_text(
        header(DATA) + "export const CONTRACT = " + json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        + " as const;\nexport type Contract = typeof CONTRACT;\n", encoding="utf-8")
    print("wrote", schema.relative_to(ROOT), "and contract-data.gen.ts")


if __name__ == "__main__":
    main()
