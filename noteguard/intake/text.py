"""Pasted-text intake: the text IS the source, so extraction status is not_applicable."""

from __future__ import annotations

from noteguard.contracts.types import ExtractionStatus, TextExtraction

TEXT_MEDIA_TYPE = "text/plain; charset=utf-8"
PASTE_EXTRACTOR = "paste@1"


def text_extraction(version_id: str, text: str) -> TextExtraction:
    return TextExtraction(source_version_id=version_id, status=ExtractionStatus.NOT_APPLICABLE, text=text, pages=(),
                          extractor=PASTE_EXTRACTOR)
