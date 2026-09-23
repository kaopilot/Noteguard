# Evaluation report: baseline v1 vs candidate v1

- Report sha256: `81cc969e384be097761f2e82b9b2bd54cae97cb82ff305a02db43d5a6f18d8cc` (canonical JSON; pin this in APPROVAL_<v>.md)
- Engine: `noteguard.engine.engine.Engine`; corpus sha256 `d7981fad5f50fe1423fea080c8a0e17ad06d7130734f83804d6c3c274742dd32`
- Cases: {'b4_labelled': 18, 'golden': 5, 'known_limit': 1}; labels: {'b4_labelled': 14, 'golden': 19, 'known_limit': 1}
- Tier 1 recall: baseline 17/17, candidate 17/17
- **Gate: PASSED**

Rates are `numerator/denominator` from the counts shown; `n/a (0)` = no denominator.

## Candidate, corpus part `b4_labelled`

| rule | tier | protected | labelled | raised | TP | FP | FN | precision | recall |
|---|---:|---|---:|---:|---:|---:|---:|---|---|
| ALG-001 | 1 | yes | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| CRIT-001 | 1 | yes | 4 | 5 | 4 | 1 | 0 | 4/5 | 4/4 |
| DET-001 | 1 | yes | 2 | 2 | 2 | 0 | 0 | 2/2 | 2/2 |
| DIFF-001 | 3 | no | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| DOSE-001 | 2 | yes | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| DOSE-002 | 3 | yes | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| OWN-001 | 1 | yes | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| PDF-001 | 2 | yes | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| PEND-001 | 2 | no | 2 | 2 | 2 | 0 | 0 | 2/2 | 2/2 |

## Candidate, corpus part `golden`

| rule | tier | protected | labelled | raised | TP | FP | FN | precision | recall |
|---|---:|---|---:|---:|---:|---:|---:|---|---|
| ALG-001 | 1 | yes | 3 | 3 | 3 | 0 | 0 | 3/3 | 3/3 |
| CRIT-001 | 1 | yes | 3 | 3 | 3 | 0 | 0 | 3/3 | 3/3 |
| DET-001 | 1 | yes | 2 | 2 | 2 | 0 | 0 | 2/2 | 2/2 |
| DIFF-001 | 3 | no | 2 | 2 | 2 | 0 | 0 | 2/2 | 2/2 |
| DOSE-001 | 2 | yes | 3 | 3 | 3 | 0 | 0 | 3/3 | 3/3 |
| OWN-001 | 1 | yes | 1 | 1 | 1 | 0 | 0 | 1/1 | 1/1 |
| PDF-001 | 2 | yes | 2 | 2 | 2 | 0 | 0 | 2/2 | 2/2 |
| PEND-001 | 2 | no | 3 | 3 | 3 | 0 | 0 | 3/3 | 3/3 |

## Candidate disagreements with the labels (gated parts)

- b4_labelled `L18_response_paraphrase_precision`: false_positive CRIT-001 `analyte:potassium`

## Known-limit cases (reported, not gated)

- `K01_allergen_outside_registry`: false_negative ALG-001 `*`
