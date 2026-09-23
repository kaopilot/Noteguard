# Requirements trace (B5; the honest ledger)

Every row names the requirement, where it is tested or built, the evidence level and a status.
Owner of this file: B5. Last updated in session B5.1, 24 Sep 2026, on `main` eff8608 (after I1 / CP2).

## Evidence runs this trace rests on

| Run | Command | Result |
|---|---|---|
| R1, B5.1 baseline | `make setup && make test` | setup exit 0; `136 passed, 1 skipped, 1 warning in 45.67s`; tally: not implemented 0 · REAL failures 0 · setup/teardown errors 0 |
| R2, B5.1 per-test | `uv run pytest -q -rA --junitxml=<tmp>` | `136 passed, 1 skipped, 1 warning in 43.23s`. The one skip is `test_stub_serves_goldens` (retired by design when the real API landed, decisions/B0.md #18). **Every test id cited below passed in R1 and R2.** |
| R3, approval evidence | `uv run python -m noteguard.governance.evaluate --baseline v1 --verify` | `APPROVAL_v1: consistent` |
| R4, UI walk (not in `make test`) | `cd frontend && npm run e2e` | See the B5.1 handoff for the recorded result |
| R5, fresh clone | clone → README steps → `make test` | See the B5.1 handoff for the recorded output |

**Evidence levels.** **E** = executed (a test that applies an input and observes behaviour, green in R1/R2). **E-lane** = executed by a lane outside `make test`, quoted from its handoff. **I** = inspected (code or data read, no test). **NP** = not produced (reason given).
**Status.** **holds** / **partial** (what is missing is stated) / **not built**.

Two caveats apply to every API row:
- B2's API tests run through `tests.support.lanes.real_app()`, which wires the **stub engine**; they prove the API layer.
- The real engine behind the API is evidenced by I1's `tests/e2e/test_api_real_engine.py` (5 tests) and `tests/e2e/test_e2e_smoke.py` (decisions/I1.md #26).

Test paths below are abbreviated: `api/` = `tests/api/`, `eng/` = `tests/engine/`, and so on.

## A · Builder Brief (`NOTEGUARD_BUILDER_BRIEF.md`), sections 1–8

| # | Requirement | Where tested / built | Ev. | Status |
|---|---|---|---|---|
| 1.1 | Unit of work is one patient encounter | encounter-scoped routes; `api/test_api_behaviour.py::test_golden_views_through_api`; `api/test_access_control.py` | E | holds |
| 1.2 | Records from clinician, nursing, physiotherapy, counselling/social work, pharmacy, other | `Discipline` enum (`contracts/types.py`); ENC-A1 carries all six and runs in `eng/test_golden_engine.py[ENC-A1_1600]` | E + I | holds |
| 1.3 | Each record shows context, author/discipline, source time, type, immutable id/version, text or PDF | summary `timeline` equals the golden in `test_golden_views_through_api` and `e2e/test_api_real_engine.py::test_golden_scenarios_through_real_api`; UI rows in `frontend/tests/intake.test.tsx` (inside `ui/test_ui_frontend.py::test_frontend_suite_all_green`) and R4 | E | holds |
| 1.4 | Chronological inventory | order `(source_time, received_at, source_version_id)` (build context 18.3); timeline compared to the golden (as 1.3) | E | holds |
| 2.1 | Pasted text and PDFs with selectable-text extraction | `api/test_api_behaviour.py::test_paste_intake_versions_and_idempotency`, `::test_pdf_intake_boundaries`, `::test_pdf_extraction_reproduces_pinned_contract` | E | holds |
| 2.2 | Provenance to the exact version; character offsets; PDF page refs and extraction status | `eng/test_grounding.py` ×5; `e2e/test_api_real_engine.py::test_grounding_through_real_api`; `contract/test_spans.py::test_offsets_are_code_points_not_utf16`; `test_pdf_intake_boundaries` (page offsets) | E | holds |
| 2.3 | Source versions immutable; new content is a new row | `test_paste_intake_versions_and_idempotency` (mutation "overwrite in place" fails it) | E | holds |
| 2.4 | Scanned/unreadable/partial PDF never looks complete; retained; limitation stated; actionable issue | `api/test_pdf_extraction_boundary.py`; `test_pdf_intake_boundaries` (unparseable PDF retained as `failed`); `e2e/test_api_real_engine.py::test_pdf001_on_failed_extraction_without_page_table`; `eng/test_question_bubble_grounding.py` (ECG bubble → `incomplete_extraction`) | E | holds |
| 3.1 | Checks at a defined source cutoff; cutoff and escalation explicit | cutoff: golden runs at 11:30 and 16:00, `test_api_behaviour.py::test_cutoff_moves_forward_only`. Escalation is in-workspace only: Tier 1 blocks closure (`::test_closure_attempt_and_decision_effect`); the UI runs checks after each intake (R4). No paging or scheduled overnight mode (stated in the brief) | E | holds (in-workspace escalation only) |
| 3.2 | Deterministic-first: normalise, diff, reconcile, independently testable checks | `eng/test_lessons_engine.py::test_engine_is_pure`, `::test_single_term_registry`; per-rule tests; `eng/test_golden_engine.py` ×5 (exact set equality); held-out `eng/test_heldout_golden.py` ×2 | E | holds |
| 3.3 | Diff each new version against prior versions and encounter facts | cross-source differencing: `eng/test_differencing.py`. Per-source amendments emit **no** Change records and no `removed` changes; they surface as `source_changed_since_flag` with cited and current side by side (`eng/test_lessons_engine.py::test_cited_source_edited_side_by_side`) | E | partial |
| 3.4 | Every issue has tier, category, reason, evidence, owner, check version, creation time | every flag field compared in `test_golden_scenarios_through_real_api`; wire shape in `contract/test_stub_api_contract.py::test_openapi_export_in_sync`, `contract/test_generated_types.py` | E | holds |
| 3.5 | Five lenses | `Lens` enum has all five; v1 uses consistency (DOSE-001), continuity (DIFF-001, DET-001), completeness (CRIT-001, DOSE-002, PEND-001, PDF-001), contradiction (ALG-001), closure (OWN-001); lens compared per flag in the goldens | E + I | holds |
| 3.6 | Three tiers with default actions | Tier 1 blocks closure (`contract/test_contract_states_permissions.py::test_blocks_closure_truth_table`, `test_closure_attempt_and_decision_effect`); owners per tier in the goldens; Tier 3 appears as a count with a "Review Tier 3 items" link in the closure view (`frontend/src/components/Closure.tsx`) | E + I | holds |
| 3.7 | ≥ 4 distinct Tier 1/2 concerns incl. critical obs., cross-note conflict, pending w/o owner+timing, unreadable PDF | CRIT-001 (T1), ALG-001 (T1), DET-001 (T1), OWN-001 (T1), DOSE-001 (T2), PEND-001 (T2), PDF-001 (T2): required tests P1–P4 below, `eng/test_det_001.py` ×11, goldens | E | holds |
| 3.8 | Conservative; a later documented response suppresses an obsolete critical flag | `eng/test_critical_observation_routing.py` (earlier, carried-forward and negated "reviewed" do not suppress); `test_critical_observation_routing_real_api`. Known false positive: a response in the same note does not suppress (`eng/test_engine_edges.py::test_engine_edge[same_statement_response_is_not_later]`) | E | holds |
| 3.9 | Do not infer events absent from the record | `contract/test_forbidden_phrase_lint.py` ×2; `test_question_bubble_grounding`; `governance/test_governance.py::test_ai_output_validator_rejects_new_entity` | E | holds |
| 4.1 | Owner routing: note owner / responsible clinician / pharmacy; Tier 1 never unassigned | owners and affected contributors compared exactly in the goldens; `eng/test_cross_note_conflicts.py` (pharmacy); `test_critical_observation_routing_real_api`; ENC-C1 golden (no responsible clinician → attending + OWN-001) | E | holds |
| 4.2 | Inspect evidence, accept, dismiss with reason, reassign, edit with rationale, resolve | API: `test_api_behaviour.py::test_decision_field_rules`, `api/test_lessons_api.py::test_decision_requires_reason_code`, `::test_role_matrix_staff_prepare_clinician_close`. Browser: only **accept** is walked end to end (R4, smoke); other decision paths in the UI are inspected (B3 handoff) | E (API) / I (UI) | holds (API); partial (UI) |
| 4.3 | Distinct lifecycle states open/accepted/edited/dismissed/resolved/superseded | `FlagState` enum; `test_blocks_closure_truth_table`; `contract/test_contract_states_permissions.py::test_engine_never_targets_human_states` | E | holds |
| 4.4 | Accepting records responsibility, not completion | accepted Tier 1 still blocks: `test_blocks_closure_truth_table`; `e2e/test_e2e_smoke.py` (mutation "accepted no longer blocks" fails it); `test_open_count_integrity_real_api` (after an accept) | E | holds |
| 4.5 | Never auto-close a Tier 1 concern | `eng/test_lessons_engine.py::test_tier1_never_auto_closed`; `test_api_behaviour.py::test_engine_contract_guard` (API refuses an engine result that moves a flag into a human-only state); `eng/test_det_001.py::test_det_001_shape_owner_and_supersede` | E | holds |
| 5.1 | Open Tier 1 blocks closure; Tier 2 prominent; decisions show owner, rationale, time | `test_closure_attempt_and_decision_effect`; `tier1_blockers` and `tier2_open` compared as sets in `test_golden_scenarios_through_real_api`; decision record fields in `test_decision_field_rules`. Free-text rationale is held in memory only; the stored decision carries the reason code | E | holds |
| 5.2 | Timestamped, copyable/exportable one-page summary with context, cutoff, timeline, open T1/T2, decisions, human-review statement | content equals the golden (`test_golden_views_through_api`, real-engine API test); exact human-review statement asserted in `test_e2e_smoke`; copy and print layout in R4 | E | holds |
| 5.3 | Every derived claim resolves to its sources | `eng/test_grounding.py` ×5; `test_grounding_through_real_api` | E | holds |
| 5.4 | Summary does not diagnose, prescribe or become the record | claims are templates over flag, decision and bubble records (engine `summary.py`, inspected); forbidden-phrase lint | E + I | holds |
| 5.5 | Summary marked stale when sources change after generation | `test_closure_attempt_and_decision_effect` (`stale_after_source_change` is true after a new source). The engine never sets it; the API does | E | holds |
| 6.1 | Deterministic, tappable question bubbles from unresolved states | bubbles compared exactly in the goldens; `test_question_bubble_grounding`; tapping in R4 | E | holds |
| 6.2 | Status is one of the five, with evidence, cutoff, uncertainty | `test_question_bubble_grounding` | E | holds |
| 6.3 | Never "did not happen" for absent documentation | `test_forbidden_phrase_lint` (backend and frontend strings); `test_question_bubble_grounding` | E | holds |
| 6.4 | AI only ranks, groups or drafts over verified evidence; cannot diagnose, close or add claims | drafting module off by default with validator, timeout and fallback: `governance/test_governance.py::test_ai_disabled_by_default`, `::test_ai_timeout_falls_back`, `::test_ai_output_validator_rejects_new_entity`. **No route calls the drafter**; AI ranking and grouping are not built (ranking is deterministic) | E | partial (by design; ships disabled) |
| 6.5 | No patient text to an external knowledge service without an approved redaction boundary | no external service is called; the egress gate refuses an unqualified payload (`api/test_log_and_redaction_safety.py`). Curated external references: not built | E | holds |
| 7.1 | Synthetic data only | fixtures ENC-A1, ENC-B1, ENC-C1 and held-out ENC-A2 are fictional | I | holds |
| 7.2 | Demonstrator keeps content in (browser) memory; nothing persisted; refresh/reset clears | **Documented deviation (OPEN-3):** content lives in a server-side per-page-load workspace in process memory (never on disk), keyed by a token held only in JS memory, so authorisation can be server-side. `test_api_behaviour.py::test_session_and_workspace_isolation`, `::test_config_key_changes_behaviour[workspace_ttl_s]`; `ui/test_ui_frontend.py::test_no_clinical_data_in_browser_storage`. "Never on disk" is inspected | E + I | partial (documented decision) |
| 7.3 | No clinical content in URLs, analytics, logs, browser persistence, SW caches | `test_api_behaviour.py::test_marker_never_logged_or_echoed`, `::test_request_log_uses_route_template_and_access_log_is_off`, `::test_unhandled_exception_is_bare_500`; `ui/test_ui_frontend.py::test_sw_never_caches_api`, `::test_no_clinical_data_in_browser_storage`. No analytics exists (I) | E | holds |
| 7.4 | Server-side encounter and care-team authorisation | `api/test_access_control.py`; `api/test_lessons_api.py::test_store_layer_authz_fault_injection` | E | holds |
| 7.5 | Immutable source versions; structured content-free audit | 2.3; `api/test_lessons_api.py::test_audit_allowlist` (allowlist + hash chain; tamper detected) | E | holds |
| 7.6 | Encrypted approved storage; short-lived document access | document tokens: `test_api_behaviour.py::test_document_token_single_use_bound_and_scoped`, `::test_config_key_changes_behaviour[document_token_ttl_s]`. Encryption at rest: **NP** (nothing clinical at rest by design; production path in the brief) | E / NP | partial |
| 7.7 | Safe PDF extraction; malware scanning; governed OCR | size, page, magic-byte and timeout limits: `test_pdf_intake_boundaries`, `test_config_key_changes_behaviour[pdf_*]` ×3. Malware scan and OCR: **not built** (known gaps) | E | partial |
| 7.8 | Versioned checks and source provenance | `check_version` on every flag (goldens); `governance/test_governance.py::test_unapproved_ruleset_refused`, `::test_approval_verify_and_offline_clis`; R3 | E | holds |
| 7.9 | Approved redaction boundary before any external service | `api/test_log_and_redaction_safety.py`; `test_api_behaviour.py::test_redaction_offsets_residual_scan_and_eval` | E | holds |
| 7.10 | Read-only baseline; write-back only as a separate artefact after human confirmation | no write-back route exists (`contract/test_stub_api_contract.py::test_registered_routes_equal_contract` pins the route set). The write-back artefact/Task is **not built** (brief §8) | E / not built | holds (read-only); write-back not built |
| 7.11 | FHIR R4 / SMART design; HL7 v2, CDA/XDS, file adapters; namespace, version, checksum, idempotency | canonical fields and idempotency key: `test_paste_intake_versions_and_idempotency`. FHIR/SMART/HL7 adapters: **not built** (mapping in the brief) | E / not built | partial |
| 7.12 | No audio capture; schema audio-ready | no audio code; `AudioAsset`, `Transcript`, `TranscriptSegment` with the listed fields in `contracts/types.py`. No test constructs them | I | holds (inspected) |
| 8.1 | Measure actionability, false positives, missed concerns, owner response time, disposition | `governance/test_governance.py` (B4, 9 tests): per-rule rates with denominators (actionability, dismissal, missing-rule reports, disposition mix); owner response time in the aggregate view (`::test_aggregate_no_content_or_ids`, CCR-04); precision/recall vs labelled cases (`::test_eval_report_tier1_recall_gate`). Blind sample of non-flagged sources: **NP** | E / NP | partial |
| 8.2 | Adjust, switch off or retire rules under governed change control | `::test_protected_floor_refused`, `::test_eval_report_tier1_recall_gate`, `::test_unapproved_ruleset_refused`; rollback = re-pin (I). Monitored release (dismissal-spike monitoring): **NP** | E / NP | partial |
| 8.3 | Store acceptance, dismissal, edits, corrected ownership, rationale, usefulness | `test_api_behaviour.py::test_feedback_capture`; UI in `frontend/tests/feedback.test.tsx`. Rationale free text is not stored by design (reason code is) | E | holds |
| 8.4 | Offline proposals only; nothing changes a production rule automatically | `governance/test_governance.py::test_no_runtime_rule_mutation` | E | holds |
| 8.5 | PHI-minimised aggregate view for Medical Director, Quality/Risk, Legal | `::test_aggregate_no_content_or_ids`; `test_api_behaviour.py::test_aggregate_route_behind_b2_authz`. Complementary small-cell suppression: **NP** | E | holds (primary suppression only) |

## B · Required proof (Builder Brief) = appendix micro-tests 1–9

| # | Proof | Test (owner) | Ev. | Status |
|---|---|---|---|---|
| P1 | K 6.4 nursing note → Tier 1 clinician-owned; later review suppresses | `eng/test_critical_observation_routing.py` (B1); `e2e/test_api_real_engine.py::test_critical_observation_routing_real_api` (I1) | E | holds |
| P2 | NKDA vs penicillin → Tier 1 with evidence from both; two doses → Tier 2 | `eng/test_cross_note_conflicts.py` (B1; dose-phrasing variants and fan-out shape) | E | holds |
| P3 | Pending result lacking owner or deadline flagged; both present → no flag | `eng/test_pending_owner_and_time.py` (B1) | E | holds |
| P4 | PDF without selectable text retained and flagged for review/OCR | `api/test_pdf_extraction_boundary.py` (B2); `test_pdf001_on_failed_extraction_without_page_table` (I1) | E | holds |
| P5 | No access outside scope; no decision without role | `api/test_access_control.py` (B2, incl. store-layer and HTTP fault injection); `api/test_lessons_api.py::test_store_layer_authz_fault_injection`. **Gap:** "a note author does not automatically gain access" holds by design (access is care-team membership), and ENC-A1 authors are not on ENC-B1's team, but no test refuses an author of one encounter access to another; the tests use a clinician on no team and a clinic admin | E / I | holds; author case partial |
| P6 | Raw identifiers never logged; external input redacted | `api/test_log_and_redaction_safety.py`; `test_api_behaviour.py::test_marker_never_logged_or_echoed`. No external service is called, so redaction is tested in isolation (the appendix allows this) | E | holds |
| P7 | Every flag and summary claim resolves to a version and span (`test_grounding`, bonus) | `eng/test_grounding.py` ×5 (B1); `test_grounding_through_real_api` (I1) | E | holds |
| P8 | Changed or copied-forward note → grounded question; legitimate change is not a contradiction | `eng/test_differencing.py`; `eng/test_lessons_engine.py::test_change_not_contradiction` (B1) | E | holds (cross-source; see 3.3) |
| P9 | Bubble returns only a permitted status and evidence; never "did not happen" | `eng/test_question_bubble_grounding.py` (B1); `contract/test_forbidden_phrase_lint.py` (B0) | E | holds |

## C · Appendix items beyond the Builder Brief

| Item | Where | Ev. | Status |
|---|---|---|---|
| Tier 1 example: deterioration vs reassuring/discharge assessment | DET-001, `eng/test_det_001.py` ×11, goldens (CCR-02) | E | holds |
| Tier 1 example: laterality conflict | LAT-001 disabled in v1, not built | NP | not built |
| Tier 3 examples: copied-forward / no next step / incomplete metadata | DIFF-001 built (`test_differencing`); NEXT-001 and META-001 disabled, not built | E / NP | partial |
| Flag JSON field names exactly (`flag_id`, `note_version_id`, …) | `test_golden_scenarios_through_real_api`; `test_openapi_export_in_sync` | E | holds |
| Two audit concepts (security audit stream; content provenance) | `test_audit_allowlist`; `eng/test_grounding.py`, `test_grounding_through_real_api` | E | holds |
| TLS in transit | local HTTP; cookie `secure=False` | NP | known gap |
| `Cache-Control: private, no-store` on authenticated responses | `api/test_lessons_api.py::test_no_store_headers` (every response, errors included) | E | holds |
| Installable, responsive PWA; mobile first-class; no offline clinical cache | `test_sw_never_caches_api`; installability, offline shell and 375 px walk in R4 (Chromium only). Edge and Safari: **NP** (not available in the build container) | E | holds (Chromium) |
| Redaction of names, national IDs, phones, emails, common ID formats; offset map; original never modified | `test_log_and_redaction_safety`; `test_redaction_offsets_residual_scan_and_eval` | E | holds |
| Schema: checksum, namespace, extraction offsets, rule version, spans, ownership changes, decision rationale, future audio | contracts types; 2.2, 2.3, 7.8, 7.12 | E + I | holds (rationale free text memory-only) |

## D · Build-context lessons (Section 5) and Section 4 checklist

| Lesson | Test | Status |
|---|---|---|
| L1 one disagreement = one flag | `eng/test_lessons_engine.py::test_conflict_fanout_one_flag` | holds (E) |
| L2 adjudication converges | `::test_adjudication_converges` | holds (E) |
| L3 change ≠ contradiction | `::test_change_not_contradiction` | holds (E) |
| L4 unparsed dose never passes | `::test_unparsed_dose_never_passes`; `eng/test_engine_edges.py` dose cases | holds (E) |
| L5 one term registry | `::test_single_term_registry`; `contract/test_contract_seams.py` ×2 | holds (E) |
| L6/L7 authz in two layers | `api/test_lessons_api.py::test_store_layer_authz_fault_injection`; `api/test_access_control.py` | holds (E) |
| L8 allowlist logging and audit | `::test_audit_allowlist`; `contract/test_log_allowlist.py::test_allowlist_not_denylist` | holds (E) |
| L9 assert on the element under test | `e2e/test_e2e_smoke.py` (exact full-string matches) | holds (E) |
| L10 no stub reports unobserved success | `governance/test_governance.py::test_ai_disabled_by_default`; UI "not available in this build" (Vitest) | holds (E) |
| L11 every config key changes behaviour | `::test_no_unread_config_keys`; `test_config_key_changes_behaviour` ×6 | holds (E) |
| L12 no env-conditional security | `::test_no_env_conditional_security` | holds (E) |
| L13 no online learning | `governance/…::test_no_runtime_rule_mutation`, `::test_unapproved_ruleset_refused` | holds (E) |
| L14 displayed counts equal store counts | `contract/test_open_count_integrity.py`; `test_open_count_integrity_real_api` | holds (E) |
| L15 reason codes; no bulk | `::test_decision_requires_reason_code`, `::test_no_bulk_decisions` | holds (E) |
| L16 staff prepare, clinicians close | `::test_role_matrix_staff_prepare_clinician_close` | holds (E) |
| L17 unevaluated = unqualified | AI status reports observed outcomes only (`test_ai_timeout_falls_back`); no test covers the general rule | partial (I) |
| L18 no DB / forward-only migrations | no database in the build | holds (I) |
| L19 clean repo; README matches trace | `.gitignore` (I); fresh-clone run R5 | see handoff B5.1 |
| L20 422 never echoes input | `::test_validation_error_no_echo` | holds (E) |
| Feedback 10: stale decision → 409, no lost decision | `::test_concurrent_decision_409`; `test_api_behaviour.py::test_concurrent_decisions_have_one_winner` | holds (E) |
| Feedback 16: cited source edited → side by side | `eng/test_lessons_engine.py::test_cited_source_edited_side_by_side` (engine); side-by-side view in R4 | holds (E) |

Section 4 checklist: every item maps to a row above (evidence and spans 2.2; owner 4.1; no Tier 1 auto-close 4.5; immutable versions 2.3; absence wording 6.3; no content in logs 7.3; two-layer authz 7.4; no-store C; PDF never complete 2.4; lifecycle 4.3; no model changes rules 8.4; audio schema 7.12; PWA C).

## E · Not built (with reason), in one place

- LAT-001, META-001, NEXT-001: disabled in ruleset v1, not built (cut order).
- Per-source version Change records and `removed` changes (B1): amendments show as "source changed since flag" instead.
- FHIR/SMART/HL7 adapters: mapping only (cut order).
- Human-authorised write-back artefact/Task: out of the demonstrator's read-only scope.
- A route that calls the AI drafter: AI ships disabled (OPEN-5).
- AI or learned ranking and grouping: ranking stays deterministic.
- Dismissal-spike monitoring, a blind sample of non-flagged sources, complementary small-cell suppression (B4).
- OCR, malware scanning, TLS locally, encryption at rest, rate limiting: production components, stated as gaps.
- In the UI: browser walks of decision paths other than accept, a focus trap in the mobile sheet, the carried-forward chip's origin view, Edge/Safari runs (B3).
