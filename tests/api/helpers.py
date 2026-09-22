"""Helpers for B2's API tests (owner: B2). Synthetic data only."""

from __future__ import annotations

from noteguard.contracts import routes as R
from noteguard.contracts.api_models import PDF_FILE_FIELD
from tests.support.api import login, run_cutoff, url
from tests.support.builders import staff_id
from tests.support.golden import ROOT, load
from tests.support.lanes import client

SCAN = ROOT / "fixtures" / "pdfs" / "ENC-A1_outside_lab_report_scanned.pdf"
REFERRAL = ROOT / "fixtures" / "pdfs" / "ENC-A1_referral_letter.pdf"


def make_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF, one Helvetica text line per page ("" = a page with no text layer)."""
    font_id = 3 + 2 * len(pages)
    objects, kids = [], []
    for i, text in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        stream = (f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if text else "").encode("latin-1")
        objects.append((page_id, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
                                  f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>").encode()))
        objects.append((content_id, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
        kids.append(f"{page_id} 0 R")
    objects = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
               (2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode())] + objects + [
        (font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")]
    out, offsets = b"%PDF-1.4\n", {}
    for num, obj in objects:
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + obj + b"\nendobj\n"
    xref, n = len(out), len(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % n + b"".join(b"%010d 00000 n \n" % offsets[i] for i in range(1, n))
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xref)


def gflag(scenario: str, rule: str) -> dict:
    return next(f for f in load(scenario)["flags"] if f["rule_id"] == rule)


def session(app, staff_key: str, scenario: str | None = None):
    c = client(app)
    h = login(c, staff_key)
    if scenario:
        r = run_cutoff(c, h, load(scenario)["encounter_id"], scenario)
        assert r.status_code == 200, r.status_code
    return c, h


def decide(c, h, enc: str, flag_id: str, **body):
    return c.post(url(R.FLAG_DECISIONS, encounter_id=enc, flag_id=flag_id), headers=h, json=body)


def ctx_of(app, c, h):
    store = app.state.store
    return store.resolve_workspace(store.staff_for_session(c.cookies.get(R.SESSION_COOKIE)), h[R.WORKSPACE_HEADER])


def sources(c, h, enc: str) -> list[dict]:
    return c.get(url(R.ENCOUNTER, encounter_id=enc), headers=h).json()["sources"]


def version_with_status(c, h, enc: str, status: str) -> str:
    return next(s["note_version_id"] for s in sources(c, h, enc) if s["extraction_status"] == status)


def upload_pdf(c, h, enc: str, data: bytes, *, author: str = "lim", title: str = "Uploaded document",
               filename: str = "doc.pdf", **extra):
    return c.post(url(R.SOURCES_PDF, encounter_id=enc), headers=h,
                  files={PDF_FILE_FIELD: (filename, data, "application/pdf")},
                  data=dict(title=title, discipline="other", author_staff_id=staff_id(author),
                            source_time="2026-09-21T04:30:00Z", **extra))


def note(author: str = "lim", text: str = "Potassium 5.1 mmol/L on repeat.", **extra) -> dict:
    body = dict(title="Evening review", discipline="clinician", author_staff_id=staff_id(author),
                source_time="2026-09-21T10:00:00Z", text=text)
    body.update(extra)
    return body
