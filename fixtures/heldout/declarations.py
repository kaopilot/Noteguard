"""HAND-WRITTEN golden expectations for the HELD-OUT encounter ENC-A2 (B0). Never give to B1.
Same conventions as fixtures/expected/declarations.py (see fixtures/expected/README.md).

22 Sep 2026: extended by B0 (not B1) after CCR-02 enabled DET-001 with the approved defaults: a clinician-
authored review of the SAME measurement is the only thing that clears it; one Tier 1 flag per reassurance kind
(subject = status key), owner = responsible clinician, evidence = the reassurance (claim) and the marker
(counter_claim), question like DIFF-001, no bubble."""

from __future__ import annotations

from noteguard.contracts import ids


def E(src, ver, role, quote, rev=1):
    return {"src": src, "ver": ver, "role": role, "quote": quote, "rev": rev}


def GAP(src, ver=1, page=1):
    return {"src": src, "ver": ver, "role": "extraction_gap", "quote": "", "page": page, "rev": 1}


NA = "Na 118 mmol/L"
NKDA = E("adm_nursing", 1, "claim", "No known drug allergies")
SULFA = E("pharmacy", 1, "counter_claim", "Sulfa allergy - hives (patient and daughter confirm)")
PREADM = "Pre-admission: bisoprolol 5 mg OD, atorvastatin 40 mg nocte"
UNPARSED = "4 units given as per chart"
UNPARSED_SUBJECT = "unparsed_dose@source:{src:adm_nursing}:" + ids.sha256_hex(UNPARSED)[:16]
URINE = E("ward_round", 1, "claim", "Urine culture sent, ward team to chase")
CXR = E("radiology", 1, "claim", "Chest X-ray done, awaiting report by 17:00")
REF_PDF = "Polyclinic referral letter (Clerk Ho, 12:40)"
CRIT_TERMS = ["analyte:sodium", "cue:response_review", "cue:response_repeat", "cue:response_treatment",
              "cue:response_escalation", "cue:response_transfer"]

R_CRIT = ('Lab result call (Nurse Arun, 09:40) records "Na 118 mmol/L". No later review, repeat, treatment, escalation '
          "or transfer for this result is documented in the supplied sources up to 12:00.")
R_ALG = ('Nursing admission (Nurse Wee, 08:30) states "No known drug allergies" while Pharmacy medicines '
         'reconciliation (Pharmacist Teo, 11:20) names "Sulfa allergy - hives (patient and daughter confirm)".')
R_DOSE = ('Consultant ward round (Dr Farah, 09:15) records "Bisoprolol 2.5mg once daily"; Pharmacy medicines '
          f'reconciliation (Pharmacist Teo, 11:20) records "{PREADM}". No explicit change links them.')
R_URINE = ('Consultant ward round (Dr Farah, 09:15) records "Urine culture sent, ward team to chase" without an explicit '
           "timing in the supplied sources.")
R_CXR = ('Radiology (Nurse Arun, 15:05) records "Chest X-ray done, awaiting report by 17:00" without an explicit owner '
         "in the supplied sources.")
R_D2 = (f'Nursing admission (Nurse Wee, 08:30) contains "{UNPARSED}", which the checker could not attach to a '
        "medication regimen, so it has not been compared.")
R_PDF = (f"{REF_PDF} has extraction status partial. Its content has not been checked; answers about absent "
         "documentation are limited until it is reviewed manually or by approved OCR.")
R_DIFF = ('Occupational therapy (OT Nadia, 17:00) repeats "Clinically stable" from Consultant ward round (Dr Farah, '
          '09:15); Observations (Nurse Arun, 13:30) records "Sats 90% on RA, resp rate 28" in between.')
Q_DIFF = 'Is the 17:00 "Clinically stable" statement current?'
R_DET = ('Occupational therapy (OT Nadia, 17:00) records "Clinically stable" after Observations (Nurse Arun, 13:30) '
         'recorded "Sats 90% on RA, resp rate 28", with no clinician review documented in between.')
