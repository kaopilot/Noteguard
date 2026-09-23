"""PDF intake (B2; Section 10.2): size limit, magic bytes, page limit, extraction with a timeout.

Extraction reproduces the pdfplumber contract pinned by
tests/contract/test_golden_fixtures.py::test_fixture_pdfs_extract_as_recorded: per-page
``extract_text() or ""``, pages joined by "\\n", document-global code-point offsets with a page
table; status no_text_layer if every page is empty, partial if some are, else complete.
A PDF that cannot be parsed is RETAINED with status failed. No OCR (declared gap).

Known limits: the size limit is checked after the upload is received (ingress must cap body
size in production); a timed-out extraction keeps running in its worker thread (it cannot be
killed) while the request returns; no malware scan (declared gap).
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass

import pdfplumber

from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.types import ExtractionStatus, PageSpan, TextExtraction

PDF_MEDIA_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"
PDF_EXTRACTOR = f"pdfplumber@{pdfplumber.__version__}"
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="noteguard-pdf")

NOTE_NO_TEXT = "no page has a text layer; OCR or manual review required"
NOTE_FAILED = "text extraction failed; source retained; OCR or manual review required"
NOTE_TIMEOUT = "text extraction timed out; source retained; OCR or manual review required"


class PdfRejected(Exception):
    """The upload is refused and NOT retained (size, type, page count)."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class PdfExtraction:
    text: str
    pages: tuple[PageSpan, ...]
    status: ExtractionStatus
    note: str | None
    timed_out: bool = False

    def to_extraction(self, version_id: str) -> TextExtraction:
        return TextExtraction(source_version_id=version_id, status=self.status, text=self.text, pages=self.pages,
                              extractor=PDF_EXTRACTOR, note=self.note)


def check_bytes(data: bytes, *, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise PdfRejected(ErrorCode.PDF_TOO_LARGE)
    if not data.startswith(PDF_MAGIC):
        raise PdfRejected(ErrorCode.PDF_NOT_A_PDF)


def _extract(data: bytes, max_pages: int) -> PdfExtraction:
    texts: list[str] = []
    pages: list[PageSpan] = []
    pos = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) > max_pages:
            raise PdfRejected(ErrorCode.PDF_TOO_MANY_PAGES)
        for n, page in enumerate(pdf.pages, start=1):
            t = page.extract_text() or ""
            if n > 1:
                pos += 1  # "\n" page separator
            pages.append(PageSpan(page=n, start=pos, end=pos + len(t), char_count=len(t)))
            texts.append(t)
            pos += len(t)
    empty = [p.page for p in pages if p.char_count == 0]
    if len(empty) == len(pages):
        status, note = ExtractionStatus.NO_TEXT_LAYER, NOTE_NO_TEXT
    elif empty:
        status = ExtractionStatus.PARTIAL
        note = f"page(s) {', '.join(map(str, empty))} have no text layer; OCR or manual review required"
    else:
        status, note = ExtractionStatus.COMPLETE, None
    return PdfExtraction("\n".join(texts), tuple(pages), status, note)


def extract(data: bytes, *, max_pages: int, timeout_s: float) -> PdfExtraction:
    future = _POOL.submit(_extract, data, max_pages)
    try:
        return future.result(timeout=timeout_s)
    except FuturesTimeout:
        return PdfExtraction("", (), ExtractionStatus.FAILED, NOTE_TIMEOUT, timed_out=True)
    except PdfRejected:
        raise
    except Exception:  # noqa: BLE001 - unparseable PDF: retained, status failed, nothing about it logged
        return PdfExtraction("", (), ExtractionStatus.FAILED, NOTE_FAILED)
