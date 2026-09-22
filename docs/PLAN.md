# Noteguard — plan (seeded by B0 on 22 Sep 2026; B5 finalises)

## Scope
A read-only reconciliation layer for one patient encounter: it cross-reads the supplied sources
(pasted notes, PDFs), raises grounded, owned flags (Tier 1/2/3), answers a fixed catalogue of
question bubbles with scoped absence answers, and shows closure blockers and a one-page summary.
It is not the medical record, does not diagnose or recommend treatment, never closes a Tier 1
flag on its own, and stores nothing clinical beyond a per-page-load, single-process workspace.

## The AI line
Deterministic rules decide whether a flag exists, its tier, owner and state, and whether it
blocks closure. AI (off by default, OPEN-5) may only rank bubbles within a tier, group evidence
and draft a short explanation from redacted, verified evidence, behind a validator, a timeout and
a deterministic fallback (build context Section 9).

## Requirement → test → code (B0 seed; B5 turns this into REQUIREMENTS_TRACE.md)

| Requirement | Test (owner) | Code |
|---|---|---|
| Critical observation without response → Tier 1, owned; later response suppresses | `test_critical_observation_routing` (B1) | `noteguard/engine` |
| Cross-note conflicts (allergy T1, dose T2), fan-out | `test_cross_note_conflicts` (B1) | engine |
| Pending action needs owner AND timing | `test_pending_owner_and_time` (B1) | engine |
| Unreadable PDF retained, issue raised, absence downgraded | `test_pdf_extraction_boundary` (B2) + bubble half in `test_question_bubble_grounding` (B1) | `noteguard/intake`, engine |
| Access control, two layers | `test_access_control` (B2), `test_store_layer_authz_fault_injection` (B2) | `noteguard/api`, store |
| No clinical content in logs; redaction + egress gate | `test_log_and_redaction_safety` (B2) | api, `noteguard/redaction`, `contracts/egress.py` |
| Every flag and summary claim grounded | `test_grounding` (B1; I1 via API) | engine |
| Differencing: stale copy → question; explicit change → change | `test_differencing` (B1) | engine |
| Bubble statuses, scoped absence, forbidden phrases | `test_question_bubble_grounding` (B1), `test_forbidden_phrase_lint` (B0) | engine, contracts |
| Engine equals hand-written goldens (exact sets) | `test_golden_engine` (B1), `test_heldout_golden` (I1) | engine |
| One definition of every shared concept | `test_contract_seams` (B0) | `noteguard/contracts` |
| Open counts agree everywhere (L14) | `test_open_count_integrity` (B0/I1) | api |
| Tier 1 never auto-closed | `test_tier1_never_auto_closed` (B1) | engine, `contracts/states.py` |
| No runtime rule mutation; unapproved ruleset refused (L13) | `tests/governance` (B4) | `noteguard/governance` |
| Main path reachable end to end | `test_e2e_smoke` (I1) | all |

## Schedule and checkpoints (Section 18.6)
CP0 B0 merged, goldens signed off → B1–B4 in parallel against stubs → CP1 each lane green on its
branch, merge B1 → B2 → B4 → B3 → CP2 (I1) real engine behind the API, goldens + held-out ENC-A2
end to end, E2E green → code freeze Thu 24 Sep 08:00 SGT → fresh-clone release check by 10:00 →
deliver 11:00. B5 drafts from CP0.

## Cut list (Section 14, cut from the top)
AI augmentation (keep gate, validator, "disabled") → FHIR adapter (keep mapping table) → aggregate
page (keep endpoint) → DET-001/LAT-001 → workstation three-pane → Tier 3 stretch rules.
Never cut: the nine required tests, two-layer authz, log marker test, absence scoping, Tier 1
non-auto-closure, the brief's honesty sections. Cuts actually made: none yet.
