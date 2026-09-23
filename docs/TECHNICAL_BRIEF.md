# Noteguard — technical brief (scoped build)

Synthetic data only. This is a demonstrator, not a production system.

- **Evidence:** `make test` → `136 passed, 1 skipped` (B5.1, 24 Sep 2026, and a fresh clone). Every claim below has a row in `docs/REQUIREMENTS_TRACE.md`, labelled executed, inspected or not produced.
- **Owner:** @kaopilot. Assembled by B5 from the lanes' brief parts.

## 1 · Problem and thesis

One encounter's record is written by many hands in many systems, and nobody cross-reads it before handover, discharge or closure. Noteguard cross-reads it; it does not write more notes.

**Notes are code.** Every source has an author, time, system and version, so Noteguard is `git log` + `git diff` + code review for one encounter. Differencing produces a review question, never a conclusion.

> Everything that decides whether a flag exists, what tier it is, who owns it, and whether it blocks closure is deterministic, versioned and unit-tested. The application is fully functional with AI disabled. AI, if enabled, may only rank, group, or draft a citation-bound explanation over an evidence cluster the deterministic layer has already verified. It cannot create, close, re-tier or reassign a flag, cannot add a clinical entity absent from its evidence, and cannot write to any source. Its output is discarded if a validator cannot map every sentence to supplied evidence.

As built, AI is off and the whole suite runs with it off (§9).

## 2 · Architecture and flow

```text
login (synthetic roster) → per-page-load workspace (server memory; token in JS memory only)
  → intake: paste | PDF (limits, magic bytes, sha256, idempotency key) → immutable SourceVersion
                                                                          + TextExtraction status/pages
  → engine (pure Python, no I/O): statement spans → normalisation (offset map) → registry match
      with negation/uncertainty scope → differencing → 9 rules at a stated cutoff
      → flag orchestration (stable id, grouping, owner routing, supersede/reopen) → bubbles → summary
  → human decisions (compare-and-swap on revision, reason codes, role × tier rules)
  → closure view · one-page summary · content-free, hash-chained audit stream
  [AI drafting: library only, off by default, behind the redaction gate and a validator]
```

- **Stack.** Python 3.12 engine and FastAPI API, pinned through `uv.lock`; a React 19 + TypeScript + Vite PWA with a hand-written service worker.
- **One source of truth.** Enums, entities, ids, the state machine, the permission matrix, error codes, the log allowlist and the egress type are defined once in `noteguard/contracts/`; a seam test fails on any redefinition, including in the frontend. The browser never computes tier, owner, state or closure.
- **Check-run latency (measured, B5.1).** `POST check-runs` on the product app (real engine behind the approval gate) for ENC-A1 at the 16:00 cutoff: 10 sources, 6 flags. Each run used a fresh login and workspace, and only the POST was timed with `time.perf_counter`, n=100 after 5 warm-ups. Two runs gave median 26.7 ms / p95 36.2 ms and median 25.7 ms / p95 28.5 ms, on 1 vCPU, x86_64, Python 3.12.3, in-process TestClient.
- **Engine latency (B1, same method).** The engine's own triple (`run_checks` + `answer_bubbles` + `build_summary`) measured median 27.2 ms / p95 33.2 ms.

## 3 · Source and version relationships

```text
Clinic ─ Encounter ─ CareTeamMembership ─ Staff(discipline, roles)
Encounter ─< Source(namespace, external_id, type, author, discipline, source_time)
Source ─< SourceVersion(version, sha256, received_at, idempotency_key, supersedes)   immutable
SourceVersion ─ TextExtraction(status: complete|partial|no_text_layer|failed|not_applicable, page table)
SourceVersion ─< Assertion(span start/end/page, quote, subject_key, polarity, certainty, carried_forward_from)
CheckRun(cutoff, ruleset@v, registry@v, source_set_hash) ─< Flag(flag_id stable, tier, lens, owner, state, revision)
Flag ─< Evidence(note_version_id, start, end, page, quote_sha256, role) → SourceVersion
Flag ─< Decision(expected_revision, action, actor, reason_code, from→to, at)            append-only
QuestionBubble(status, evidence, cutoff, uncertainty) ── AbsenceFinding(terms, sources+status, cutoff)
Audio-ready, schema only: AudioAsset(consent) ─ Transcript(version) ─< TranscriptSegment(speaker, ms, confidence)
```

