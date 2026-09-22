"""Synthetic seed for every new workspace (OPEN-3): ENC-A1, ENC-B1, ENC-C1, the clinic staff,
and the fixture PDFs' original bytes (for document tokens). Synthetic data only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from noteguard.contracts import ids
from noteguard.contracts.types import EncounterSnapshot, Staff

ROOT = Path(__file__).resolve().parents[2]
ENCOUNTERS_DIR = ROOT / "fixtures" / "encounters"
PDF_DIR = ROOT / "fixtures" / "pdfs"


@dataclass(frozen=True)
class Seed:
    snapshots: tuple[EncounterSnapshot, ...]
    staff: dict[str, Staff]
    blobs: dict[str, bytes]  # sha256 -> original bytes of the fixture PDFs


@lru_cache(maxsize=1)
def load_seed() -> Seed:
    snaps = tuple(EncounterSnapshot.model_validate_json(p.read_text(encoding="utf-8"))
                  for p in sorted(ENCOUNTERS_DIR.glob("ENC-*.json")))
    clinic = json.loads((ENCOUNTERS_DIR / "clinic.json").read_text(encoding="utf-8"))
    staff = {s.staff_id: s for s in (Staff.model_validate(x) for x in clinic["staff"])}
    blobs = {ids.sha256_hex(data): data for data in (p.read_bytes() for p in sorted(PDF_DIR.glob("*.pdf")))}
    return Seed(snapshots=snaps, staff=staff, blobs=blobs)