# The 13:30 escalation is nurse-authored; the 16:20 review is Dr Farah's but covers sodium, not SpO2/RR (CCR-02 Q1).
DET_STABLE = {"rule": "DET-001", "subject": "status:stable", "tier": 1, "owner": "farah", "affected": ["arun", "nadia"],
              "evidence": [E("ot", 1, "claim", "Clinically stable"),
                           E("obs", 1, "counter_claim", "Sats 90% on RA, resp rate 28")],
              "reason": R_DET, "question": Q_DIFF}
U_CONFLICT = ("The supplied sources disagree. Only a clinician's decision can settle which entry is correct; the "
              "checker does not choose between sources.")
U_DOC = "Documented in the cited source. The checker matched wording only and has not verified the clinical content."
U_ABSENT = ("Searched 6 supplied sources up to 12:00 for the listed terms and found no matching entry. This describes "
            "the supplied record only, not what took place.")
U_INCOMPLETE = (f"1 in-scope source could not be fully read: {REF_PDF}. The answer stays incomplete until it is "
                "reviewed manually or by approved OCR.")
U_HUMAN = "The checker cannot answer this from the supplied text; a person needs to check."

SCOPE_1200 = [("overnight", 1), ("adm_nursing", 1), ("ward_round", 1), ("lab", 1), ("handover", 1), ("pharmacy", 1)]
SCOPE_1730 = SCOPE_1200 + [("referral_pdf", 1), ("obs", 1), ("radiology", 1), ("review", 1), ("ot", 1)]

COMMON = [
    {"rule": "ALG-001", "subject": "allergen:sulfonamide", "tier": 1, "owner": "farah", "affected": ["teo", "wee"],
     "evidence": [NKDA, SULFA], "reason": R_ALG},
    {"rule": "DOSE-001", "subject": "drug:bisoprolol", "tier": 2, "owner": "farah", "affected": ["teo"],
     "evidence": [E("ward_round", 1, "claim", "Bisoprolol 2.5mg once daily"), E("pharmacy", 1, "counter_claim", PREADM)],
     "reason": R_DOSE},
    {"rule": "PEND-001", "subject": "test:urine_culture", "tier": 2, "owner": "farah", "affected": [],
     "evidence": [URINE], "reason": R_URINE},
    {"rule": "DOSE-002", "subject": UNPARSED_SUBJECT, "tier": 3, "owner": "wee", "affected": [],
     "evidence": [E("adm_nursing", 1, "claim", UNPARSED)], "reason": R_D2},
]

B_ALG = {"template": "q_allergy_which_correct", "subject": "allergen:sulfonamide", "status": "conflicting",
         "flag": ("ALG-001", "allergen:sulfonamide"), "evidence": "flag", "question": "Which allergy entry is correct?",
         "uncertainty": U_CONFLICT}
B_DOSE = {"template": "q_dose_current", "subject": "drug:bisoprolol", "status": "conflicting",
          "flag": ("DOSE-001", "drug:bisoprolol"), "evidence": "flag", "question": "Which bisoprolol dose is current?",
          "uncertainty": U_CONFLICT}
B_URINE = {"template": "q_pending_owner", "subject": "test:urine_culture", "status": "documented",
           "flag": ("PEND-001", "test:urine_culture"), "evidence": [E("ward_round", 1, "trigger", "Urine culture sent, ward team to chase")],
           "question": "Who owns the pending urine culture result?", "uncertainty": U_DOC}
B_D2 = {"template": "q_unparsed_dose", "subject": UNPARSED_SUBJECT, "status": "requires_human_review",
        "flag": ("DOSE-002", UNPARSED_SUBJECT), "evidence": "flag",
        "question": f'Which medication does "{UNPARSED}" belong to?', "uncertainty": U_HUMAN}
NA_CARRIED = ("carried_forward", "analyte:sodium", ("overnight", 1, "Na reviewed overnight, plan as per team"),
              ("handover", 1, "Na reviewed overnight, plan as per team"))

