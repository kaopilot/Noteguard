"""Author the synthetic seed encounters (B0). ALL NAMES AND CONTENT ARE FICTIONAL.

Run: `uv run python fixtures/author_fixtures.py` (writes fixtures/encounters/*.json and
fixtures/pdfs/*.pdf). The declarations below ARE the fixture; @k signs them off at CP0.
After CP0 only a CCR changes them.

IDs: deterministic UUIDv4-format values derived from a readable label (fixture-only
helper `fid`), so golden files are stable. Runtime IDs use contracts.ids.new_id().

PDF text extraction for the fixtures is produced with pdfplumber (pinned in uv.lock),
`page.extract_text()` with defaults, pages joined by "\\n". B2's intake must reproduce
exactly this extraction for these files (test_pdf_extraction_boundary); if it cannot,
raise a CCR rather than editing the fixture.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from noteguard.contracts import ids  # noqa: E402
from noteguard.contracts.types import EncounterSnapshot  # noqa: E402

SGT = timezone(timedelta(hours=8))
DAY = (2026, 9, 21)
ENC_DIR = ROOT / "fixtures" / "encounters"
PDF_DIR = ROOT / "fixtures" / "pdfs"


def fid(label: str) -> str:
    """Deterministic UUIDv4-format id from a readable label (fixtures only)."""
    return str(uuid.UUID(bytes=hashlib.sha256(label.encode()).digest()[:16], version=4))


def sgt(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    return datetime(*DAY, h, m, tzinfo=SGT).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Clinic and staff (fictional)
# ---------------------------------------------------------------------------

CLINIC = {"clinic_id": fid("clinic/CLN-1"), "display_name": "Synthetic General Hospital, Ward 7"}

STAFF = {
    # key: (display_name, discipline, role)
    "lim": ("Dr Lim", "clinician", "clinician"),
    "tan": ("Nurse Tan", "nursing", "nurse"),
    "ravi": ("Nurse Ravi", "nursing", "nurse"),
    "ong": ("Pharmacist Ong", "pharmacy", "pharmacist"),
    "chen": ("Physio Chen", "physiotherapy", "allied_health"),
    "goh": ("SW Goh", "counselling_social_work", "allied_health"),
    "lee": ("Ward Clerk Lee", "other", "clerical_staff"),
    "wong": ("Dr Wong", "clinician", "clinician"),
    "lau": ("Nurse Lau", "nursing", "nurse"),
    "kaur": ("Dr Kaur", "clinician", "clinician"),  # same clinic, on NO care team
    "siti": ("Admin Siti", "other", "clinic_admin"),  # not a clinical superuser
    "rao": ("Dr Rao (Medical Director)", "clinician", "medical_director"),
    "koh": ("Koh (Quality & Risk)", "other", "quality_risk"),
    "menon": ("Menon (Legal)", "other", "legal"),
}


def staff_id(key: str) -> str:
    return fid(f"staff/{key}")


def staff_record(key: str) -> dict:
    name, disc, role = STAFF[key]
    return {"staff_id": staff_id(key), "display_name": name, "discipline": disc, "role": role,
            "clinic_id": CLINIC["clinic_id"]}


# ---------------------------------------------------------------------------
# Minimal PDF writer (no dependency): one text page, or one image-only page
# ---------------------------------------------------------------------------


def _pdf(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _stream(data: bytes, extra: str = "") -> bytes:
    return f"<< {extra} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"


def text_pdf(lines: list[str]) -> bytes:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT", "/F1 11 Tf", "14 TL", "72 740 Td"]
    for ln in lines:
        ops += [f"({esc(ln)}) Tj", "T*"]
    ops.append("ET")
    content = "\n".join(ops).encode("latin-1")
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        _stream(content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ])


def image_only_pdf() -> bytes:
    """A 'scanned' page: a grey raster with dark bars that look like lines of text.
    No font, no text layer."""
    w, h = 240, 90
    rows = []
    for y in range(h):
        row = bytearray([235] * w)
        if (y // 6) % 2 == 1 and y < 84:
            for x in range(12, w - 12 - (y * 7) % 60):
                row[x] = 40 if (x // 9) % 4 else 235
        rows.append(bytes(row))
    raster = b"".join(rows)
    content = b"q 432 0 0 162 72 560 cm /Im1 Do Q"
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
        _stream(content),
        _stream(raster, f"/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray /BitsPerComponent 8"),
    ])


def extract_pdf(data: bytes) -> tuple[str, list[dict], str]:
    """Fixture-authoring extraction with pdfplumber defaults (the contract B2 must match)."""
    import io

    import pdfplumber

    texts, pages, pos = [], [], 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            t = page.extract_text() or ""
            if n > 1:
                pos += 1  # "\n" page separator
            pages.append({"page": n, "start": pos, "end": pos + len(t), "char_count": len(t)})
            texts.append(t)
            pos += len(t)
    text = "\n".join(texts)
    if all(p["char_count"] == 0 for p in pages):
        status = "no_text_layer"
    elif any(p["char_count"] == 0 for p in pages):
        status = "partial"
    else:
        status = "complete"
    return text, pages, status


# ---------------------------------------------------------------------------
# ENC-A1 — medical ward, one calendar day (times Asia/Singapore)
# ---------------------------------------------------------------------------

REFERRAL_LINES = [
    "Sunrise Family Clinic (synthetic)",
    "Referral letter",
    "Re: 72-year-old patient for admission.",
    "Reason: poorly controlled diabetes and hypertension.",
    "Current medicines as per attached GP list.",
    "Thank you for seeing this patient.",
]

# Each source: key, title, discipline, author key, type, source_time, versions[(version_time, text|pdf)]
ENC_A1_SOURCES = [
    ("referral", "Outside referral letter", "other", "lee", "pdf", "08:30",
     [("08:30", ("pdf", "ENC-A1_referral_letter.pdf", text_pdf(REFERRAL_LINES)))]),
    ("adm_nursing", "Admission nursing assessment", "nursing", "tan", "pasted_text", "08:40",
     [("08:40", "Admission nursing assessment.\n"
                "Allergies: NKDA (patient reported).\n"
                "Obs on arrival: BP 132/78, HR 84, RR 16, SpO2 97% on room air, T 36.8.\n"
                "Pain 2/10. Mobilising with frame. Oriented. Family at bedside.")]),
    ("ward_round", "Ward round", "clinician", "lim", "pasted_text", "09:00",
     [("09:00", "Ward round (Dr Lim).\n"
                "Patient stable. Afebrile overnight.\n"
                "Plan:\n"
                "1. Amlodipine 5 mg OD.\n"
                "2. Metformin 500 mg BD.\n"
                "3. Blood culture sent, awaiting result.")]),
    ("medrec", "Medication reconciliation", "pharmacy", "ong", "pasted_text", "10:30",
     [("10:30", "Medication reconciliation (pharmacy).\n"
                "Allergy: Penicillin allergy \u2014 rash (per GP records).\n"
                "GP list: amlodipine 10 mg once daily; metformin 500 mg twice daily."),
      ("15:45", "Medication reconciliation (pharmacy). Amended 15:45: GP list date added.\n"
                "Allergy: Penicillin allergy \u2014 rash (per GP records).\n"
                "GP list dated 01/09/2026: amlodipine 10 mg once daily; metformin 500 mg twice daily.")]),
    ("bloods", "Blood results", "nursing", "tan", "pasted_text", "11:15",
     [("11:15", "Blood results (phoned through by lab).\n"
                "Potassium 6.4 mmol/L. Sodium 138 mmol/L.\n"
                "Not yet reviewed by medical team.")]),
    ("lab_pdf", "Scanned outside lab report", "other", "ravi", "pdf", "12:10",
     [("12:10", ("pdf", "ENC-A1_outside_lab_report_scanned.pdf", image_only_pdf()))]),
    ("obs", "Afternoon observations", "nursing", "ravi", "pasted_text", "13:00",
     [("13:00", "Afternoon observations.\n"
                "SpO2 89% on room air, RR 26.\n"
                "Patient sitting out in chair.")]),
    ("physio", "Physiotherapy mobilisation", "physiotherapy", "chen", "pasted_text", "14:00",
     [("14:00", "Physiotherapy: mobilisation.\n"
                "Walked 20 m with frame, supervision of one. Breathless on exertion, settled with rest.\n"
                "Next step: physio review tomorrow AM for stairs assessment.")]),
    ("clin_review", "Clinician review", "clinician", "lim", "pasted_text", "15:30",
     [("15:30", "Clinician review (Dr Lim).\n"
                "K 6.4 reviewed, treated per protocol.\n"
                "Repeat K sent; Dr Lim to review result by 18:00.\n"
                "Metformin increased to 1 g BD.")]),
    # Chinese characters, Hokkien POJ (combining U+030D in chia\u030dh), an astral emoji and
    # Malay precede the evidence span, to exercise code-point offsets (Section 18.3).
    ("sw", "Discharge planning", "counselling_social_work", "goh", "pasted_text", "16:00",
     [("16:00", "Discharge planning (medical social work).\n"
                "Met patient and daughter (\u5973\u513f), who prefers Hokkien: "
                "\"L\u00ed h\u00f3, chia\u030dh-p\u00e1 b\u0113?\" \U0001F642 "
                "Day centre (pusat jagaan harian) options discussed.\n"
                "Patient stable.\n"
                "Next step: SW Goh to meet family again tomorrow 10:00.")]),
]

ENC_A1_TEAM = [("lim", "responsible_clinician"), ("tan", "member"), ("ravi", "member"), ("ong", "member"),
               ("chen", "member"), ("goh", "member"), ("lee", "member")]

# ---------------------------------------------------------------------------
# ENC-B1 — another care team, same clinic (access-control tests; must not flag)
# ---------------------------------------------------------------------------

ENC_B1_SOURCES = [
    ("nursing", "Ward nursing note", "nursing", "lau", "pasted_text", "09:15",
     [("09:15", "Ward nursing note.\n"
                "Allergies: NKDA.\n"
                "Obs within normal limits overnight.\n"
                "Plan: continue current care.")]),
]
ENC_B1_TEAM = [("wong", "responsible_clinician"), ("lau", "member")]


def build_encounter(ref: str, setting: str, rc: str, team, sources) -> dict:
    enc_id = fid(f"encounter/{ref}")
    patient = {"patient_id": fid(f"patient/{ref}"), "patient_ref": fid(f"patient_ref/{ref}"),
               "display_label": f"Synthetic patient {ref[-2:]}"}
    encounter = {"encounter_id": enc_id, "encounter_ref": ref, "clinic_id": CLINIC["clinic_id"],
                 "patient_id": patient["patient_id"], "setting": setting, "started_at": sgt("08:20"),
                 "responsible_clinician_id": staff_id(rc), "attending_clinician_id": staff_id(rc)}
    memberships = [{"encounter_id": enc_id, "staff_id": staff_id(k), "team_role": r,
                    "valid_from": sgt("08:00"), "valid_to": None} for k, r in team]
    src_rows, ver_rows, ext_rows = [], [], []
    for key, title, disc, author, stype, stime, versions in sources:
        src_id = fid(f"{ref}/source/{key}")
        ext_id = f"{ref}-{key.upper()}"
        src_rows.append({"source_id": src_id, "encounter_id": enc_id, "source_system": "fixture-emr",
                         "identifier_namespace": "urn:synthetic:fixture-emr", "external_id": ext_id,
                         "source_type": stype, "author_staff_id": staff_id(author), "discipline": disc,
                         "title": title, "source_time": sgt(stime)})
        prev = None
        for n, (vtime, body) in enumerate(versions, start=1):
            vid = fid(f"{ref}/source/{key}/v{n}")
            if isinstance(body, tuple):
                _, fname, data = body
                PDF_DIR.mkdir(parents=True, exist_ok=True)
                (PDF_DIR / fname).write_bytes(data)
                text, pages, status = extract_pdf(data)
                media, extractor = "application/pdf", "pdfplumber@0.11.7"
                note = "page 1 has no text layer; manual review or approved OCR required" if status != "complete" else None
            else:
                data = body.encode("utf-8")
                text, pages, status = body, [], "not_applicable"
                media, extractor, note = "text/plain; charset=utf-8", "paste@1", None
            sha = ids.sha256_hex(data)
            ver_rows.append({"source_version_id": vid, "source_id": src_id, "version": n,
                             "version_time": sgt(vtime), "received_at": sgt(vtime), "sha256": sha,
                             "byte_length": len(data), "media_type": media,
                             "idempotency_key": ids.idempotency_key("urn:synthetic:fixture-emr", ext_id, n, sha),
                             "supersedes_version_id": prev})
            ext_rows.append({"source_version_id": vid, "status": status, "text": text, "pages": pages,
                             "extractor": extractor, "note": note})
            prev = vid
    staff_keys = sorted({k for k, _ in team})
    snap = {"clinic": CLINIC, "patient": patient, "encounter": encounter,
            "staff": [staff_record(k) for k in staff_keys], "memberships": memberships,
            "sources": src_rows, "versions": ver_rows, "extractions": ext_rows,
            "prior_flags": [], "decisions": []}
    EncounterSnapshot.model_validate(snap)  # contract check at authoring time
    return snap


def main() -> None:
    ENC_DIR.mkdir(parents=True, exist_ok=True)
    clinic = {"clinic": CLINIC, "staff": [staff_record(k) for k in STAFF]}
    (ENC_DIR / "clinic.json").write_text(json.dumps(clinic, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for ref, setting, rc, team, sources in (
        ("ENC-A1", "medical ward", "lim", ENC_A1_TEAM, ENC_A1_SOURCES),
        ("ENC-B1", "medical ward", "wong", ENC_B1_TEAM, ENC_B1_SOURCES),
    ):
        snap = build_encounter(ref, setting, rc, team, sources)
        (ENC_DIR / f"{ref}.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(ref, len(snap["sources"]), "sources,", len(snap["versions"]), "versions")


if __name__ == "__main__":
    main()
