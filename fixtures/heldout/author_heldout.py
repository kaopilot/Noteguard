"""HELD-OUT synthetic encounter ENC-A2 (B0). ALL NAMES AND CONTENT ARE FICTIONAL.

NEVER give this package to a B1 (engine) chat. The integrator installs it at I1:
  cp -r noteguard_heldout_ENC-A2/* <repo>/fixtures/heldout/
  NOTEGUARD_HELDOUT_DIR=<repo>/fixtures/heldout uv run pytest tests/engine/test_heldout_golden.py
Same rules as ENC-A1, different names, drugs, times, phrasings and structure; a partial
(2-page) PDF; the 'earlier reviewed' and 'carried-forward reviewed' traps inside the record.

Regenerate: NOTEGUARD_REPO=<repo> uv run --project <repo> python author_heldout.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("NOTEGUARD_REPO", HERE.parents[1]))
sys.path.insert(0, str(REPO))

from noteguard.contracts import ids  # noqa: E402
from noteguard.contracts.types import EncounterSnapshot  # noqa: E402

_spec = importlib.util.spec_from_file_location("seed_author", REPO / "fixtures" / "author_fixtures.py")
SEED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SEED)  # PDF helpers and the extraction contract only

SGT = timezone(timedelta(hours=8))
DAY = (2026, 9, 14)
ENC_DIR = HERE / "encounters"
PDF_DIR = HERE / "pdfs"


def fid(label: str) -> str:
    return str(uuid.UUID(bytes=hashlib.sha256(("heldout/" + label).encode()).digest()[:16], version=4))


def sgt(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    return datetime(*DAY, h, m, tzinfo=SGT).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


CLINIC = {"clinic_id": fid("clinic/CLN-2"), "display_name": "Synthetic Community Hospital, Ward 3"}
STAFF = {
    "farah": ("Dr Farah", "clinician", "clinician"),
    "hakim": ("Dr Hakim", "clinician", "clinician"),
    "wee": ("Nurse Wee", "nursing", "nurse"),
    "arun": ("Nurse Arun", "nursing", "nurse"),
    "teo": ("Pharmacist Teo", "pharmacy", "pharmacist"),
    "nadia": ("OT Nadia", "other", "allied_health"),
    "ho": ("Clerk Ho", "other", "clerical_staff"),
}


def staff_id(key: str) -> str:
    return fid(f"staff/{key}")


def staff_record(key: str) -> dict:
    name, disc, role = STAFF[key]
    return {"staff_id": staff_id(key), "display_name": name, "discipline": disc, "role": role,
            "clinic_id": CLINIC["clinic_id"]}


def two_page_pdf(lines: list[str]) -> bytes:
    """Page 1 has a text layer; page 2 is a scanned image with no text layer -> status partial."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT", "/F1 11 Tf", "14 TL", "72 740 Td"] + [x for ln in lines for x in (f"({esc(ln)}) Tj", "T*")] + ["ET"]
    text_stream = "\n".join(ops).encode("latin-1")
    w, h = 200, 60
    raster = b"".join(bytes([230 if (y // 5) % 2 == 0 else (50 if (x // 7) % 3 else 230) for x in range(w)])
                      for y in range(h))
    return SEED._pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        SEED._stream(text_stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im1 8 0 R >> >> /Contents 7 0 R >>",
        SEED._stream(b"q 400 0 0 120 90 600 cm /Im1 Do Q"),
        SEED._stream(raster, f"/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray /BitsPerComponent 8"),
    ])


REFERRAL = ["Riverside Polyclinic (synthetic)", "Referral letter", "Re: 81-year-old for inpatient review.",
            "Medication chart attached on page 2."]

SOURCES = [
    ("overnight", "Overnight review", "clinician", "hakim", "pasted_text", "08:10",
     [("08:10", "Overnight review (Dr Hakim).\nNa reviewed overnight, plan as per team.\nNo acute issues.")]),
    ("adm_nursing", "Nursing admission", "nursing", "wee", "pasted_text", "08:30",
     [("08:30", "Nursing admission.\nNo known drug allergies.\n4 units given as per chart.\n"
                "Obs: sats 97% on RA, resp rate 16.")]),
    ("ward_round", "Consultant ward round", "clinician", "farah", "pasted_text", "09:15",
     [("09:15", "Consultant ward round - Dr Farah.\nClinically stable.\nBisoprolol 2.5mg once daily.\n"
                "Atorvastatin 40 mg nocte.\nUrine culture sent, ward team to chase.")]),
    ("lab", "Lab result call", "nursing", "arun", "pasted_text", "09:40",
     [("09:40", "Lab phoned.\nNa 118 mmol/L.")]),
    ("handover", "Nursing handover", "nursing", "wee", "pasted_text", "10:30",
     [("10:30", "Nursing handover.\nNa reviewed overnight, plan as per team.\nMobilising independently.")]),
    ("pharmacy", "Pharmacy medicines reconciliation", "pharmacy", "teo", "pasted_text", "11:20",
     [("11:20", "Pharmacy medicines reconciliation.\nSulfa allergy - hives (patient and daughter confirm).\n"
                "Pre-admission: bisoprolol 5 mg OD, atorvastatin 40 mg nocte.")]),
    ("referral_pdf", "Polyclinic referral letter", "other", "ho", "pdf", "12:40",
     [("12:40", ("pdf", "ENC-A2_polyclinic_referral_partial.pdf", two_page_pdf(REFERRAL)))]),
    ("obs", "Observations", "nursing", "arun", "pasted_text", "13:30",
     [("13:30", "Observations.\nSats 90% on RA, resp rate 28.\nEscalated to Dr Farah by phone.")]),
    ("radiology", "Radiology", "nursing", "arun", "pasted_text", "15:05",
     [("15:05", "Radiology.\nChest X-ray done, awaiting report by 17:00.")]),
    ("review", "Medical review", "clinician", "farah", "pasted_text", "16:20",
     [("16:20", "Medical review (Dr Farah).\nSodium 118 seen by Dr Farah; fluid restriction commenced.\n"
                "Repeat Na sent; Dr Farah to review by 21:00.\nAtorvastatin reduced to 20 mg nocte.")]),
    ("ot", "Occupational therapy", "other", "nadia", "pasted_text", "17:00",
     [("17:00", "Occupational therapy.\nKitchen assessment with daughter (\u5973\u513f translating) \u2014 made tea "
                "safely \U0001F375.\nClinically stable.\nPlan: home visit Thursday.")]),
]
TEAM = [("farah", "responsible_clinician"), ("hakim", "member"), ("wee", "member"), ("arun", "member"),
        ("teo", "member"), ("nadia", "member"), ("ho", "member")]


def build(ref: str = "ENC-A2", write_pdfs: bool = False) -> dict:
    enc_id = fid(f"encounter/{ref}")
    patient = {"patient_id": fid(f"patient/{ref}"), "patient_ref": fid(f"patient_ref/{ref}"),
               "display_label": "Synthetic patient A2"}
    encounter = {"encounter_id": enc_id, "encounter_ref": ref, "clinic_id": CLINIC["clinic_id"],
                 "patient_id": patient["patient_id"], "setting": "community hospital ward", "started_at": sgt("08:00"),
                 "responsible_clinician_id": staff_id("farah"), "attending_clinician_id": staff_id("farah")}
    memberships = [{"encounter_id": enc_id, "staff_id": staff_id(k), "team_role": r, "valid_from": sgt("07:30"),
                    "valid_to": None} for k, r in TEAM]
    srcs, vers, exts = [], [], []
    for key, title, disc, author, stype, stime, versions in SOURCES:
        src_id = fid(f"{ref}/source/{key}")
        ext_id = f"{ref}-{key.upper()}"
        srcs.append({"source_id": src_id, "encounter_id": enc_id, "source_system": "heldout-emr",
                     "identifier_namespace": "urn:synthetic:heldout-emr", "external_id": ext_id, "source_type": stype,
                     "author_staff_id": staff_id(author), "discipline": disc, "title": title, "source_time": sgt(stime)})
        prev = None
        for n, (vtime, body) in enumerate(versions, start=1):
            vid = fid(f"{ref}/source/{key}/v{n}")
            if isinstance(body, tuple):
                _, fname, data = body
                if write_pdfs:
                    PDF_DIR.mkdir(parents=True, exist_ok=True)
                    (PDF_DIR / fname).write_bytes(data)
                text, pages, status = SEED.extract_pdf(data)
                media, extractor = "application/pdf", "pdfplumber@0.11.7"
                note = "page 2 has no text layer; manual review or approved OCR required" if status != "complete" else None
            else:
                data = body.encode("utf-8")
                text, pages, status, media, extractor, note = body, [], "not_applicable", "text/plain; charset=utf-8", "paste@1", None
            sha = ids.sha256_hex(data)
            vers.append({"source_version_id": vid, "source_id": src_id, "version": n, "version_time": sgt(vtime),
                         "received_at": sgt(vtime), "sha256": sha, "byte_length": len(data), "media_type": media,
                         "idempotency_key": ids.idempotency_key("urn:synthetic:heldout-emr", ext_id, n, sha),
                         "supersedes_version_id": prev})
            exts.append({"source_version_id": vid, "status": status, "text": text, "pages": pages,
                         "extractor": extractor, "note": note})
            prev = vid
    snap = {"clinic": CLINIC, "patient": patient, "encounter": encounter,
            "staff": [staff_record(k) for k in sorted(STAFF)], "memberships": memberships,
            "sources": srcs, "versions": vers, "extractions": exts, "prior_flags": [], "decisions": []}
    EncounterSnapshot.model_validate(snap)
    return snap


def main() -> None:
    ENC_DIR.mkdir(parents=True, exist_ok=True)
    snap = build(write_pdfs=True)
    (ENC_DIR / "ENC-A2.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ENC-A2", len(snap["sources"]), "sources;", [e["status"] for e in snap["extractions"] if e["pages"]])


if __name__ == "__main__":
    main()