ENC_A2_1200 = {
    "encounter": "ENC-A2", "cutoff": "12:00", "evaluated_at": "12:01", "prior": None, "scope": SCOPE_1200,
    "outcome": "completed",
    "flags": [{"rule": "CRIT-001", "subject": "analyte:sodium", "tier": 1, "owner": "farah", "affected": ["arun"],
               "evidence": [E("lab", 1, "claim", NA)], "reason": R_CRIT}] + COMMON,
    "must_not_flag": [
        ("DOSE-001", "drug:atorvastatin", '"40 mg nocte" in both sources.'),
        ("DIFF-001", "*", '"Clinically stable" occurs once in scope; the repeated Na line is not a status statement.'),
        ("PDF-001", "*", "No PDF is in scope at 12:00."),
        ("DET-001", "*", 'The only reassurance (09:15 "Clinically stable") precedes every deterioration marker; the '
                         "08:30 observations are inside the placeholder ranges (CCR-02)."),
    ],
    "must_not_suppress_note": ('08:10 "Na reviewed overnight" is EARLIER than the 09:40 result, and the 10:30 copy of it '
                               "is CARRIED FORWARD: neither suppresses CRIT-001."),
    "bubbles": [
        B_ALG,
        {"template": "q_crit_response", "subject": "analyte:sodium", "status": "not_documented_in_supplied_sources",
         "flag": ("CRIT-001", "analyte:sodium"), "evidence": [E("lab", 1, "trigger", NA)], "terms": CRIT_TERMS,
         "question": "Was the critical sodium reviewed or repeated?", "uncertainty": U_ABSENT},
        B_DOSE, B_URINE, B_D2,
    ],
    "required_changes": [
        ("reworded", "drug:atorvastatin", ("ward_round", 1, "Atorvastatin 40 mg nocte"), ("pharmacy", 1, PREADM)),
        NA_CARRIED,
    ],
    "summary_open_priorities": [("CRIT-001", "analyte:sodium"), ("ALG-001", "allergen:sulfonamide"),
                                ("DOSE-001", "drug:bisoprolol"), ("PEND-001", "test:urine_culture")],
    "summary_top_questions": [("q_allergy_which_correct", "allergen:sulfonamide"), ("q_crit_response", "analyte:sodium"),
                              ("q_dose_current", "drug:bisoprolol")],
    "closure": {"status": "blocked", "tier1": [("CRIT-001", "analyte:sodium"), ("ALG-001", "allergen:sulfonamide")],
                "tier2": [("DOSE-001", "drug:bisoprolol"), ("PEND-001", "test:urine_culture")], "tier3_count": 1},
}

