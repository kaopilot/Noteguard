"""Aggregate risk view route (OWNER: B4 from hand-off; created by B2 as a 501 placeholder).

Access is already enforced here with B2's dependency ``authz.require_aggregate_viewer``
(aggregate roles only: medical director, quality/risk, legal; no encounter access, no
workspace). B4 replaces the 501 with the PHI-minimised AggregateView (no content, no patient or
encounter identifiers, small cells as "<5") and keeps the dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from noteguard.contracts import routes as R
from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.types import Staff

from ..authz import require_aggregate_viewer
from ..errors import ApiError

router = APIRouter()


@router.get(R.AGGREGATE)
def aggregate(staff: Staff = Depends(require_aggregate_viewer)):
    raise ApiError(ErrorCode.NOT_IMPLEMENTED)  # B4: not built yet (explicit, never a plausible empty view)
