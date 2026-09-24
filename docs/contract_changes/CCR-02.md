# CCR-02 — Enable DET-001 (reassurance after deterioration) with its goldens
Raised by: B1, session B1.2   Date: 2026-09-22

What changes (files, fields, values):
  1. `rulesets/v1.json`: DET-001 `"enabled": true` (B1 rule content; lands in the SAME merge as the goldens,
     never before). Reason and question templates are unchanged.
  2. `fixtures/expected/declarations.py` (B0/integrator; proposed entries below, written by hand from the rule
     catalog, 8.2 row DET-001, not from engine output), then `make goldens` and the review sheet.
  No contract (types, states, ids, routes) changes. No new question template (see question 5).

Why (the failing case or missing capability):
  The appendix tier table lists "deterioration versus reassuring/discharge assessment" as a Tier 1 minimum
  example. In v1 the 16:00 "Patient stable" after the 13:00 SpO2 89% / RR 26 surfaces only as DIFF-001 (Tier 3),
  and only because it happens to be copied; a freshly written reassurance after deterioration raises nothing.
  @kaopilot (22 Sep, decisions/B0.md #26): DET-001 is the first stretch rule, only via a CCR adding its goldens.
  B1 built it (`noteguard/engine/rules/deterioration.py`, B1.2) with the rule DISABLED, so no golden moved.

Semantics as built (each is a question for @kaopilot below):
  - Reassurance: registry `status` term, live, not queried, in a source whose source_time is LATER than a
    deterioration marker (registry `deterioration_*` thresholds only; critical values are not markers).
  - Answered only by a clinician review: a statement in a CLINICIAN-authored source, live response cue in the
    same clause as the SAME analyte, not carried forward, at or after the marker's source and at or before the
    reassurance. Seen before and now answered -> superseded (Tier 1: still blocks closure).
  - Subject: the status term key (`status:stable`), one flag per reassurance kind (L1).
  - Evidence: claim = reassurance(s); counter_claim = unreviewed marker statement(s). Owner: responsible
    clinician (else attending); affected = evidence authors minus owner. `question` set (like DIFF-001).

Proposed golden declarations (declarations.py syntax):

    DET_STABLE = {"rule": "DET-001", "subject": "status:stable", "tier": 1, "owner": "lim", "affected": ["goh", "ravi"],
                  "evidence": [E("sw", 1, "claim", "Patient stable"),
                               E("obs", 1, "counter_claim", "SpO2 89% on room air, RR 26")],
                  "reason": ('Discharge planning (SW Goh, 16:00) records "Patient stable" after Afternoon observations '
                             '(Nurse Ravi, 13:00) recorded "SpO2 89% on room air, RR 26", with no clinician review '
                             "documented in between."),
                  "question": 'Is the 16:00 "Patient stable" statement current?'}

    ENC_A1_1130: must_not_flag += ("DET-001", "*", "The only reassurance (09:00) precedes every deterioration marker;
                 the 08:40 observations are within the placeholder ranges.")
    ENC_A1_1600: flags += DET_STABLE; summary_open_priorities += ("DET-001", "status:stable");
                 closure["tier1"] += ("DET-001", "status:stable");
                 must_not_flag += ("DET-001", "status:fit_for_discharge", "No discharge-readiness statement in scope.")
                 (the 15:30 Dr Lim review names potassium, not SpO2 or RR, so it does not answer DET-001)
    ENC_A1_1600_rerun: flags += DET_STABLE (new in this run: first_run is the rerun); same summary/closure additions.
    ENC_B1_1600, ENC_C1_1000: must_not_flag += ("DET-001", "*", "No reassurance after a deterioration marker.")
    Bubbles and top questions: unchanged (no DET-001 template). Glance open_tier1 +1 at 16:00 (fresh and rerun).
  Closure stays `blocked` in every affected scenario (ALG-001 already blocks); no other flag changes.
  B1 cross-check (not the source of the above): `tests/engine/test_det_001.py::
  test_det_001_disabled_in_v1_and_proposed_golden` shows the engine, with DET enabled in memory, produces
  exactly this evidence on ENC-A1 at 16:00.

Questions for @kaopilot (defaults are what B1 built):
  1. Clinician review = clinician-authored source reviewing the SAME analyte (default). Alternative: any
     clinician-authored note after the marker. The default raises the ENC-A1 16:00 flag; the alternative would
     not (the 15:30 Dr Lim note would count although it concerns potassium).
  2. Overlap: the 16:00 statement also raises DIFF-001 (Tier 3). Default: keep both (different questions:
     "copied?" vs "current after deterioration?"). Alternative: suppress DIFF-001 on a statement DET-001 covers.
  3. A later normal observation does not answer DET-001 (default, avoids inferring recovery). Alternative:
     treat a later in-range value of the same analyte before the reassurance as answering it.
  4. One flag per reassurance kind (default) vs per reassuring note.
  5. No bubble template (default). Alternative: add `q_reassurance_current` (flag_rule DET-001, human_review).

Lanes affected and what each must do:
  B0/integrator: add the declarations, `make goldens`, review sheet; land with B1's `enabled: true` in one commit.
  @kaopilot: sign off the new/changed scenarios (SIGNOFF), answer questions 1-5.
  B1: flip `enabled` in the same merge; adjust the rule if @kaopilot picks an alternative.
  B4: refresh APPROVAL_v1.md hashes at CP2 (ruleset content changes).
  B3: none beyond rendering another Tier 1 card (same flag shape; text label + icon).
  B2: none (wire shape unchanged).
  I1: held-out ENC-A2 goldens may need DET-001 entries; update them outside B1's view.

Golden fixture impact: as listed above (ENC-A1_1130, ENC-A1_1600, ENC-A1_1600_rerun, ENC-B1_1600, ENC-C1_1000);
review sheet diff to be generated by the integrator with `make goldens`.

Status: approved with defaults (@kaopilot, 22 Sep 2026, chat B1.2). Landing prepared by B1 on branch `ccr-01-02`
  (session B1.3) in ONE commit, "[B1.3] CCR-02 landing": DET-001 enabled + the declarations above + `make goldens`.
  Deviation from the text above, as the review doc allowed: the ENC-B1/ENC-C1 "must not flag DET-001" lines were
  left out (exact comparison already covers them), so those two scenarios keep their sign-off.
  Checked: outside DET-001, every golden JSON is byte-identical; closure status unchanged in all five scenarios.
  ENC-A1_1130, ENC-A1_1600 and ENC-A1_1600_rerun were re-signed by @kaopilot in 73a85f8 ("re-sign ENC-A1 goldens after
  CCR-02"). LANDED: merged by @kaopilot in 336267a ("Merge ccr-01-02", 23 Sep 2026). Status line updated by I1 (session I1.5, 24 Sep 2026) at @kaopilot's request.
