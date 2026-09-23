"""Offline evaluation and the release gate (B4; Section 11 step 4, REVIEW_STANDARD_OBSERVATIONS §4.2).

Runs the REAL engine with a baseline and a candidate ruleset bundle over a fixed labelled corpus
(``labelled.py``) and reports per-rule counts with denominators: labelled, raised, true positives,
false positives, false negatives, precision "tp/raised" and recall "tp/labelled".

Release gate (the candidate is refused if ANY holds):
- ``tier1_recall_below_1``: a Tier 1 label is not raised at Tier 1 by the candidate;
- ``tier1_recall_decreased``: candidate Tier 1 recall is lower than the baseline's;
- ``new_protected_miss``: a label on a protected rule that the baseline caught and the candidate does not;
- ``floor:<code>``: a static diff lowers, disables or unprotects a protected rule, removes registry
  vocabulary, extends a suppressing cue, or loosens a threshold.
Known-limit cases are run and reported but never enter the gate (declared in cases.json).

The report is deterministic (no wall-clock time), so anyone can rerun it and check the hash that
``APPROVAL_<v>.md`` pins as ``evaluation_report_sha256``. It holds rule ids, case ids, subject keys
and counts only; no source text.

Usage:
    uv run python -m noteguard.governance.evaluate --baseline v1 --candidate v1 [--out-dir DIR]
    uv run python -m noteguard.governance.evaluate --baseline v1 --verify   (CP2: record/report/fresh agree)
    (--candidate-ruleset / --candidate-registry take file paths for an unreleased candidate)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from noteguard.contracts import ids
from noteguard.contracts.engine_api import EngineAPI
from noteguard.contracts.types import CueKind, Ruleset, RulesetBundle, RuleId, TermRegistry, Tier

from . import labelled
from .propose import _WIDENING_CUES, is_protected

REPORT_VERSION = 1
ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "fixtures" / "labelled_eval" / "reports"
GATED_PARTS = ("b4_labelled", "golden")


def bundle_from_files(ruleset_path: Path, registry_path: Path) -> RulesetBundle:
    """Unapproved on purpose: evaluation is the step BEFORE approval. Never used by the runtime."""
    rs, reg = ruleset_path.read_bytes(), registry_path.read_bytes()
    return RulesetBundle(ruleset=Ruleset.model_validate_json(rs), registry=TermRegistry.model_validate_json(reg),
                         ruleset_sha256=ids.sha256_hex(rs), registry_sha256=ids.sha256_hex(reg))


def _ratio(n: int, d: int) -> str:
    return f"{n}/{d}" if d else "n/a (0)"


# ---------------------------------------------------------------------------------------------
# Static floor check (candidate vs baseline)
# ---------------------------------------------------------------------------------------------


def floor_violations(baseline: RulesetBundle, candidate: RulesetBundle) -> list[str]:
    out = []
    cand_rules = {r.rule_id: r for r in candidate.ruleset.rules}
    for r in baseline.ruleset.rules:
        if not is_protected(r):
            continue
        c = cand_rules.get(r.rule_id)
        if c is None:
            out.append(f"floor:rule_removed:{r.rule_id.value}")
            continue
        if r.enabled and not c.enabled:
            out.append(f"floor:rule_disabled:{r.rule_id.value}")
        if c.default_tier > r.default_tier:
            out.append(f"floor:tier_lowered:{r.rule_id.value}")
        if r.protected_floor and not c.protected_floor:
            out.append(f"floor:unprotected:{r.rule_id.value}")
    b_reg, c_reg = baseline.registry, candidate.registry
    c_terms = {t.key: t for t in c_reg.terms}
    for t in b_reg.terms:
        ct = c_terms.get(t.key)
        if ct is None or not set(t.synonyms) <= set(ct.synonyms):
            out.append(f"floor:term_vocabulary_removed:{t.key}")
            continue
        if t.critical_high is not None and (ct.critical_high is None or ct.critical_high > t.critical_high):
            out.append(f"floor:threshold_loosened:{t.key}:critical_high")
        if t.critical_low is not None and (ct.critical_low is None or ct.critical_low < t.critical_low):
            out.append(f"floor:threshold_loosened:{t.key}:critical_low")
        if t.deterioration_below is not None and (ct.deterioration_below is None
                                                  or ct.deterioration_below < t.deterioration_below):
            out.append(f"floor:threshold_loosened:{t.key}:deterioration_below")
        if t.deterioration_at_or_above is not None and (ct.deterioration_at_or_above is None
                                                        or ct.deterioration_at_or_above > t.deterioration_at_or_above):
            out.append(f"floor:threshold_loosened:{t.key}:deterioration_at_or_above")
    if not {d.phrase for d in b_reg.allergy_denials} <= {d.phrase for d in c_reg.allergy_denials}:
        out.append("floor:denial_vocabulary_removed")
    for kind in CueKind:
        b, c = set(b_reg.cues.get(kind, ())), set(c_reg.cues.get(kind, ()))
        if kind in _WIDENING_CUES and not b <= c:
            out.append(f"floor:cue_removed:{kind.value}")
        if kind not in _WIDENING_CUES and not c <= b:
            out.append(f"floor:suppressing_cue_extended:{kind.value}")
    return out


# ---------------------------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------------------------


def _score_case(case: labelled.Case, flags) -> dict:
    """Greedy one-to-one matching: each label claims at most one raised flag of its rule."""
    remaining = list(flags)
    tp, fn = [], []
    for lab in case.expected:
        hit = next((f for f in remaining if lab.matches(f.rule_id, f.subject_key)), None)
        if hit is None:
            fn.append((lab, None))
        else:
            remaining.remove(hit)
            tp.append((lab, hit))
    return {"tp": tp, "fn": fn, "fp": remaining}


def run_side(engine: EngineAPI, bundle: RulesetBundle, cases: tuple[labelled.Case, ...]) -> dict[str, dict]:
    out = {}
    for case in cases:
        result = engine.run_checks(case.snapshot, bundle, case.cutoff, run_id=case.run_id,
                                   evaluated_at=case.evaluated_at)
        out[case.case_id] = _score_case(case, result.flags)
    return out


def _per_rule(scored: dict[str, dict], cases: tuple[labelled.Case, ...], bundle: RulesetBundle) -> list[dict]:
    rules = {r.rule_id: r for r in bundle.ruleset.rules}
    c = defaultdict(lambda: {"labelled": 0, "raised": 0, "tp": 0, "fp": 0, "fn": 0, "tier_mismatch": 0})
    for case in cases:
        s = scored[case.case_id]
        for lab, hit in s["tp"]:
            c[lab.rule_id]["labelled"] += 1
            c[lab.rule_id]["raised"] += 1
            c[lab.rule_id]["tp"] += 1
            c[lab.rule_id]["tier_mismatch"] += hit.tier != lab.tier
        for lab, _ in s["fn"]:
            c[lab.rule_id]["labelled"] += 1
            c[lab.rule_id]["fn"] += 1
        for f in s["fp"]:
            c[f.rule_id]["raised"] += 1
            c[f.rule_id]["fp"] += 1
    rows = []
    for rid in sorted(set(c) | set(rules), key=lambda r: r.value):
        r, x = rules.get(rid), c[rid]
        rows.append(dict(rule_id=rid.value, tier=int(r.default_tier) if r else None,
                         enabled=bool(r and r.enabled), protected=bool(r and is_protected(r)), **x,
                         precision=_ratio(x["tp"], x["raised"]), recall=_ratio(x["tp"], x["labelled"])))
    return rows


def _tier1(scored: dict[str, dict], cases) -> tuple[int, int, set]:
    """(caught at Tier 1, Tier 1 labels, keys of labels caught at Tier 1)."""
    caught, total, keys = 0, 0, set()
    for case in cases:
        s = scored[case.case_id]
        for lab, hit in s["tp"] + s["fn"]:
            if lab.tier is Tier.T1:
                total += 1
                if hit is not None and hit.tier is Tier.T1:
                    caught += 1
                    keys.add((case.case_id, lab.rule_id.value, lab.subject))
    return caught, total, keys


def _caught(scored: dict[str, dict], cases, protected: set[RuleId]) -> set:
    return {(c.case_id, lab.rule_id.value, lab.subject) for c in cases for lab, hit in scored[c.case_id]["tp"]
            if lab.rule_id in protected}


def _disagreements(scored: dict[str, dict], cases) -> list[dict]:
    out = []
    for c in cases:
        s = scored[c.case_id]
        out += [{"part": c.part, "case": c.case_id, "kind": "false_negative", "rule_id": lab.rule_id.value,
                 "subject": lab.subject} for lab, _ in s["fn"]]
        out += [{"part": c.part, "case": c.case_id, "kind": "tier_mismatch", "rule_id": lab.rule_id.value,
                 "subject": lab.subject, "labelled_tier": int(lab.tier), "raised_tier": int(h.tier)}
                for lab, h in s["tp"] if h.tier != lab.tier]
        out += [{"part": c.part, "case": c.case_id, "kind": "false_positive", "rule_id": f.rule_id.value,
                 "subject": f.subject_key, "raised_tier": int(f.tier)} for f in s["fp"]]
    return out


def evaluate(baseline: RulesetBundle, candidate: RulesetBundle, engine: EngineAPI | None = None,
             cases: tuple[labelled.Case, ...] | None = None, corpus_sha256: str | None = None) -> dict:
    if engine is None:
        from noteguard.engine import get_engine

        engine = get_engine()
    cases = cases if cases is not None else labelled.load_cases() + labelled.load_golden()
    gated = tuple(c for c in cases if c.part in GATED_PARTS)
    limits = tuple(c for c in cases if c.part not in GATED_PARTS)
    sides = {"baseline": baseline, "candidate": candidate}
    scored = {name: run_side(engine, b, cases) for name, b in sides.items()}

    t1 = {name: _tier1(scored[name], gated) for name in sides}
    protected = {r.rule_id for r in baseline.ruleset.rules if is_protected(r)}
    new_protected_misses = sorted(_caught(scored["baseline"], gated, protected) - _caught(scored["candidate"], gated, protected))
    reasons = []
    c_caught, c_total, _ = t1["candidate"]
    b_caught, b_total, _ = t1["baseline"]
    if c_total == 0 or c_caught < c_total:
        reasons.append("tier1_recall_below_1")
    if b_total and c_caught * b_total < b_caught * c_total:
        reasons.append("tier1_recall_decreased")
    if new_protected_misses:
        reasons.append("new_protected_miss")
    floor = floor_violations(baseline, candidate)
    reasons += floor

    def side_report(name: str) -> dict:
        b = sides[name]
        return dict(ruleset_version=b.ruleset.ruleset_version, ruleset_sha256=b.ruleset_sha256,
                    registry_version=b.registry.registry_version, registry_sha256=b.registry_sha256,
                    tier1_recall=_ratio(t1[name][0], t1[name][1]),
                    per_rule={part: _per_rule(scored[name], tuple(c for c in gated if c.part == part), b)
                              for part in GATED_PARTS},
                    per_rule_all_gated=_per_rule(scored[name], gated, b),
                    disagreements=_disagreements(scored[name], gated),
                    known_limits=_disagreements(scored[name], limits))

    report = {
        "report_version": REPORT_VERSION,
        "engine": f"{type(engine).__module__}.{type(engine).__name__}",
        "corpus": {"sha256": corpus_sha256 or labelled.corpus_sha256(),
                   "cases": {p: sum(c.part == p for c in cases) for p in (*GATED_PARTS, "known_limit")},
                   "labels": {p: sum(len(c.expected) for c in cases if c.part == p) for p in (*GATED_PARTS, "known_limit")},
                   "gated_parts": list(GATED_PARTS)},
        "baseline": side_report("baseline"),
        "candidate": side_report("candidate"),
        "new_protected_misses": [list(k) for k in new_protected_misses],
        "floor_violations": floor,
        "gate": {"passed": not reasons, "reasons": reasons},
    }
    return report


def report_sha256(report: dict) -> str:
    return ids.sha256_hex(ids.canonical_json(report))


def render_markdown(report: dict) -> str:
    c, g = report["candidate"], report["gate"]
    lines = [f"# Evaluation report: baseline {report['baseline']['ruleset_version']} vs candidate {c['ruleset_version']}",
             "", f"- Report sha256: `{report_sha256(report)}` (canonical JSON; pin this in APPROVAL_<v>.md)",
             f"- Engine: `{report['engine']}`; corpus sha256 `{report['corpus']['sha256']}`",
             f"- Cases: {report['corpus']['cases']}; labels: {report['corpus']['labels']}",
             f"- Tier 1 recall: baseline {report['baseline']['tier1_recall']}, candidate {c['tier1_recall']}",
             f"- **Gate: {'PASSED' if g['passed'] else 'REFUSED'}**" + ("" if g["passed"] else f" ({', '.join(g['reasons'])})"),
             "", "Rates are `numerator/denominator` from the counts shown; `n/a (0)` = no denominator.", ""]
    for part in GATED_PARTS:
        lines += [f"## Candidate, corpus part `{part}`", "",
                  "| rule | tier | protected | labelled | raised | TP | FP | FN | precision | recall |",
                  "|---|---:|---|---:|---:|---:|---:|---:|---|---|"]
        for r in c["per_rule"][part]:
            if r["labelled"] or r["raised"]:
                lines.append(f"| {r['rule_id']} | {r['tier']} | {'yes' if r['protected'] else 'no'} | {r['labelled']} | "
                             f"{r['raised']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['precision']} | {r['recall']} |")
        lines.append("")
    lines += ["## Candidate disagreements with the labels (gated parts)", ""]
    lines += [f"- {d['part']} `{d['case']}`: {d['kind']} {d['rule_id']} `{d['subject']}`" for d in c["disagreements"]] or ["- none"]
    lines += ["", "## Known-limit cases (reported, not gated)", ""]
    lines += [f"- `{d['case']}`: {d['kind']} {d['rule_id']} `{d['subject']}`" for d in c["known_limits"]] or ["- none"]
    return "\n".join(lines) + "\n"


def verify_approval(approval_path: Path, report_path: Path, *, engine: EngineAPI | None = None) -> list[str]:
    """CP2 check: the record's files, the committed report and a FRESH evaluation all agree, and the
    gate passes. Returns problem codes (empty = consistent). Rulesets are read from the record's dir."""
    from .approval import RulesetRefused, parse_approval_record

    try:
        rec = parse_approval_record(approval_path)
    except RulesetRefused as exc:
        return list(exc.codes)
    if rec.evaluation_report_sha256 is None:
        return ["evaluation_report_missing"]
    d = approval_path.parent
    bundle = bundle_from_files(d / f"{rec.ruleset_version}.json", d / f"registry_{rec.registry_version}.json")
    problems = []
    if (bundle.ruleset_sha256, bundle.registry_sha256) != (rec.ruleset_sha256, rec.registry_sha256):
        problems.append("file_hash_mismatch")
    if not report_path.is_file() or report_sha256(json.loads(report_path.read_text(encoding="utf-8"))) != rec.evaluation_report_sha256:
        problems.append("report_file_does_not_match_record")
    fresh = evaluate(bundle, bundle, engine=engine)
    if report_sha256(fresh) != rec.evaluation_report_sha256:
        problems.append("report_not_reproducible")
    if not fresh["gate"]["passed"]:
        problems.append("gate_refused")
    return problems


