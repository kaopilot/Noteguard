"""Materialise the hand-written golden declarations into contract-valid JSON (B0).

Run: `uv run python fixtures/expected/materialize.py` (or `make goldens`).
Writes fixtures/expected/<scenario>.json and fixtures/expected/REVIEW_SHEET.md.

This script makes NO rule decision. It only:
  - resolves each declared quote to code-point offsets (exactly one occurrence, and it
    must be a statement span per contracts/spans.py),
  - computes ids, hashes and check_version with contracts.ids,
  - validates every object against the frozen contract,
  - CROSS-CHECKS the declarations for internal consistency (declared scope vs the scope
    rule, closure/summary/glance vs contracts.states, bubble order, forbidden phrases).
Any mismatch raises; nothing is silently corrected.

tests/contract/test_golden_fixtures.py re-runs this in memory and fails if the committed
JSON differs, so the JSON is never hand-edited.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from noteguard.contracts import ids, states  # noqa: E402
from noteguard.contracts.api_models import ChangeView, GlanceView  # noqa: E402
from noteguard.contracts.forbidden_phrases import find_forbidden  # noqa: E402
from noteguard.contracts.spans import statement_at  # noqa: E402
from noteguard.contracts.types import (  # noqa: E402
    ABSENCE_SAFE_EXTRACTION,
    AbsenceFinding,
    BubbleStatus,
    CheckRun,
    ClosureBlocker,
    ClosureView,
    EncounterSnapshot,
    Evidence,
    Flag,
    QuestionBubble,
    Ruleset,
    Summary,
    SummaryClaim,
    TimelineEntry,
)

EXPECTED = ROOT / "fixtures" / "expected"
ENCOUNTERS = ROOT / "fixtures" / "encounters"
SGT = timezone(timedelta(hours=8))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


DECL = _load_module("golden_declarations", EXPECTED / "declarations.py")
AUTHOR = _load_module("author_fixtures", ROOT / "fixtures" / "author_fixtures.py")
RULESET = Ruleset.model_validate(json.loads((ROOT / "rulesets" / "v1.json").read_text(encoding="utf-8")))
RULES = {r.rule_id.value: r for r in RULESET.rules}
TEMPLATES = {t.template_id: t for t in RULESET.question_templates}


class GoldenError(AssertionError):
    pass


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise GoldenError(msg)


def _time(hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(*AUTHOR.DAY, h, m, tzinfo=SGT).astimezone(timezone.utc)


def _run_id(scenario: str) -> str:
    return AUTHOR.fid(f"run/{scenario}")


class Enc:
    """Index over one fixture encounter file."""

    def __init__(self, ref: str):
        self.raw = json.loads((ENCOUNTERS / f"{ref}.json").read_text(encoding="utf-8"))
        self.snapshot = EncounterSnapshot.model_validate(self.raw)
        self.ref = ref
        self.encounter_id = self.snapshot.encounter.encounter_id
        self.src = {s.external_id[len(ref) + 1:].lower(): s for s in self.snapshot.sources}
        self.ver = {(s.source_id, v.version): v for s in self.snapshot.sources for v in self.snapshot.versions
                    if v.source_id == s.source_id}
        self.ext = {e.source_version_id: e for e in self.snapshot.extractions}
        self.staff = {s.staff_id: s for s in self.snapshot.staff}

    def version(self, key: str, n: int):
        return self.ver[(self.src[key].source_id, n)]

    def subject(self, text: str) -> str:
        for key, s in self.src.items():
            text = text.replace("{src:" + key + "}", s.source_id)
        _check("{src:" not in text, f"unresolved source placeholder in {text!r}")
        return text

    def computed_scope(self, cutoff: datetime) -> list[tuple[str, int]]:
        """Scope rule from engine_api.run_checks (cross-check only)."""
        rows = []
        for key, s in self.src.items():
            if s.source_time > cutoff:
                continue
            vs = [v for v in self.snapshot.versions if v.source_id == s.source_id and v.version_time <= cutoff]
            if vs:
                v = max(vs, key=lambda v: v.version)
                rows.append((s.source_time, v.received_at, v.source_version_id, key, v.version))
        return [(k, n) for *_, k, n in sorted(rows)]

    def evidence(self, d: dict) -> Evidence:
        v = self.version(d["src"], d["ver"])
        ext = self.ext[v.source_version_id]
        if d["role"] == "extraction_gap":
            page = next(p for p in ext.pages if p.page == d["page"])
            _check(page.char_count == 0 or ext.status.value != "complete", f"gap declared on a read page: {d}")
            start = end = page.start
            pno = page.page
        else:
            n = ext.text.count(d["quote"])
            _check(n == 1, f"quote must occur exactly once in {d['src']} v{d['ver']} (found {n}): {d['quote']!r}")
            start = ext.text.index(d["quote"])
            end = start + len(d["quote"])
            _check(statement_at(ext.text, start, end), f"quote is not a statement span: {d['quote']!r}")
            pno = None
            for p in ext.pages:
                if p.start <= start and end <= p.end:
                    pno = p.page
            _check(not ext.pages or pno is not None, f"quote not inside one page: {d['quote']!r}")
        return Evidence(note_version_id=v.source_version_id, start=start, end=end, page=pno,
                        quote=ext.text[start:end], quote_sha256=ids.quote_sha256(ext.text[start:end]),
                        role_in_flag=d["role"], evidence_revision=d["rev"])

    def label(self, key: str) -> str:
        s = self.src[key]
        return f"{s.title} ({self.staff[s.author_staff_id].display_name}, {s.source_time.astimezone(SGT):%H:%M})"


def _order_key(enc: Enc, ev: Evidence):
    v = next(v for v in enc.snapshot.versions if v.source_version_id == ev.source_version_id)
    s = next(s for s in enc.snapshot.sources if s.source_id == v.source_id)
    return (s.source_time, v.received_at, v.source_version_id, ev.start, ev.role_in_flag.value)


def build(name: str, built: dict[str, dict]) -> dict:
    d = DECL.SCENARIOS[name]
    enc = Enc(d["encounter"])
    cutoff = _time(d["cutoff"])
    evaluated_at = _time(d["evaluated_at"])
    run_id = _run_id(name)

    # --- scope (declared by hand, cross-checked against the scope rule) ---
    scope = d["scope"]
    _check(scope == enc.computed_scope(cutoff), f"{name}: declared scope {scope} != scope rule {enc.computed_scope(cutoff)}")
    scope_versions = [enc.version(k, n) for k, n in scope]
    run = CheckRun(run_id=run_id, encounter_id=enc.encounter_id, source_cutoff=cutoff, ruleset_version="v1",
                   registry_version="v1", source_set_hash=ids.source_set_hash([v.sha256 for v in scope_versions]),
                   started_at=evaluated_at, completed_at=evaluated_at, outcome=d["outcome"])
    unread = [v for v in scope_versions if enc.ext[v.source_version_id].status not in ABSENCE_SAFE_EXTRACTION]
    _check((d["outcome"] == "completed_with_extraction_gaps") == bool(unread), f"{name}: outcome vs unread sources")

    # --- flags ---
    flags: dict[tuple[str, str], Flag] = {}
    pharmacists = {m.staff_id for m in enc.snapshot.memberships
                   if enc.staff[m.staff_id].role.value == "pharmacist"}
    for f in d["flags"]:
        rule = RULES[f["rule"]]
        _check(rule.enabled, f"{name}: flag declared for disabled rule {f['rule']}")
        subject = enc.subject(f["subject"])
        evidence = tuple(sorted((enc.evidence(e) for e in f["evidence"]), key=lambda ev: _order_key(enc, ev)))
        owner = AUTHOR.staff_id(f["owner"])
        affected = tuple(sorted(AUTHOR.staff_id(k) for k in f["affected"]))
        # cross-check the affected-contributor convention
        authors = {next(s.author_staff_id for s in enc.snapshot.sources
                        if any(v.source_id == s.source_id and v.source_version_id == ev.source_version_id
                               for v in enc.snapshot.versions)) for ev in evidence}
        if rule.owner_routing.value == "responsible_clinician_plus_pharmacy":
            authors |= pharmacists
        _check(set(affected) == authors - {owner}, f"{name}: {f['rule']} affected contributors != convention")
        if int(rule.default_tier) == 1 or rule.owner_routing.value.startswith("responsible_clinician"):
            _check(owner == enc.snapshot.encounter.responsible_clinician_id, f"{name}: {f['rule']} owner must be RC")
        _check(f["tier"] == int(rule.default_tier), f"{name}: {f['rule']} tier != rule default")
        first = f.get("first_run", name)
        created = _time(DECL.SCENARIOS[first]["evaluated_at"])
        flag = Flag(
            flag_id=ids.flag_id(f["rule"], enc.encounter_id, subject), tier=f["tier"], category=rule.category,
            title=rule.title, reason=f["reason"], evidence=evidence, owner_staff_id=owner,
            check_version=ids.check_version("v1", f["rule"], rule.version, "v1"), created_at=created,
            rule_id=f["rule"], lens=rule.lens, subject_key=subject, state=f.get("state", "open"),
            revision=f.get("revision", 1), evidence_revision=f.get("evidence_revision", 1),
            affected_contributor_ids=affected, question=f.get("question"),
            source_changed_since_flag=f.get("source_changed", False),
            first_run_id=_run_id(first), last_run_id=run_id,
        )
        _check(flag.state.value not in {"dismissed", "resolved", "accepted", "edited"} or False,
               f"{name}: engine output may not contain human-only states")
        flags[(f["rule"], subject)] = flag

    if d["prior"]:
        prior_ids = {fl["flag_id"] for fl in built[d["prior"]]["flags"]}
        _check(prior_ids <= {fl.flag_id for fl in flags.values()}, f"{name}: a prior flag vanished (flags never disappear)")

    def flag_for(key):
        if key is None:
            return None
        return flags[(key[0], enc.subject(key[1]))]

    # --- bubbles ---
    bubble_decls = d["bubbles"]
    if isinstance(bubble_decls, str):
        base = DECL.SCENARIOS[bubble_decls.split(":", 1)[1].split(" ")[0]]["bubbles"]
        bubble_decls = []
        for b in base:
            b = dict(b)
            b.update(d["bubbles_override"].get((b["template"], b["subject"]), {}))
            bubble_decls.append(b)
    bubbles = []
    for b in bubble_decls:
        tpl = TEMPLATES[b["template"]]
        subject = enc.subject(b["subject"])
        fl = flag_for(b["flag"])
        if b["evidence"] == "flag":
            evidence = fl.evidence
        else:
            evidence = tuple(sorted((enc.evidence(e) for e in b["evidence"]), key=lambda ev: _order_key(enc, ev)))
        absence = None
        if b["status"] in ("not_documented_in_supplied_sources", "incomplete_extraction"):
            _check(tpl.answer_mode.value == "absence_search", f"{name}: absence status on non-search template")
            absence = AbsenceFinding(
                question_template_id=tpl.template_id, terms_searched=tuple(b["terms"]), registry_version="v1",
                sources_searched=tuple({"note_version_id": v.source_version_id,
                                        "extraction_status": enc.ext[v.source_version_id].status}
                                       for v in scope_versions),
                cutoff=cutoff, status=b["status"])
        bubbles.append(QuestionBubble(
            bubble_id=ids.bubble_id(tpl.template_id, enc.encounter_id, subject), question_template_id=tpl.template_id,
            question=b["question"], subject_key=subject, status=b["status"], evidence=evidence, cutoff=cutoff,
            uncertainty_note=b["uncertainty"], flag_id=fl.flag_id if fl else None, absence=absence, rank=tpl.rank))
    _check([(x.rank, x.subject_key) for x in bubbles] == sorted((x.rank, x.subject_key) for x in bubbles),
           f"{name}: bubbles not in (rank, subject_key) order")

    # --- changes (required subset; ChangeView roles: from=origin, to=claim) ---
    change_decls = d["required_changes"]
    if isinstance(change_decls, str):
        change_decls = DECL.SCENARIOS[change_decls.split(":", 1)[1]]["required_changes"]
    changes = [ChangeView(kind=k, subject_key=s,
                          from_evidence=enc.evidence({"src": a[0], "ver": a[1], "role": "origin", "quote": a[2], "rev": 1}),
                          to_evidence=enc.evidence({"src": b[0], "ver": b[1], "role": "claim", "quote": b[2], "rev": 1}))
               for k, s, a, b in change_decls]

    # --- closure (declared by hand; cross-checked against states.blocks_closure) ---
    cl = d["closure"]
    blockers = [flag_for(k) for k in cl["tier1"]]
    tier2 = [flag_for(k) for k in cl["tier2"]]
    _check({f.flag_id for f in blockers} == {f.flag_id for f in flags.values() if states.blocks_closure(f.tier, f.state)},
           f"{name}: declared Tier 1 blockers != states.blocks_closure")
    _check({f.flag_id for f in tier2} == {f.flag_id for f in flags.values()
                                          if int(f.tier) == 2 and states.is_unresolved(f.tier, f.state)},
           f"{name}: declared Tier 2 open != states.is_unresolved")
    t3 = sum(1 for f in flags.values() if int(f.tier) == 3 and states.is_unresolved(f.tier, f.state))
    _check(cl["tier3_count"] == t3, f"{name}: tier3 count")
    expected_status = "blocked" if blockers else ("clear_with_open_tier2" if tier2 else "clear")
    _check(cl["status"] == expected_status, f"{name}: closure status")

    def blocker(f: Flag) -> ClosureBlocker:
        return ClosureBlocker(flag_id=f.flag_id, tier=f.tier, state=f.state, owner_staff_id=f.owner_staff_id,
                              opened_at=f.created_at)

    closure = ClosureView(encounter_id=enc.encounter_id, cutoff=cutoff, status=cl["status"],
                          tier1_blockers=tuple(blocker(f) for f in blockers),
                          tier2_open=tuple(blocker(f) for f in tier2), tier3_open_count=t3, decisions=())

    # --- summary (claims declared by hand; cross-checked against the claim composition rule) ---
    open_pri = [flag_for(k) for k in d["summary_open_priorities"]]
    _check({f.flag_id for f in open_pri} == {f.flag_id for f in flags.values()
                                             if int(f.tier) in (1, 2) and states.is_unresolved(f.tier, f.state)},
           f"{name}: summary open priorities != unresolved Tier 1/2")
    by_key = {(x.question_template_id, x.subject_key): x for x in bubbles}
    top = [by_key[(t, enc.subject(s))] for t, s in d["summary_top_questions"]]
    _check([x.bubble_id for x in top] == [x.bubble_id for x in bubbles if x.status != BubbleStatus.DOCUMENTED][:3],
           f"{name}: top questions != first three non-documented bubbles")
    staff_name = {s.staff_id: s.display_name for s in enc.snapshot.staff}
    status_label = {"conflicting": "conflicting", "not_documented_in_supplied_sources": "not documented in supplied sources",
                    "incomplete_extraction": "incomplete extraction", "requires_human_review": "requires human review",
                    "documented": "documented"}
    claims = [SummaryClaim(template="open_priority",
                           params={"flag_id": f.flag_id, "rule_id": f.rule_id.value, "tier": int(f.tier),
                                   "state": f.state.value, "owner_staff_id": f.owner_staff_id},
                           text=f"Tier {int(f.tier)} \u00b7 {f.title} \u00b7 owner {staff_name[f.owner_staff_id]} \u00b7 {f.state.value}",
                           evidence=f.evidence) for f in open_pri]
    claims += [SummaryClaim(template="top_question",
                            params={"bubble_id": x.bubble_id, "question_template_id": x.question_template_id,
                                    "status": x.status.value},
                            text=f"{x.question} \u2014 {status_label[x.status.value]}", evidence=x.evidence) for x in top]
    timeline = []
    for v in scope_versions:
        s = next(s for s in enc.snapshot.sources if s.source_id == v.source_id)
        timeline.append(TimelineEntry(source_id=s.source_id, note_version_id=v.source_version_id, version=v.version,
                                      author_staff_id=s.author_staff_id, discipline=s.discipline, source_type=s.source_type,
                                      source_time=s.source_time, extraction_status=enc.ext[v.source_version_id].status,
                                      title=s.title))
    summary = Summary(encounter_id=enc.encounter_id, encounter_ref=enc.ref, patient_ref=enc.snapshot.patient.patient_ref,
                      generated_at=evaluated_at, cutoff=cutoff, ruleset_version="v1", registry_version="v1",
                      closure_status=cl["status"], timeline=tuple(timeline), claims=tuple(claims))

    glance = GlanceView(encounter_id=enc.encounter_id, cutoff=cutoff, closure_status=cl["status"],
                        open_tier1=sum(1 for f in flags.values() if int(f.tier) == 1 and states.is_unresolved(f.tier, f.state)),
                        open_tier2=len(tier2), open_tier3=t3,
                        tier1_owner_ids=tuple(sorted({f.owner_staff_id for f in blockers})),
                        top_bubble_ids=tuple(x.bubble_id for x in top), top_bubble_statuses=tuple(x.status for x in top))

    # --- lint every human-facing string ---
    texts = [f.reason for f in flags.values()] + [f.question or "" for f in flags.values()]
    texts += [x.question for x in bubbles] + [x.uncertainty_note for x in bubbles] + [c.text for c in claims]
    texts += [m[2] for m in d["must_not_flag"]]
    for t in texts:
        _check(find_forbidden(t) is None, f"{name}: forbidden phrase {find_forbidden(t)!r} in {t!r}")

    must_not = [{"rule_id": r, "subject_key": enc.subject(s) if s not in ("*", "encounter") else s, "why": why}
                for r, s, why in d["must_not_flag"]]
    for m in must_not:
        hits = [f for (r, s), f in flags.items()
                if (m["rule_id"] in ("*", r)) and (m["subject_key"] in ("*", "encounter") or m["subject_key"] == s)]
        _check(not hits, f"{name}: must-not-flag {m} contradicts a declared flag")

    dump = lambda m: m.model_dump(mode="json", by_alias=True)  # noqa: E731
    return {
        "scenario": name,
        "encounter_ref": enc.ref,
        "encounter_id": enc.encounter_id,
        "cutoff": dump(run)["source_cutoff"],
        "evaluated_at": dump(run)["started_at"],
        "run_id": run_id,
        "prior_scenario": d["prior"],
        "comparison": "flags, bubbles and summary claims: EXACT set equality on the fields in fixtures/expected/README.md; required_changes: must be present",
        "run": dump(run),
        "flags": [dump(f) for f in sorted(flags.values(), key=lambda f: (int(f.tier), f.rule_id.value, f.subject_key))],
        "must_not_flag": must_not,
        "must_not_suppress_note": d["must_not_suppress_note"],
        "bubbles": [dump(x) for x in bubbles],
        "required_changes": [dump(c) for c in changes],
        "summary": dump(summary),
        "closure": dump(closure),
        "glance": dump(glance),
    }


def build_all() -> dict[str, dict]:
    built: dict[str, dict] = {}
    for name in DECL.SCENARIOS:
        built[name] = build(name, built)
    return built


def review_sheet(built: dict[str, dict]) -> str:
    staff = {AUTHOR.staff_id(k): v[0] for k, v in AUTHOR.STAFF.items()}
    lines = ["# Golden fixtures \u2014 review sheet for CP0 sign-off", "",
             "Generated by `fixtures/expected/materialize.py` from the hand-written `declarations.py`.",
             "Read this, not the JSON. Sign off by adding your initials and time at the bottom.", ""]
    for name, g in built.items():
        enc = Enc(g["encounter_ref"])
        vlabel = {}
        for key, s in enc.src.items():
            for v in enc.snapshot.versions:
                if v.source_id == s.source_id:
                    vlabel[v.source_version_id] = f"{enc.label(key)} v{v.version}"
        lines += [f"## {name}", "",
                  f"Cutoff {name.split('_')[1][:2]}:{name.split('_')[1][2:4]} SGT"
                  + (f"; rerun after {g['prior_scenario']} (prior flags supplied)" if g["prior_scenario"] else "; fresh run")
                  + f"; outcome `{g['run']['outcome']}`; closure **{g['closure']['status']}**.", "",
                  "| Rule | Tier | Subject | Owner | Also affected | State (rev/ev) | Evidence |", "|---|---|---|---|---|---|---|"]
        for f in g["flags"]:
            ev = "<br>".join(f"{e['role_in_flag']}: {vlabel[e['note_version_id']]} \u201c{e['quote'] or '[no text layer, p.' + str(e['page']) + ']'}\u201d"
                             for e in f["evidence"])
            extra = " \u00b7 source changed" if f["source_changed_since_flag"] else ""
            lines.append(f"| {f['rule_id']} | {f['tier']} | `{f['subject_key'][:40]}` | {staff[f['owner_staff_id']]} | "
                         f"{', '.join(staff[a] for a in f['affected_contributor_ids']) or '\u2014'} | "
                         f"{f['state']} ({f['revision']}/{f['evidence_revision']}){extra} | {ev} |")
        if not g["flags"]:
            lines.append("| \u2014 | | no flags | | | | |")
        lines += ["", "**Must not flag:**", ""]
        lines += [f"- `{m['rule_id']}` on `{m['subject_key'][:40]}` \u2014 {m['why']}" for m in g["must_not_flag"]]
        if g["must_not_suppress_note"]:
            lines += [f"- {g['must_not_suppress_note']}"]
        lines += ["", "**Bubbles** (rank order):", ""]
        for b in g["bubbles"]:
            lines.append(f"- {b['rank']}. {b['question']} \u2192 `{b['status']}`"
                         + (f" (searched {len(b['absence']['sources_searched'])} sources for {', '.join(b['absence']['terms_searched'])})"
                            if b["absence"] else ""))
        if not g["bubbles"]:
            lines.append("- none")
        lines += ["", "**Required changes:** " + ("; ".join(
            f"`{c['kind']}` {c['subject_key']}: \u201c{c['from_evidence']['quote']}\u201d \u2192 \u201c{c['to_evidence']['quote']}\u201d"
            for c in g["required_changes"]) or "none"), ""]
    lines += ["---", "", "Signed off (CP0): ________  date/time SGT: ________", ""]
    return "\n".join(lines)


def main() -> None:
    built = build_all()
    for name, g in built.items():
        (EXPECTED / f"{name}.json").write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(name, len(g["flags"]), "flags,", len(g["bubbles"]), "bubbles,", len(g["summary"]["claims"]), "claims")
    (EXPECTED / "REVIEW_SHEET.md").write_text(review_sheet(built), encoding="utf-8")


if __name__ == "__main__":
    main()