ENC_A2_1730 = {
    "encounter": "ENC-A2", "cutoff": "17:30", "evaluated_at": "17:31", "prior": None, "scope": SCOPE_1730,
    "outcome": "completed_with_extraction_gaps",
    "flags": COMMON + [
        {"rule": "PEND-001", "subject": "test:chest_xray", "tier": 2, "owner": "arun", "affected": [],
         "evidence": [CXR], "reason": R_CXR},
        {"rule": "PDF-001", "subject": "source:{src:referral_pdf}", "tier": 2, "owner": "ho", "affected": [],
         "evidence": [GAP("referral_pdf", page=2)], "reason": R_PDF},
        {"rule": "DIFF-001", "subject": "status:stable@source:{src:ot}", "tier": 3, "owner": "nadia",
         "affected": ["arun", "farah"], "reason": R_DIFF, "question": Q_DIFF,
         "evidence": [E("ot", 1, "claim", "Clinically stable"), E("ward_round", 1, "origin", "Clinically stable"),
                      E("obs", 1, "counter_claim", "Sats 90% on RA, resp rate 28")]},
        DET_STABLE,
    ],
    "must_not_flag": [
        ("CRIT-001", "analyte:sodium", '16:20 "Sodium 118 seen by Dr Farah; fluid restriction commenced" is a later, new, non-negated response for the same analyte.'),
        ("DOSE-001", "drug:atorvastatin", '16:20 "Atorvastatin reduced to 20 mg nocte" is an explicit change (L3).'),
        ("PEND-001", "analyte:sodium", '"Repeat Na sent; Dr Farah to review by 21:00" names an owner and a time.'),
        ("CRIT-001", "analyte:spo2", "Deterioration marker in registry v1, not a critical threshold."),
        ("CRIT-001", "analyte:respiratory_rate", "Deterioration marker in registry v1, not a critical threshold."),
        ("DET-001", "status:fit_for_discharge", "No discharge-readiness statement in scope (CCR-02)."),
    ],
    "must_not_suppress_note": ('13:30 "Escalated to Dr Farah by phone" names no analyte; it is not a sodium response. It is '
                               "also nurse-authored, and the 16:20 medical review covers sodium, not SpO2 or RR, so "
                               "neither clears DET-001 (CCR-02 Q1)."),
    "bubbles": [
        B_ALG,
        {"template": "q_crit_response", "subject": "analyte:sodium", "status": "documented", "flag": None,
         "evidence": [E("lab", 1, "trigger", NA),
                      E("review", 1, "suppressor", "Sodium 118 seen by Dr Farah; fluid restriction commenced"),
                      E("review", 1, "suppressor", "Repeat Na sent; Dr Farah to review by 21:00")],
         "question": "Was the critical sodium reviewed or repeated?", "uncertainty": U_DOC},
        B_DOSE,
        {"template": "q_pending_owner", "subject": "test:chest_xray", "status": "incomplete_extraction",
         "flag": ("PEND-001", "test:chest_xray"),
         "evidence": [E("radiology", 1, "trigger", "Chest X-ray done, awaiting report by 17:00"), GAP("referral_pdf", page=2)],
         "terms": ["test:chest_xray", "cue:owner"], "question": "Who owns the pending chest x-ray result?",
         "uncertainty": U_INCOMPLETE},
        B_URINE,
        {"template": "q_pdf_manual_review", "subject": "source:{src:referral_pdf}", "status": "requires_human_review",
         "flag": ("PDF-001", "source:{src:referral_pdf}"), "evidence": "flag",
         "question": f"Has {REF_PDF} been reviewed manually or by approved OCR?", "uncertainty": U_HUMAN},
        {"template": "q_carried_forward_current", "subject": "status:stable@source:{src:ot}",
         "status": "requires_human_review", "flag": ("DIFF-001", "status:stable@source:{src:ot}"), "evidence": "flag",
         "question": Q_DIFF, "uncertainty": U_HUMAN},
        B_D2,
    ],
    "required_changes": [
        ("explicit_change", "drug:atorvastatin", ("pharmacy", 1, PREADM), ("review", 1, "Atorvastatin reduced to 20 mg nocte")),
        ("carried_forward", "status:stable", ("ward_round", 1, "Clinically stable"), ("ot", 1, "Clinically stable")),
        NA_CARRIED,
    ],
    "summary_open_priorities": [("ALG-001", "allergen:sulfonamide"), ("DET-001", "status:stable"),
                                ("DOSE-001", "drug:bisoprolol"),
                                ("PEND-001", "test:urine_culture"), ("PEND-001", "test:chest_xray"),
                                ("PDF-001", "source:{src:referral_pdf}")],
    "summary_top_questions": [("q_allergy_which_correct", "allergen:sulfonamide"), ("q_dose_current", "drug:bisoprolol"),
                              ("q_pending_owner", "test:chest_xray")],
    "closure": {"status": "blocked", "tier1": [("ALG-001", "allergen:sulfonamide"), ("DET-001", "status:stable")],
                "tier2": [("DOSE-001", "drug:bisoprolol"), ("PEND-001", "test:urine_culture"),
                          ("PEND-001", "test:chest_xray"), ("PDF-001", "source:{src:referral_pdf}")], "tier3_count": 2},
}

SCENARIOS = {"ENC-A2_1200": ENC_A2_1200, "ENC-A2_1730": ENC_A2_1730}
