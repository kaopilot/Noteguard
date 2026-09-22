"""Required test 9. owner: B1 (also asserts the bubble-downgrade half of test_pdf_extraction_boundary).
The forbidden-phrase lint over backend/frontend strings is B0's tests/contract/test_forbidden_phrase_lint.py."""

import pytest

from noteguard.contracts.forbidden_phrases import find_forbidden
from noteguard.contracts.types import BubbleStatus
from tests.support import golden
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]


def _bubble(bubbles, template):
    return next(x for x in bubbles if x.question_template_id == template)


def test_question_bubble_grounding():
    """Mutation: answer absence without checking extraction status -> the 16:00 ECG bubble
    says not_documented instead of incomplete_extraction."""
    eng = engine()
    out = {}
    for name in golden.SCENARIOS:
        g, snap, b, r = golden.run(eng, name)
        bubbles = eng.answer_bubbles(snap, r, b, golden.cutoff(g))
        out[name] = (snap, bubbles)
        for x in bubbles:
            assert x.status in set(BubbleStatus)
            assert find_forbidden(x.question) is None and find_forbidden(x.uncertainty_note) is None
        assert [(x.rank, x.subject_key) for x in bubbles] == sorted((x.rank, x.subject_key) for x in bubbles)
        golden.assert_same([golden.bubble_key(x) for x in bubbles], [golden.bubble_key(x) for x in g["bubbles"]],
                           f"{name} bubbles")
    ecg_1130 = _bubble(out["ENC-A1_1130"][1], "q_ecg_documented")
    assert ecg_1130.status is BubbleStatus.NOT_DOCUMENTED_IN_SUPPLIED_SOURCES  # every in-scope source readable
    snap16, b16 = out["ENC-A1_1600"]
    ecg_1600 = _bubble(b16, "q_ecg_documented")
    assert ecg_1600.status is BubbleStatus.INCOMPLETE_EXTRACTION
    unread = {s.source_version_id for s in ecg_1600.absence.sources_searched if s.extraction_status.value == "no_text_layer"}
    pdf_versions = {e.source_version_id for e in snap16.extractions if e.status.value == "no_text_layer"}
    assert unread == pdf_versions and unread, "the unread scanned PDF must be named"
