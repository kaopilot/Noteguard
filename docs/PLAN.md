# Noteguard — plan (seeded by B0 on 22 Sep 2026; finalised by B5 in session B5.1, 24 Sep 2026)

Owner: @kaopilot. (Lane records written before 24 Sep call the owner "@kaopilot"; see docs/DECISIONS.md.)

## Scope
A read-only reconciliation layer for one patient encounter:
- It cross-reads the supplied sources (pasted notes, PDFs).
- It raises grounded, owned flags (Tier 1/2/3).
- It answers a fixed catalogue of question bubbles with scoped absence answers.
- It shows closure blockers and a one-page summary.

It is not the medical record and does not diagnose or recommend treatment. It never closes a Tier 1 flag on its own, and stores nothing clinical beyond a per-page-load, single-process workspace.

## The AI line
- Deterministic rules decide whether a flag exists, its tier, owner and state, and whether it blocks closure.
- AI (off by default, OPEN-5) may only rank bubbles within a tier, group evidence, and draft a short explanation from redacted, verified evidence.
- Any AI output sits behind a validator, a timeout and a deterministic fallback (build context Section 9).

As built, the drafting module and its gate are tested, but no route calls it; the product ships with AI disabled.

## Requirement → test → code
The full matrix is `docs/REQUIREMENTS_TRACE.md`. It covers every Builder Brief requirement (§1–8), the nine required proofs / appendix micro-tests, the appendix extras, and lessons L1–L20, each with an evidence level and a status.

The nine required tests and their homes:

| Requirement | Test (owner) | Code |
|---|---|---|
| Critical observation → Tier 1, owned; later response suppresses | `test_critical_observation_routing` (B1); API run (I1) | `noteguard/engine/rules/` |
| Allergy T1 / dose T2 conflicts, fan-out | `test_cross_note_conflicts` (B1) | engine |
| Pending action needs owner AND timing | `test_pending_owner_and_time` (B1) | engine |
| Unreadable PDF retained, issue raised, absence downgraded | `test_pdf_extraction_boundary` (B2); bubble half in `test_question_bubble_grounding` (B1); failed extraction via API (I1) | `noteguard/intake`, engine |
| Access control, two layers | `test_access_control`, `test_store_layer_authz_fault_injection` (B2) | `noteguard/api` |
| No identifiers in logs; redaction + egress gate | `test_log_and_redaction_safety` (B2) | api, `noteguard/redaction`, `contracts/egress.py` |
| Every flag and summary claim grounded | `test_grounding` (B1); `test_grounding_through_real_api` (I1) | engine, api |
| Differencing: stale copy → question; explicit change → change | `test_differencing` (B1) | engine |
| Bubble statuses, scoped absence, forbidden phrases | `test_question_bubble_grounding` (B1), `test_forbidden_phrase_lint` (B0) | engine, contracts |

## Schedule actually followed (from git history and handoffs; times SGT)

| When | What |
|---|---|
| 22 Sep ~02:15–12:10 | **B0** contracts, fixtures, hand-written goldens, stubs, test skeletons. **CP0**: @kaopilot confirmed OPEN-1…8 and signed off the goldens |
| 22 Sep | **B1** engine (B1.1–B1.3): 8 rules, then DET-001 via CCR-02; CCR-01 (dose units into the registry) |
| 23 Sep 00:44 | CCR-01/02 merged, ENC-A1 goldens re-signed; held-out ENC-A2 run by @kaopilot (2/2 after the DET-001 answer-key update) |
| 23 Sep 01:40–10:23 | **B2** API and safety (B2.2 merged 10:23) |
| 23 Sep 11:40–17:24 | **B3** UI/PWA (B3.1 merged 17:24) |
| 23 Sep 17:30–18:27 | **B4** governance and AI gate (B4.1–B4.2 merged 18:27) |
| 23 Sep 18:40–23:50 | **CP1** follow-ups: B2.3/B2.4 (CCR-03), B3.2/B3.3 (governance pause, feedback UI, aggregate page), B4.3 (CCR-04) |
| 24 Sep 00:07–02:17 | **I1 / CP2**: ENC-A2 installed; v1 approved by @kaopilot; real engine behind the approval gate; API-level goldens; E2E smoke; CCR-05; B1.5, B3.4, B4.4; merged to `main` (eff8608) |
| 24 Sep | **B5.1**: trace, brief, README, this plan, DECISIONS fold, fresh-clone release check |

B5 did not draft from CP0 as planned; it started after CP2, so the docs were written once, against final evidence.

## Cut list (Section 14 order) and what was actually cut

| Item | Outcome | Reason |
|---|---|---|
| AI augmentation | **Partly cut**: gate, validator, timeout, fallback and the "disabled" state built and tested; no route calls the drafter | OPEN-5: ship disabled; nothing in the contract needed a drafting route |
| FHIR adapter | **Cut**; mapping in the brief §8 | cut order |
| Aggregate page | **Built** (B3.3), endpoint (B4) | time allowed |
| DET-001 / LAT-001 | DET-001 **built and enabled** (CCR-02); LAT-001 **cut** | DET-001 covers the appendix's deterioration-vs-reassurance Tier 1 example |
| Workstation three-pane | Wide screens show decisions in a side panel (B3); a full three-pane layout is not verified by B5 | — |
| Tier 3 stretch rules | META-001, NEXT-001 **cut** (disabled in v1) | cut order |
| Also not built | Per-source amendment Change records (B1); dismissal-spike monitoring, blind sample, shadow ranking, complementary suppression (B4); OCR, malware scan, local TLS, rate limiting (production components) | time; declared in the brief |

Never cut, and all built and tested: the nine required tests, two-layer authz, the log marker test, absence scoping, Tier 1 non-auto-closure, and the brief's honesty sections.

## Release check
Fresh clone → README → `make test`, recorded in `docs/handoffs/B5.md` (session B5.1).