- **Identity.** `flag_id` = hash of `(rule_id, encounter_id, normalised subject)`, so reruns never duplicate a flag.
- **Offsets.** All offsets are Unicode code points into the original text. The UI converts them to UTF-16 and highlights only when the slice equals the quote. This is tested on a note with Chinese, a combining mark and an astral emoji before the span.
- **Amendments.** An EMR amendment is a new `SourceVersion`. A flag keeps citing the version it cited and shows the cited and current versions side by side.

## 4 · Check engine

- **Purity and vocabulary.** No web, file, network, clock or logging imports; every term, cue and threshold comes from the versioned registry (both tested). A NegEx-style window turns uncertain wording into `review_required`, never a reassuring negative.
- **Differencing** classifies statements as `carried_forward`, `explicit_change`, `reworded` or `new`. Explicit change language in a later clinician or pharmacy note ("increased to 1 g BD") is a change, not a conflict.

| Rule | Lens | Tier | Raises when | Owner |
|---|---|---|---|---|
| CRIT-001 | completeness | 1 | registry critical value with no later, non-carried, non-negated response for the same analyte | responsible clinician |
| ALG-001 | contradiction | 1 | NKDA/all-drug denial vs a named allergy; never settled by source priority | responsible clinician + pharmacy |
| DET-001 | continuity | 1 | reassurance after a deterioration marker with no clinician review between (CCR-02) | responsible clinician |
| OWN-001 | closure | 1 | no responsible clinician recorded; cites the care-team field | attending |
| DOSE-001 | consistency | 2 | same drug, different dose/unit/frequency, no explicit change | responsible clinician + pharmacy |
| PEND-001 | completeness | 2 | pending test/result/referral lacking an owner **or** timing | source-note owner / clinician |
| PDF-001 | completeness | 2 | page(s) without a text layer, or extraction failed/partial | uploader |
| DOSE-002 | completeness | 3 | number + dose unit not attached to a parsed regimen | source-note owner |
| DIFF-001 | continuity | 3 | copied-forward sentence with newer contradicting evidence between | source-note owner |

- **Suppression versus auto-closure (OPEN-4).**
  - If a later, new-text response exists at the cutoff, CRIT-001 is not raised.
  - Once a human could have seen the flag, a later response only moves it to `superseded`, with the response linked.
  - A superseded Tier 1 still blocks closure until the responsible clinician resolves it.
  - Copied-forward and negated "reviewed" lines never suppress.
- **Absence is a scoped search.** An `AbsenceFinding` cannot be built without its terms, sources and cutoff. "Not documented in the supplied sources" is only possible when every in-scope source was fully extracted; otherwise the answer is `incomplete_extraction` and names the unread source. A lint fails the build on "did not happen" wording anywhere.
- **Intake is as-of.** New intake is recorded at the server clock, so a run at an earlier cutoff (for example the 16:00 golden) correctly ignores a note added today. A run at "now" includes it.
- **Measured.** Engine output equals hand-written goldens by exact set equality in 5 scenarios, at engine level and through the real API. Must-not-flag cases are explicit, for example no DOSE-001 on the metformin change and no CRIT-001 at 16:00.
- **Held-out check.** ENC-A2 (different names, drugs, times and phrasing) passes 2 of 2 scenarios. Two caveats: its answer key was extended for the later-approved DET-001 after the first run (the engine was not changed), and B1 saw two of its statements afterwards, so it is only partly independent now.
- **Determinism.** Two runs of each scenario are byte-identical; B1's 34 mutation spot-checks caught 30 first time, and the 4 misses were closed.

## 5 · Ownership, decisions and closure

