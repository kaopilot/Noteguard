"""Real API routes (B2) on exactly contracts.routes.ROUTE_TEMPLATES (minus AGGREGATE, see
aggregate.py). Routes are thin: authenticate, route-layer authz, parse, call the store (which
re-checks authz), return a frozen contract model."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, File, Form, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from noteguard.contracts import routes as R
from noteguard.contracts.api_models import (
    AddPdfSourceForm,
    AddTextSourceRequest,
    AIStatusView,
    BubbleList,
    CheckRunRequest,
    CheckRunView,
    DocumentTokenView,
    EncounterListItem,
    EncounterView,
    FeedbackRequest,
    FlagDetail,
    GlanceView,
    LoginRequest,
    SessionView,
    SourceText,
    SourceView,
)
from noteguard.contracts.errors import ErrorCode
from noteguard.contracts.types import (
    AIDraftStatus,
    ClosureView,
    DecisionRequest,
    FeedbackEvent,
    Flag,
    StaleRevision,
    Staff,
    Summary,
    WorkspaceInfo,
)

from .. import authz
from ..authz import AuthContext
from ..errors import ApiError
from ..store import WorkspaceStore

router = APIRouter()
Me = Annotated[Staff, Depends(authz.current_staff)]
Ctx = Annotated[AuthContext, Depends(authz.auth_context)]
Guard = Annotated[AuthContext, Depends(authz.encounter_route_guard)]


def _store(request: Request) -> WorkspaceStore:
    return request.app.state.store


def _session_view(s: Staff) -> SessionView:
    return SessionView(staff_id=s.staff_id, display_name=s.display_name, role=s.role, discipline=s.discipline)


# --- health, session, workspace -------------------------------------------------------

@router.get(R.HEALTH)
def health() -> dict:
    return {"status": "ok"}  # process is up; says nothing else


@router.post(R.SESSION, response_model=SessionView)
def login(body: LoginRequest, request: Request, response: Response):
    token, staff = _store(request).login(body.staff_id)
    response.set_cookie(R.SESSION_COOKIE, token, max_age=request.app.state.settings.session_ttl_s, path="/api",
                        httponly=True, samesite="lax", secure=False)  # secure=False: local HTTP is a declared gap
    return _session_view(staff)


@router.get(R.SESSION, response_model=SessionView)
def current_session(staff: Me):
    return _session_view(staff)


@router.delete(R.SESSION, status_code=204)
def logout(request: Request, ng_session: str | None = Cookie(default=None)):
    _store(request).logout(ng_session)  # server-side revocation, not only a cookie deletion
    out = Response(status_code=204)
    out.delete_cookie(R.SESSION_COOKIE, path="/api")
    return out


@router.post(R.WORKSPACES, response_model=WorkspaceInfo)
def new_workspace(staff: Me, request: Request):
    return _store(request).create_workspace(staff)


@router.delete(R.WORKSPACE_CURRENT, status_code=204)
def reset_workspace(ctx: Ctx, request: Request):
    _store(request).reset_workspace(ctx)
    return Response(status_code=204)


# --- encounters and sources -----------------------------------------------------------

@router.get(R.ENCOUNTERS, response_model=tuple[EncounterListItem, ...])
def list_encounters(ctx: Ctx, request: Request):
    return _store(request).list_encounters(ctx)


@router.get(R.ENCOUNTER, response_model=EncounterView)
def get_encounter(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).get_encounter(ctx, encounter_id)


@router.post(R.SOURCES, response_model=SourceView, status_code=201)
def add_text_source(encounter_id: str, body: AddTextSourceRequest, ctx: Guard, request: Request, response: Response):
    view, created = _store(request).add_text_source(ctx, encounter_id, body)
    if not created:
        response.status_code = 200  # idempotent replay: no new version
    return view


@router.post(R.SOURCES_PDF, response_model=SourceView, status_code=201)
async def add_pdf_source(encounter_id: str, ctx: Guard, request: Request, response: Response,
                         file: UploadFile = File(...), title: str = Form(...), discipline: str = Form(...),
                         author_staff_id: str = Form(...), source_time: str = Form(...),
                         source_id: str | None = Form(None), identifier_namespace: str | None = Form(None),
                         external_id: str | None = Form(None), idempotency_key: str | None = Form(None)):
    raw = dict(title=title, discipline=discipline, author_staff_id=author_staff_id, source_time=source_time)
    for name, value in (("source_id", source_id), ("identifier_namespace", identifier_namespace),
                        ("external_id", external_id), ("idempotency_key", idempotency_key)):
        if value is not None:
            raw[name] = value
    try:
        form = AddPdfSourceForm.model_validate(raw)  # the frozen form contract
    except ValidationError:
        raise ApiError(ErrorCode.VALIDATION_FAILED) from None
    data = await file.read(request.app.state.settings.pdf_max_bytes + 1)
    view, created = await run_in_threadpool(_store(request).add_pdf_source, ctx, encounter_id, form, data)
    if not created:
        response.status_code = 200
    return view


@router.get(R.SOURCE_TEXT, response_model=SourceText)
def get_source_text(encounter_id: str, source_version_id: str, ctx: Guard, request: Request):
    return _store(request).get_source_text(ctx, encounter_id, source_version_id)


# --- checks, flags, decisions, derived views -----------------------------------------

@router.post(R.CHECK_RUNS, response_model=CheckRunView)
def run_checks(encounter_id: str, body: CheckRunRequest, ctx: Guard, request: Request):
    return _store(request).run_checks(ctx, encounter_id, body.cutoff)


@router.get(R.CHECK_RUN_LATEST, response_model=CheckRunView)
def latest_run(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).latest_run(ctx, encounter_id)


@router.get(R.FLAGS, response_model=tuple[Flag, ...])
def list_flags(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).list_flags(ctx, encounter_id)


@router.get(R.FLAG, response_model=FlagDetail)
def get_flag(encounter_id: str, flag_id: str, ctx: Guard, request: Request):
    return _store(request).get_flag(ctx, encounter_id, flag_id)


_DECISION_409 = {409: {"model": StaleRevision, "description": (
    "stale_revision: StaleRevision body (current state and the other actor's decision). "
    "invalid_transition: {error_code} only; branch on error_code.")}}  # CCR-03 (approved by @kaopilot, 23 Sep 2026)


@router.post(R.FLAG_DECISIONS, response_model=FlagDetail, responses=_DECISION_409)
def decide(encounter_id: str, flag_id: str, body: DecisionRequest, ctx: Guard, request: Request):
    authz.decision_route_check(request, ctx, encounter_id, body.action)  # route layer (coarse)
    return _store(request).decide(ctx, encounter_id, flag_id, body)  # store layer (exact tier/owner rule)


@router.get(R.BUBBLES, response_model=BubbleList)
def list_bubbles(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).bubbles(ctx, encounter_id)


@router.get(R.CLOSURE, response_model=ClosureView)
def get_closure(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).closure(ctx, encounter_id)


@router.post(R.CLOSURE, response_model=ClosureView)
def attempt_close(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).attempt_close(ctx, encounter_id)


@router.get(R.GLANCE, response_model=GlanceView)
def get_glance(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).glance(ctx, encounter_id)


@router.get(R.SUMMARY, response_model=Summary)
def get_summary(encounter_id: str, ctx: Guard, request: Request):
    return _store(request).summary(ctx, encounter_id)


# --- documents, feedback, AI status ---------------------------------------------------

@router.post(R.DOCUMENT_TOKEN, response_model=DocumentTokenView)
def document_token(encounter_id: str, source_version_id: str, ctx: Guard, request: Request):
    return _store(request).issue_document_token(ctx, encounter_id, source_version_id)


@router.get(R.DOCUMENT)
def get_document(document_token: str, staff: Me, request: Request):
    """Needs the session cookie but not the workspace header (opened in a new tab); the token
    is bound to the issuing staff member and workspace and re-checked against the care team."""
    data = _store(request).read_document(staff, document_token)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="document.pdf"'})


@router.post(R.FEEDBACK, response_model=FeedbackEvent, status_code=201)
def feedback(encounter_id: str, body: FeedbackRequest, ctx: Guard, request: Request):
    return _store(request).record_feedback(ctx, encounter_id, body)


@router.get(R.AI_STATUS, response_model=AIStatusView)
def ai_status():
    return AIStatusView(status=AIDraftStatus.DISABLED, detail="AI drafting disabled")  # OPEN-5; B4 owns the module