def _side(version: str, ruleset: Path | None, registry: Path | None) -> RulesetBundle:
    rs = ruleset or ROOT / "rulesets" / f"{version}.json"
    reg = registry or ROOT / "rulesets" / f"registry_{Ruleset.model_validate_json(rs.read_bytes()).registry_version}.json"
    return bundle_from_files(rs, reg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline evaluation and release gate (B4)")
    ap.add_argument("--baseline", default="v1")
    ap.add_argument("--candidate", default="v1")
    ap.add_argument("--candidate-ruleset", type=Path)
    ap.add_argument("--candidate-registry", type=Path)
    ap.add_argument("--out-dir", type=Path, default=REPORTS_DIR)
    ap.add_argument("--verify", action="store_true",
                    help="CP2 check of APPROVAL_<baseline>.md against the committed and a fresh report")
    a = ap.parse_args(argv)
    if a.verify:
        problems = verify_approval(ROOT / "rulesets" / f"APPROVAL_{a.baseline}.md",
                                   a.out_dir / f"EVAL_{a.baseline}_vs_{a.baseline}.json")
        sys.stdout.write(f"APPROVAL_{a.baseline}: {'consistent' if not problems else ', '.join(problems)}\n")
        return 0 if not problems else 1
    base = _side(a.baseline, None, None)
    cand = _side(a.candidate, a.candidate_ruleset, a.candidate_registry)
    report = evaluate(base, cand)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"EVAL_{a.baseline}_vs_{a.candidate}"
    (a.out_dir / f"{stem}.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (a.out_dir / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    sys.stdout.write(f"{stem}: gate {'passed' if report['gate']['passed'] else 'refused'}; "
                     f"report sha256 {report_sha256(report)}\n")  # ids and hashes only
    return 0 if report["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
