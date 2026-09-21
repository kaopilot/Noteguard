"""Route templates (frozen, B0). The ONLY values the logger may emit as
``route_template`` (Section 10.3: never the raw path). The stub API registers
exactly these; a test asserts the registered set equals ROUTE_TEMPLATES."""

from __future__ import annotations

HEALTH = "/api/health"
SESSION = "/api/session"  # POST login (synthetic), GET current, DELETE logout
WORKSPACES = "/api/workspaces"  # POST: new per-page-load workspace
WORKSPACE_CURRENT = "/api/workspaces/current"  # DELETE: reset case
ENCOUNTERS = "/api/encounters"
ENCOUNTER = "/api/encounters/{encounter_id}"
SOURCES = "/api/encounters/{encounter_id}/sources"  # POST pasted text
SOURCES_PDF = "/api/encounters/{encounter_id}/sources/pdf"  # POST multipart PDF
SOURCE_TEXT = "/api/encounters/{encounter_id}/source-versions/{source_version_id}/text"
CHECK_RUNS = "/api/encounters/{encounter_id}/check-runs"  # POST {cutoff}
CHECK_RUN_LATEST = "/api/encounters/{encounter_id}/check-runs/latest"
FLAGS = "/api/encounters/{encounter_id}/flags"
FLAG = "/api/encounters/{encounter_id}/flags/{flag_id}"
FLAG_DECISIONS = "/api/encounters/{encounter_id}/flags/{flag_id}/decisions"
BUBBLES = "/api/encounters/{encounter_id}/bubbles"
CLOSURE = "/api/encounters/{encounter_id}/closure"  # GET view, POST attempt close
SUMMARY = "/api/encounters/{encounter_id}/summary"
DOCUMENT_TOKEN = "/api/encounters/{encounter_id}/source-versions/{source_version_id}/document-token"
DOCUMENT = "/api/documents/{document_token}"  # single-use, short-lived, no-store
FEEDBACK = "/api/encounters/{encounter_id}/feedback"
AGGREGATE = "/api/aggregate/risk"
AI_STATUS = "/api/ai/status"

ROUTE_TEMPLATES: frozenset[str] = frozenset({
    HEALTH, SESSION, WORKSPACES, WORKSPACE_CURRENT, ENCOUNTERS, ENCOUNTER, SOURCES, SOURCES_PDF,
    SOURCE_TEXT, CHECK_RUNS, CHECK_RUN_LATEST, FLAGS, FLAG, FLAG_DECISIONS, BUBBLES, CLOSURE,
    SUMMARY, DOCUMENT_TOKEN, DOCUMENT, FEEDBACK, AGGREGATE, AI_STATUS,
})

#: Header carrying the per-page-load workspace token (JS memory only; never a cookie).
WORKSPACE_HEADER = "X-Workspace-Token"
#: Identity cookie (httpOnly, SameSite=Lax, short-lived). Carries identity only.
SESSION_COOKIE = "ng_session"
#: Present on every response served by the B0 stub; B2 removes it when real routes land.
STUB_HEADER = "X-Noteguard-Stub"