- **Routing.** Single-source → note owner; cross-source → responsible clinician with affected contributors listed; medication adds pharmacy; Tier 1 → responsible clinician, or the attending plus an OWN-001 flag when none is recorded.
- **Decisions.** Accept, edit, reassign, mark ready for clinician, dismiss, resolve. Each carries `expected_revision`; dismiss/resolve need a reason code from a fixed list; no bulk actions. Only the responsible clinician dismisses or resolves a Tier 1 ("staff prepare, clinicians close"). A stale revision gets 409 naming who decided first; in 20 trials of 6 simultaneous decisions exactly one succeeded each time (B2).
- **Closure.** `accepted` records responsibility, not completion: an accepted Tier 1 still blocks (OPEN-6), and so do sources newer than the last run.
- **Summary.** Every line is a cited template over flag, decision or bubble records, under "Requires human review. Not the medical record. Does not diagnose or recommend treatment."; it is marked stale when sources change after generation.

## 6 · Access enforcement, audit and provenance

- **Two layers.** Every encounter route passes a guard that checks care-team membership and role, and every store method re-checks both against the workspace's own copy.
- **Fault injection.** With the route guard removed, all 17 encounter-scoped store methods still refuse out-of-scope users, and over HTTP a nurse still cannot dismiss a Tier 1 flag.
- **No existence leaks.** Out of scope returns 404, never 403. A clinic admin and the aggregate roles have no clinical access.
- **Membership, not authorship.** Access is by care-team membership. In the fixtures, ENC-A1's authors are not on ENC-B1's team, but no test yet asserts the author case directly (trace P5).
- **Audit stream.** The security/clinical audit stream is append-only, hash-chained, and allowlisted keys only. A test detects a dropped or edited event. The chain is not externally anchored.
- **Provenance.** Content provenance is separate: Evidence → immutable SourceVersion + span, and both the engine and the API are tested to resolve every flag and claim to text whose hash matches.
- **Logs.** One allowlisted logger, route-template request lines, uvicorn access log off, error bodies `{"error_code": …}` only. Markers in body, header, query, path, cookie, a malformed request, a rationale and a PDF reached no log, error body or audit event, also against a real uvicorn server.

## 7 · Security assumptions

| Control | Status |
|---|---|
| Authentication: synthetic login, random server-side session, HttpOnly SameSite=Lax cookie, revoked at logout | implemented |
| Authorisation in two layers, with fault injection | implemented |
| `Cache-Control: private, no-store` on every API response, errors included | implemented |
| Service worker caches the static shell only; never `/api/`; offline shell says content is not stored | implemented |
| Log and audit allowlist; route-template request log | implemented |
| Hash-chained audit | implemented (not externally anchored: known gap) |
| Redaction gate before any external call (fail closed; offset map; original never modified) | implemented |
| PDF limits: 10 MB, 50 pages, magic bytes, 10 s extraction timeout | implemented (size checked after receipt; timed-out threads not killed: known gap) |
| Short-lived, single-use, staff-bound document tokens | implemented |
| Single-process, in-memory workspace store; per page load; refresh/reset clears; TTL | documented decision (OPEN-3); production: Postgres + RLS |
| Encryption at rest | documented decision: nothing clinical is at rest; production: encrypted Postgres, per-clinic keys |
| Malware scanning · governed OCR · TLS locally (`secure=False` cookie) · rate limiting | known gaps |

- **Demonstrator versus production.** One process holds everything, and a restart clears it.
- **Workspaces are per user.** Two users never see each other's decisions in the demonstrator; production shares one encounter state under the same two-layer checks.
- **Redaction measured.** On a self-written 10-item set, 1 of 19 identifiers was missed (a lower-case "dr lim") and 1 of 19 clinical strings was over-redacted ("Nurse Led Clinic"). The set is not independent evidence.
- **Redaction is not permission.** It reduces risk on the path to an external service; it does not make disclosure acceptable.

## 8 · Integration path

Read-only integration is the baseline; the FHIR R4 mapping is documented, not built:
- Patient/Encounter → context; Practitioner/PractitionerRole → Staff + discipline; CareTeam → membership.
- DocumentReference/Composition/Binary → Source/SourceVersion (`meta.versionId`, `identifier.system` as namespace, `attachment.hash`).
- Observation, DiagnosticReport, MedicationRequest, AllergyIntolerance → structured assertions; Task → pending actions and write-back; Provenance/AuditEvent → audit export.

SMART App Launch supplies patient/encounter context and identity. HL7 v2 (ORU/MDM), CDA/XDS and file drops go through adapters emitting the same canonical `SourceVersion`, with idempotency key `namespace|external_id|version|sha256` (replay and versioning tested). Write-back would be a separate Task or amendment after explicit clinician confirmation, never an edit of a source note; it is not built.

