# Noteguard

A read-only reconciliation layer for one patient encounter. It cross-reads multidisciplinary notes and PDFs, raises source-grounded, owned flags (Tier 1/2/3), answers question bubbles with scoped absence statuses, and shows closure blockers and a cited one-page summary.

It is not the medical record, does not diagnose, and never closes a Tier 1 concern on its own.

**Synthetic data only. This is a demonstrator, not a production system.** It runs as a single process with in-memory, per-page-load workspaces on local HTTP. AI drafting is off. The limits are listed below and in `docs/TECHNICAL_BRIEF.md` §7.

Owner: @kaopilot. Status: integrated (CP2), with the real engine behind the API and ruleset v1 approved.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/). `uv sync` uses the pinned `uv.lock`.
- Node 22, 24 or 26 with npm; `frontend/package.json` `engines` lists exactly these. The Makefile comment says Node 22.
- Chromium for Playwright, because `make test` includes a browser smoke test.
- Setup needs network access to PyPI, the npm registry and the Playwright browser download.

## Setup

```bash
git clone <repo-url> noteguard && cd noteguard
make setup                                          # uv sync --frozen; npm ci in frontend/
(cd frontend && npx playwright install chromium)    # needed by the smoke test inside make test
```

## Test

```bash
make test
```

This runs everything: contract, engine, API, governance, the frontend Vitest suite (wrapped in pytest), the held-out ENC-A2 check and the Playwright smoke test. It takes about 45 s. It ends with a lane tally; on a clean clone expect:

```text
============================= Noteguard lane tally =============================
not implemented (lane not landed yet): 0
REAL failures: 0
setup/teardown errors: 0
...
136 passed, 1 skipped, 1 warning in ~45s
```

The one skip is a stub-only check retired when the real API landed. The warning is an upstream starlette/anyio deprecation.

| Target | Runs |
|---|---|
| `make test-contracts` | B0 contract and seam tests (`-m contract`) |
| `make test-engine` | engine tests, goldens, held-out (`-m engine`) |
| `make test-api` | API tests (`-m api`); these run the API with the stub engine; the real-engine API tests are under `make e2e` |
| `make test-governance` | approval gate, proposals, evaluation, aggregate view, AI gate (`-m governance`) |
| `make test-ui` | frontend Vitest suite (`npm test` in `frontend/`) |
| `make e2e` | real engine through the API, and the Playwright smoke test (`-m e2e`) |

The fuller browser walk (main path at 375 px and 1440 px, intake, PDF token, copy/print, install, offline shell, feedback, aggregate page) is **not** part of `make test`:

```bash
cd frontend && npm run e2e      # starts the API and a production build; ~45 s
```

Stop any `make run` first: this config reuses a server already listening on port 8000.

To check the approval evidence behind ruleset v1:

```bash
uv run python -m noteguard.governance.evaluate --baseline v1 --verify   # prints: APPROVAL_v1: consistent
```

## Run the app

```bash
make run                         # API on http://127.0.0.1:8000 (one process; restart clears everything)
cd frontend && npm run dev       # UI on http://127.0.0.1:5173, proxies /api to :8000
```

To try install and the offline shell, use a production build with the service worker instead of `npm run dev`:

```bash
cd frontend && npm run build && npm run preview   # UI on http://127.0.0.1:4173
```

Sign in from the synthetic roster; there are no passwords:

- **Dr Lim** is the responsible clinician for ENC-A1, the seed encounter.
- **Nurse Tan, Nurse Ravi, Pharmacist Ong, Physio Chen, SW Goh and Ward Clerk Lee** are on ENC-A1's care team.
- **Dr Wong** is responsible for ENC-B1, another team.
- **Dr Kaur** is on no team, so she sees no encounters.
- **Admin Siti** is a clinic admin with no clinical access.
- **Dr Rao, Koh and Menon** see the aggregate page only.

Refreshing the page or using "Reset case" starts a fresh workspace.

Run checks at 11:30 to see the unacknowledged critical potassium, and at 16:00 to see it suppressed by the later response. The seed day is 21 Sep 2026, Asia/Singapore time.

## What works and what does not

- **Works (tested):**
  - intake of pasted notes and PDFs, with immutable versions and extraction status;
  - 9 deterministic rules at a stated cutoff, with owners;
  - differencing (copied-forward vs explicit change);
  - question bubbles with scoped absence;
  - decisions with reason codes, role rules and 409 on stale revisions;
  - closure blocking;
  - a cited summary;
  - two-layer authorisation;
  - content-free logs and audit;
  - the redaction/egress gate;
  - the ruleset approval gate;
  - the aggregate view;
  - an installable PWA that never caches `/api/`.
- **Not built:**
  - rules LAT-001, META-001 and NEXT-001;
  - FHIR/SMART/HL7 adapters (mapping documented);
  - write-back;
  - a route that calls the AI drafter;
  - dismissal monitoring and a blind sample;
  - OCR and malware scanning.
- **Evidence gaps:**
  - only the accept decision is walked in a browser;
  - Edge and Safari have not been run;
  - no test checks that a note author on another team is refused.

Every claim has a row in `docs/REQUIREMENTS_TRACE.md` with its test and evidence level.

## Security posture

| Control | Status |
|---|---|
| Authentication (synthetic login; server-side session; HttpOnly cookie; revoked at logout) | implemented |
| Authorisation: care-team scope + role at the route **and** in the store (fault-injection tested) | implemented |
| `Cache-Control: private, no-store` on every API response | implemented |
| Service worker caches the static shell only, never `/api/` | implemented |
| Log and audit key allowlist; route-template request log | implemented |
| Hash-chained audit stream | implemented (not externally anchored: known gap) |
| Redaction gate before any external service | implemented (measured on a self-written set only) |
| PDF limits (10 MB, 50 pages, magic bytes, 10 s timeout) | implemented (size checked after receipt: known gap) |
| Single-process, in-memory workspace store | documented decision (production: Postgres + RLS) |
| Encryption at rest | documented decision: nothing clinical at rest (production: encrypted storage) |
| Malware scan · OCR · TLS locally · rate limiting | known gaps |

## Documents

- `docs/TECHNICAL_BRIEF.md` — the technical brief.
- `docs/REQUIREMENTS_TRACE.md` — the requirement → test → evidence ledger.
- `docs/PLAN.md`, `docs/DECISIONS.md`, `docs/RULES.md` — planning, decisions, rule catalog.
- `docs/handoffs/`, `docs/decisions/`, `docs/contract_changes/` — how the parallel build was coordinated.

## Licence

MIT (`LICENSE`). Code adapted from care-core (MIT) is listed with its notice in `THIRD_PARTY_NOTICES.md`. Dependencies and their licences are recorded in `docs/decisions/B0.md` #21, and in the lane decision files for later additions.
