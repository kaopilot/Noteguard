"""Required test 7 (bonus). owner: B1; I1 repeats it through the API."""

import pytest

from noteguard.contracts import ids
from noteguard.contracts.spans import statement_at
from tests.support import golden
from tests.support.lanes import engine

pytestmark = [pytest.mark.owner("B1"), pytest.mark.engine]


@pytest.mark.parametrize("name", golden.SCENARIOS)
def test_grounding(name):
    """Mutation: keep offsets into normalised text instead of the original -> the quote check
    fails on the multilingual 16:00 note."""
    eng = engine()
    g, snap, b, r = golden.run(eng, name)
    bubbles = eng.answer_bubbles(snap, r, b, golden.cutoff(g))
    summary = eng.build_summary(snap, r, bubbles, (), b, golden.cutoff(g), generated_at=golden.evaluated_at(g))
    ext = {e.source_version_id: e for e in snap.extractions}
    items = ([(f"flag {f.rule_id.value}", e) for f in r.flags for e in f.evidence]
             + [(f"bubble {x.question_template_id}", e) for x in bubbles for e in x.evidence]
             + [(f"claim {c.template.value}", e) for c in summary.claims for e in c.evidence])
    assert items or not g["flags"]
    for label, e in items:
        assert e.source_version_id in ext, f"{label}: cites an unknown SourceVersion"
        x = ext[e.source_version_id]
        assert x.text[e.start:e.end] == e.quote, f"{label}: quote does not match the cited span"
        assert e.quote_sha256 == ids.quote_sha256(e.quote)
        if e.role_in_flag.value != "extraction_gap":
            assert statement_at(x.text, e.start, e.end), f"{label}: not a statement span"
        assert (e.page is not None) == bool(x.pages), f"{label}: page must be set exactly for paged sources"
    for a in r.assertions:
        assert ext[a.source_version_id].text[a.span.start:a.span.end] == a.quote