## 9 · Governance and learning

- **Nothing learns online.** Feedback (disposition, reason code, corrected owner, usefulness, measured time on screen) is stored without content and read only offline. The runtime loads a ruleset only if its approval record is approved and its hashes match, on every load; otherwise runs return 503 `ruleset_unapproved` and the UI says checks are paused.
- **Proposals.** `propose.py` refuses any proposal that lowers, disables, narrows or retires a protected rule (Tier 1, allergy, medication, critical-result, PDF).
- **Release gate.** `evaluate.py` gates releases on Tier 1 recall. Over 23 gated cases (18 hand-labelled before the engine ran on them, plus 5 goldens): Tier 1 recall 17/17, and one declared false positive (CRIT-001 precision 4/5).
- **Approved v1.** @kaopilot approved v1 as synthetic demo approver on 24 Sep and re-signed after CCR-05; `--verify` prints `consistent` (B5.1 run). A stale evaluation report is caught by the test suite and `--verify`, not at request time; this split is intended.
- **Rollback** = re-pin the previous approved version.
- **Exposure bias.** Feedback exists only for surfaced flags, so its rates say nothing about concerns never raised. Built: protected rules cannot be demoted; every rate names its denominator. Not built: a blind sample of non-flagged sources, dismissal-spike monitoring, shadow learned ranking.
- **Aggregate view** (Medical Director, Quality/Risk, Legal): counts by rule, tier, state, age and time to first decision; no text or identifiers; cells under 5 shown as "<5"; checked at route and store. Complementary suppression is a gap.
- **AI drafting.** It may draft an explanation of one flag from its verified, redacted quotes. The draft is discarded on any extra field, missing citation, entity or dose absent from the quotes, raised certainty or forbidden phrase; a timeout shows the rule text. No route calls it yet.

## 10 · What auditing care-core changed

- One allergy disagreement opened 8 cases in care-core. Here, one disagreement is one flag with many evidence pairs, and adjudication converges.
- `increased to` was read as a contradiction there; here it is a change. A dose the parser misses is never a pass (DOSE-002).
- Role rules lived only in the route; here the store re-checks, proven by fault injection.
- A denylist leaked drug and dose into logs; here there is an allowlist and a marker test, and 422s never echo input.
- Online weight updates created a governance dispute; here nothing learns at runtime, and approval is checked at load.
- A green suite hid a 500 on a primary action; here goldens are hand-written, compared by exact set, with a held-out case and a browser smoke that asserts exact text.

## 11 · Scope cuts and where this build fails first

- **Cut:** LAT-001, META-001, NEXT-001; per-source amendment Change records; FHIR/SMART/HL7 adapters; write-back; an AI route and AI ranking; dismissal monitoring and the blind sample; OCR, malware scanning, local TLS, rate limiting. UI: only the accept decision is walked in a browser, there is no focus trap in the mobile sheet, and Edge/Safari are not run.
- **Browser evidence.** B3's walk: 12/12 at 375 px and 1440 px in Chromium (B5.1 run); axe-core 0 WCAG A/AA violations in 14 states (B3, scratch run, not in the repo).
- **Fails first:** paraphrase and anything outside the registry; a one-clause, 6-token negation window; a response in the same note as a critical value (false positive); PEND-001 pairing subject and cue per statement; placeholder thresholds; no OCR; a single-process store; no real EMR connectivity; no clinical validation; labelled cases in registry vocabulary; a self-written redaction set.

## 12 · Challenged assumptions

1. **"Not documented" is a claim about a search, not the patient:** one unread PDF downgrades every absence answer to `incomplete_extraction`.
2. **Copy-forward can forge a suppression:** only new, later, non-negated text for the same analyte suppresses.
3. **Neither a model nor a rule closes a critical concern:** once seen, only a clinician closes a Tier 1, and the API refuses an engine that tries.
4. **Source versioning beats an attractive summary:** every line is cited, and flags keep the version they cited.
5. **Redaction is risk reduction, not permission:** measured both ways, fail closed.

Each is tested (trace rows 2.4, 3.8, 4.5, 5.3, 7.9).
