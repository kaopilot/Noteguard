"""STUB API routes (B0). Serves the golden fixtures on exactly contracts.routes.ROUTE_TEMPLATES
so B3 can build before B2 lands. B2 replaces this module; it is not a security layer.

What the stub does NOT do (and says so): no authorisation (every logged-in synthetic user
sees both fixture encounters), no intake, no decisions, no documents, no feedback, no
aggregate. Those return 501 {"error_code": "not_implemented"}. Every response carries
X-Noteguard-Stub: 1 so no test or reviewer can mistake stub output for the product.

It does already require the session cookie and the workspace header, and it never echoes
input in errors, so B3 builds against the real request shape.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Cookie, Header, Request, Response
from fastapi.responses import JSONResponse

from noteguard.contracts import routes as R
from noteguard.contracts.api_models import (
    AIStatusView,
    BubbleList,
    ChangeView,
    CheckRunRequest,
    CheckRunView,
    EncounterListItem,
    EncounterView,
    FlagDetail,
    FlagRevision,
    GlanceView,
    LoginRequest,
    SessionView,
    SourceText,
    SourceView,
)
from noteguard.contracts.errors import HTTP_STATUS, ErrorCode
from noteguard.contracts.types import (
    AIDraftStatus,
    ClosureView,
    EncounterSnapshot,
    Flag,
    Staff,
    Summary,
    WorkspaceInfo,
)
from noteguard.engine_stub import StubEngine, golden_names, load_golden

ROOT = Path(__file__).resolve().parents[3]
ENCOUNTERS_DIR = ROOT / "fixtures" / "encounters"

router = APIRouter()
_engine = StubEngine()
#: workspace token -> {"staff_id": str, "last": {encounter_id: scenario name}}; process memory only.
_workspaces: dict[str, dict] = {}


class StubError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code


def error_response(code: ErrorCode) -> JSONResponse:
    return JSONResponse({"error_code": code.value}, status_code=HTTP_STATUS[code])


def _snapshots() -> dict[str, EncounterSnapshot]:
    out = {}
    for p in sorted(ENCOUNTERS_DIR.glob("ENC-*.json")):
        s = EncounterSnapshot.model_validate(json.loads(p.read_text(encoding="utf-8")))
        out[s.encounter.encounter_id] = s
    return out


SNAPSHOTS = _snapshots()
STAFF: dict[str, Staff] = {s.staff_id: s for s in
                           (Staff.model_validate(x) for x in json.loads(
                               (ENCOUNTERS_DIR / "clinic.json").read_text(encoding="utf-8"))["staff"])}


def _staff(ng_session: str | None) -> Staff:
    if not ng_session or ng_session not in STAFF:
        raise StubError(ErrorCode.UNAUTHENTICATED)
    return STAFF[ng_session]


def _ws(token: str | None, staff: Staff) -> dict:
    ws = _workspaces.get(token or "")
    if ws is None or ws["staff_id"] != staff.staff_id:
        raise StubError(ErrorCode.WORKSPACE_REQUIRED)
    return ws


def _enc(encounter_id: str) -> EncounterSnapshot:
    if encounter_id not in SNAPSHOTS:
        raise StubError(ErrorCode.NOT_FOUND)
    return SNAPSHOTS[encounter_id]


def _ctx(ng_session, token, encounter_id=None):
    staff = _staff(ng_session)
    ws = _ws(token, staff)
    enc = _enc(encounter_id) if encounter_id else None
    return staff, ws, enc


def _scenario(ws: dict, encounter_id: str) -> dict:
    name = ws["last"].get(encounter_id)
    if name is None:
        raise StubError(ErrorCode.NOT_FOUND)  # no check run yet in this workspace
    return load_golden(name)


def _not_implemented() -> JSONResponse:
    return error_response(ErrorCode.NOT_IMPLEMENTED)


# --- health, session, workspace -------------------------------------------------------

@router.get(R.HEALTH)
def health() -> dict:
    return {"status": "ok", "stub": True}


@router.post(R.SESSION, response_model=SessionView)
def login(body: LoginRequest, response: Response):
    staff = _staff(body.staff_id)
    response.set_cookie(R.SESSION_COOKIE, staff.staff_id, httponly=True, samesite="lax", max_age=3600)
    return SessionView(staff_id=staff.staff_id, display_name=staff.display_name, role=staff.role,
                       discipline=staff.discipline)


@router.get(R.SESSION, response_model=SessionView)
def current_session(ng_session: str | None = Cookie(default=None)):
    s = _staff(ng_session)
    return SessionView(staff_id=s.staff_id, display_name=s.display_name, role=s.role, discipline=s.discipline)


@router.delete(R.SESSION, status_code=204)
def logout(response: Response):
    response.delete_cookie(R.SESSION_COOKIE)
    return Response(status_code=204)


@router.post(R.WORKSPACES, response_model=WorkspaceInfo)
def new_workspace(ng_session: str | None = Cookie(default=None)):
    staff = _staff(ng_session)
    token = secrets.token_urlsafe(32)
    _workspaces[token] = {"staff_id": staff.staff_id, "last": {}}
    return WorkspaceInfo(workspace_token=token, encounter_ids=tuple(SNAPSHOTS),
                         expires_at=datetime.now(timezone.utc) + timedelta(hours=8))


@router.delete(R.WORKSPACE_CURRENT, status_code=204)
def reset_workspace(ng_session: str | None = Cookie(default=None),
                    x_workspace_token: str | None = Header(default=None)):
    staff = _staff(ng_session)
    _ws(x_workspace_token, staff)
    _workspaces.pop(x_workspace_token, None)
    return Response(status_code=204)


# --- encounters and sources -----------------------------------------------------------

@router.get(R.ENCOUNTERS, response_model=tuple[EncounterListItem, ...])
def list_encounters(ng_session: str | None = Cookie(default=None),
                    x_workspace_token: str | None = Header(default=None)):
    _ctx(ng_session, x_workspace_token)
    return tuple(EncounterListItem(encounter_id=s.encounter.encounter_id, encounter_ref=s.encounter.encounter_ref,
                                   patient_label=s.patient.display_label, setting=s.encounter.setting,
                                   responsible_clinician_id=s.encounter.responsible_clinician_id)
                 for s in SNAPSHOTS.values())


def _source_views(s: EncounterSnapshot) -> tuple[SourceView, ...]:
    src = {x.source_id: x for x in s.sources}
    ext = {x.source_version_id: x for x in s.extractions}
    rows = sorted(s.versions, key=lambda v: (src[v.source_id].source_time, v.received_at, v.source_version_id))
    return tuple(SourceView(source_id=v.source_id, note_version_id=v.source_version_id, version=v.version,
                            supersedes_version_id=v.supersedes_version_id, title=src[v.source_id].title,
                            source_type=src[v.source_id].source_type, discipline=src[v.source_id].discipline,
                            author_staff_id=src[v.source_id].author_staff_id, source_time=src[v.source_id].source_time,
                            version_time=v.version_time, received_at=v.received_at, sha256=v.sha256,
                            extraction_status=ext[v.source_version_id].status,
                            extraction_note=ext[v.source_version_id].note,
                            page_count=len(ext[v.source_version_id].pages)) for v in rows)


@router.get(R.ENCOUNTER, response_model=EncounterView)
def get_encounter(encounter_id: str, ng_session: str | None = Cookie(default=None),
                  x_workspace_token: str | None = Header(default=None)):
    _, _, s = _ctx(ng_session, x_workspace_token, encounter_id)
    return EncounterView(encounter=s.encounter, patient_label=s.patient.display_label, staff=s.staff,
                         memberships=s.memberships, sources=_source_views(s))


@router.post(R.SOURCES)
def add_text_source(encounter_id: str):
    return _not_implemented()


@router.post(R.SOURCES_PDF)
def add_pdf_source(encounter_id: str):
    return _not_implemented()


@router.get(R.SOURCE_TEXT, response_model=SourceText)
def get_source_text(encounter_id: str, source_version_id: str, ng_session: str | None = Cookie(default=None),
                    x_workspace_token: str | None = Header(default=None)):
    _, _, s = _ctx(ng_session, x_workspace_token, encounter_id)
    ext = next((e for e in s.extractions if e.source_version_id == source_version_id), None)
    if ext is None:
        raise StubError(ErrorCode.NOT_FOUND)
    return SourceText(note_version_id=ext.source_version_id, extraction_status=ext.status, text=ext.text,
                      pages=ext.pages)


# --- checks, flags, bubbles, closure, summary -----------------------------------------

def _run_view(g: dict) -> CheckRunView:
    return CheckRunView(run=g["run"], flags=tuple(Flag.model_validate(f) for f in g["flags"]),
                        changes=tuple(ChangeView.model_validate(c) for c in g["required_changes"]))


@router.post(R.CHECK_RUNS, response_model=CheckRunView)
def run_checks(encounter_id: str, body: CheckRunRequest, ng_session: str | None = Cookie(default=None),
               x_workspace_token: str | None = Header(default=None)):
    _, ws, s = _ctx(ng_session, x_workspace_token, encounter_id)
    prior_name = ws["last"].get(encounter_id)
    prior = tuple(Flag.model_validate(f) for f in load_golden(prior_name)["flags"]) if prior_name else ()
    snapshot = s.model_copy(update={"prior_flags": prior})
    try:
        _engine.run_checks(snapshot, None, body.cutoff, run_id="stub", evaluated_at=body.cutoff)  # type: ignore[arg-type]
    except NotImplementedError:
        return _not_implemented()
    name = next(n for n in golden_names()
                if load_golden(n)["encounter_id"] == encounter_id
                and datetime.fromisoformat(load_golden(n)["cutoff"]) == body.cutoff
                and load_golden(n)["prior_scenario"] == prior_name)
    ws["last"][encounter_id] = name
    return _run_view(load_golden(name))


@router.get(R.CHECK_RUN_LATEST, response_model=CheckRunView)
def latest_run(encounter_id: str, ng_session: str | None = Cookie(default=None),
               x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    return _run_view(_scenario(ws, encounter_id))


@router.get(R.FLAGS, response_model=tuple[Flag, ...])
def list_flags(encounter_id: str, ng_session: str | None = Cookie(default=None),
               x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    return tuple(Flag.model_validate(f) for f in _scenario(ws, encounter_id)["flags"])


def _revisions(g: dict, flag_id: str) -> tuple[FlagRevision, ...]:
    chain = []
    while g is not None:
        chain.insert(0, g)
        g = load_golden(g["prior_scenario"]) if g["prior_scenario"] else None
    out: dict[int, FlagRevision] = {}
    for sc in chain:
        for f in sc["flags"]:
            if f["flag_id"] == flag_id and f["revision"] not in out:
                out[f["revision"]] = FlagRevision(revision=f["revision"], evidence_revision=f["evidence_revision"],
                                                  state=f["state"], owner_staff_id=f["owner_staff_id"],
                                                  evidence=f["evidence"], run_id=sc["run_id"], decision_id=None,
                                                  at=sc["evaluated_at"])
    return tuple(out[k] for k in sorted(out))


@router.get(R.FLAG, response_model=FlagDetail)
def get_flag(encounter_id: str, flag_id: str, ng_session: str | None = Cookie(default=None),
             x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    g = _scenario(ws, encounter_id)
    f = next((f for f in g["flags"] if f["flag_id"] == flag_id), None)
    if f is None:
        raise StubError(ErrorCode.NOT_FOUND)
    return FlagDetail(flag=f, revisions=_revisions(g, flag_id), decisions=())


@router.post(R.FLAG_DECISIONS)
def decide(encounter_id: str, flag_id: str):
    return _not_implemented()


@router.get(R.BUBBLES, response_model=BubbleList)
def list_bubbles(encounter_id: str, ng_session: str | None = Cookie(default=None),
                 x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    g = _scenario(ws, encounter_id)
    return BubbleList(cutoff=g["cutoff"], bubbles=g["bubbles"], ai_status=AIDraftStatus.DISABLED)


@router.get(R.CLOSURE, response_model=ClosureView)
def get_closure(encounter_id: str, ng_session: str | None = Cookie(default=None),
                x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    return ClosureView.model_validate(_scenario(ws, encounter_id)["closure"])


@router.post(R.CLOSURE)
def attempt_close(encounter_id: str):
    return _not_implemented()


@router.get(R.GLANCE, response_model=GlanceView)
def get_glance(encounter_id: str, ng_session: str | None = Cookie(default=None),
               x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    return GlanceView.model_validate(_scenario(ws, encounter_id)["glance"])


@router.get(R.SUMMARY, response_model=Summary)
def get_summary(encounter_id: str, ng_session: str | None = Cookie(default=None),
                x_workspace_token: str | None = Header(default=None)):
    _, ws, _ = _ctx(ng_session, x_workspace_token, encounter_id)
    return Summary.model_validate(_scenario(ws, encounter_id)["summary"])


# --- not built in the stub ------------------------------------------------------------

@router.post(R.DOCUMENT_TOKEN)
def document_token(encounter_id: str, source_version_id: str):
    return _not_implemented()


@router.get(R.DOCUMENT)
def get_document(document_token: str):
    return _not_implemented()


@router.post(R.FEEDBACK)
def feedback(encounter_id: str):
    return _not_implemented()


@router.get(R.AGGREGATE)
def aggregate():
    return _not_implemented()


@router.get(R.AI_STATUS, response_model=AIStatusView)
def ai_status():
    return AIStatusView(status=AIDraftStatus.DISABLED, detail="AI drafting disabled")


def install_error_handlers(app) -> None:
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(StubError)
    async def _stub_error(request: Request, exc: StubError):
        return error_response(exc.code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return error_response(ErrorCode.VALIDATION_FAILED)  # never echo input (L20)
