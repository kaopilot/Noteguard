"""Aggregate risk view route (OWNER: B4 from hand-off; created by B2 as a 501 placeholder).

Two layers, both B2's: the route dependency ``authz.require_aggregate_viewer`` (aggregate roles only:
medical director, quality/risk, legal; no encounter access, no workspace) and the store-layer
re-check inside ``store.aggregate_rows``. The rows carry no content and no identifiers; bucketing,
counting and "<5" suppression are in ``noteguard.governance.aggregate`` (pure).

``ruleset_version`` is the version PINNED at generation time (governance.approval.PINNED_VERSION):
B2's rows do not carry each flag's check_version, so a view spanning a re-pin cannot split by
version (declared gap; see docs/decisions/B4.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from noteguard.contracts import routes as R
from noteguard.contracts.api_models import AggregateView
from noteguard.contracts.types import Staff
from noteguard.governance.aggregate import build_view
from noteguard.governance.approval import PINNED_VERSION

from ..authz import require_aggregate_viewer
from ..settings import utcnow

router = APIRouter()


# No response_model: declaring AggregateView would change docs/openapi.json (integrator-owned); the
# body is the same frozen AggregateView either way. Declaring it is proposed in CCR-04.
@router.get(R.AGGREGATE, response_model=None)
def aggregate(request: Request, staff: Staff = Depends(require_aggregate_viewer)) -> AggregateView:
    rows = request.app.state.store.aggregate_rows(staff)  # store-layer role re-check + audit (B2)
    return build_view(rows, now=utcnow(), ruleset_version=PINNED_VERSION)
