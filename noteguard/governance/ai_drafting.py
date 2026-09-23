"""Optional AI drafting over a verified evidence cluster (B4; Section 9, L10, L17, OPEN-5).

OFF BY DEFAULT. The application is fully functional without it; when disabled nothing is sent
anywhere and the status says "AI drafting disabled" (never a fake result, L10).

What it may do: draft a short, citation-bound explanation of ONE flag the deterministic engine has
already raised. It never decides whether a flag exists, its tier, owner or state: none of those is
sent to the model, and an output carrying any key other than the fixed schema is discarded.

Path (each step fails closed to the deterministic rule text, ``flag.reason``):
1. Cluster: the flag's span evidence with a non-empty quote whose sha256 matches ``quote_sha256``;
   ids E1..En. Only the flag title and these quotes are used; never whole notes.
2. Egress: ``noteguard.redaction.prepare_egress`` (B2) mints a ``QualifiedRedactedText``; a refusal
   means no call. The provider must call ``payload.assert_qualified()`` (contracts/egress.py).
3. Provider call on a worker thread with a hard timeout; a timeout or any exception (e.g. a 5xx) is
   "unavailable"; consecutive failures open a circuit breaker for a cooldown.
4. Validator (``validate_output``): discard on the first failure (codes below).

Known limits (declared): entity and dose checks are bounded by the term registry (a drug the
registry does not know is not recognised); certainty is two-level (registry uncertainty cue or not);
polarity is checked only as "a negated sentence must cite a negated quote"; a timed-out worker
thread keeps running until the provider returns. No route calls this module yet (the contract has
only /api/ai/status); see docs/decisions/B4.md.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

from noteguard.contracts import ids
from noteguard.contracts.api_models import AIStatusView
from noteguard.contracts.egress import DraftingProvider, QualifiedRedactedText, Redactor
from noteguard.contracts.forbidden_phrases import find_forbidden
from noteguard.contracts.types import AIDraftStatus, Certainty, CueKind, Flag, TermRegistry

S = AIDraftStatus
DETAIL_DISABLED = "AI drafting disabled"
DETAIL_UNAVAILABLE = "AI drafting unavailable; showing rule explanation"
DETAIL_REJECTED = "AI draft discarded by the validator; showing rule explanation"
DETAIL_VALIDATED = "AI draft (validated against the cited evidence; not a clinical judgement)"
DETAIL_NO_DRAFT_YET = "AI drafting enabled; no draft observed yet; showing rule explanation"

# Codes (machine codes only; never content).
EMPTY_CLUSTER = "empty_cluster"
QUOTE_HASH_MISMATCH = "quote_hash_mismatch"
EGRESS_NOT_QUALIFIED = "egress_not_qualified"
TIMEOUT = "timeout"
PROVIDER_ERROR = "provider_error"
CIRCUIT_OPEN = "circuit_open"
SCHEMA_INVALID = "schema_invalid"
EXTRA_FIELD = "extra_field"
MISSING_EVIDENCE_IDS = "missing_evidence_ids"
UNKNOWN_EVIDENCE_ID = "unknown_evidence_id"
ENTITY_NOT_IN_EVIDENCE = "entity_not_in_evidence"
DOSE_NOT_IN_EVIDENCE = "dose_not_in_evidence"
CERTAINTY_RAISED = "certainty_raised"
POLARITY_UNSUPPORTED = "polarity_unsupported"
FORBIDDEN_PHRASE = "forbidden_phrase"

_TOP_KEYS = frozenset({"sentences"})
_ITEM_KEYS = frozenset({"text", "evidence_ids"})
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class AIConfig:
    enabled: bool = False  # OPEN-5: off by default
    timeout_s: float = 3.0
    breaker_failures: int = 3  # consecutive unavailable outcomes that open the breaker
    breaker_cooldown_s: float = 60.0


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str  # "E1".. within one cluster
    quote: str


@dataclass(frozen=True)
class DraftResult:
    status: AIDraftStatus
    text: str  # validated draft, or the deterministic rule text
    detail: str  # UI label
    code: str | None = None  # why it fell back (None when validated or disabled)
    cited_evidence_ids: tuple[str, ...] = ()


def _norm(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()


def _has_phrase(text: str, phrase: str) -> bool:
    p = re.escape(phrase.lower())
    return re.search(rf"(?<![a-z0-9]){p}(?![a-z0-9])", text) is not None if phrase[:1].isalnum() else phrase in text


def build_cluster(flag: Flag) -> tuple[EvidenceItem, ...]:
    """Verified span evidence only. Raises ValueError(code) if a quote does not match its hash."""
    items = []
    for ev in flag.evidence:
        if not ev.quote:
            continue  # extraction gaps and encounter-record evidence carry no quote
        if ids.quote_sha256(ev.quote) != ev.quote_sha256:
            raise ValueError(QUOTE_HASH_MISMATCH)
        items.append(EvidenceItem(f"E{len(items) + 1}", ev.quote))
    return tuple(items)


def build_prompt(flag: Flag, cluster: tuple[EvidenceItem, ...]) -> str:
    lines = ["Explain this review flag in at most three short sentences, using ONLY the quoted evidence.",
             "Do not add any drug, dose, allergen, test or diagnosis that the evidence does not contain.",
             "Do not state more certainty than the evidence. Do not mention tier, owner or state.",
             'Reply with JSON only: {"sentences": [{"text": "...", "evidence_ids": ["E1"]}]}',
             f"Flag: {flag.title}"]
    lines += [f"{e.evidence_id}: \"{e.quote}\"" for e in cluster]
    return "\n".join(lines)


def _certainty(text: str, registry: TermRegistry) -> Certainty:
    cues = registry.cues.get(CueKind.UNCERTAINTY, ())
    return Certainty.POSSIBLE if any(_has_phrase(text, c) for c in cues) else Certainty.ASSERTED


def _negated(text: str, registry: TermRegistry) -> bool:
    return any(_has_phrase(text, c) for c in registry.cues.get(CueKind.NEGATION, ()))


def _entities(text: str, registry: TermRegistry) -> set[str]:
    found = {t.key for t in registry.terms if any(_has_phrase(text, s) for s in t.synonyms)}
    found |= {f"denial:{d.phrase}" for d in registry.allergy_denials if _has_phrase(text, d.phrase)}
    return found


def _doses(text: str, registry: TermRegistry) -> set[str]:
    units = "|".join(sorted((re.escape(u.lower()) for u in registry.dose_units), key=len, reverse=True))
    return {f"{float(n.replace(',', ''))}{u}" for n, u in
            re.findall(rf"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*({units})(?![a-z])", text)}


def validate_output(raw: str, cluster: tuple[EvidenceItem, ...],
                    registry: TermRegistry) -> tuple[tuple[tuple[str, tuple[str, ...]], ...] | None, str | None]:
    """Returns ((sentence, evidence_ids), ...) and None, or None and the first failure code."""
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError):
        return None, SCHEMA_INVALID
    if not isinstance(doc, dict) or not isinstance(doc.get("sentences"), list) or not doc["sentences"]:
        return None, SCHEMA_INVALID
    if set(doc) != _TOP_KEYS:
        return None, EXTRA_FIELD  # e.g. a tier, owner or state: not in the schema at all
    quotes = {e.evidence_id: _norm(e.quote) for e in cluster}
    out = []
    for item in doc["sentences"]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
            return None, SCHEMA_INVALID
        if set(item) != _ITEM_KEYS:
            return None, EXTRA_FIELD
        cited = item.get("evidence_ids")
        if not isinstance(cited, list) or not cited:
            return None, MISSING_EVIDENCE_IDS
        if any(c not in quotes for c in cited):
            return None, UNKNOWN_EVIDENCE_ID
        text, source = _norm(item["text"]), " \n ".join(quotes[c] for c in cited)
        if find_forbidden(text):
            return None, FORBIDDEN_PHRASE
        if not _entities(text, registry) <= _entities(source, registry):
            return None, ENTITY_NOT_IN_EVIDENCE
        if not _doses(text, registry) <= _doses(source, registry):
            return None, DOSE_NOT_IN_EVIDENCE
        if _certainty(text, registry) > min(_certainty(quotes[c], registry) for c in cited):
            return None, CERTAINTY_RAISED
        if _negated(text, registry) and not any(_negated(quotes[c], registry) for c in cited):
            return None, POLARITY_UNSUPPORTED
        out.append((item["text"].strip(), tuple(cited)))
    return tuple(out), None


@dataclass
class _Breaker:
    failures: int = 0
    open_until: float = 0.0


@dataclass
class Drafter:
    """One per process. ``provider`` is required when enabled (never a stand-in that claims success)."""

    config: AIConfig = field(default_factory=AIConfig)
    provider: DraftingProvider | None = None
    redactor_factory: Callable[[Iterable[str]], Redactor] | None = None
    clock: Callable[[], float] = time.monotonic
    _breaker: _Breaker = field(default_factory=_Breaker)
    _last: AIDraftStatus | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.config.enabled and self.provider is None:
            raise ValueError("ai_enabled_without_provider")

    def status_view(self) -> AIStatusView:
        """For /api/ai/status. Reports only what was observed (L10)."""
        if not self.config.enabled:
            return AIStatusView(status=S.DISABLED, detail=DETAIL_DISABLED)
        if self.clock() < self._breaker.open_until:
            return AIStatusView(status=S.UNAVAILABLE_FALLBACK, detail=DETAIL_UNAVAILABLE)
        if self._last is None:
            return AIStatusView(status=S.UNAVAILABLE_FALLBACK, detail=DETAIL_NO_DRAFT_YET)
        detail = {S.VALIDATED: DETAIL_VALIDATED, S.REJECTED_FALLBACK: DETAIL_REJECTED}.get(self._last, DETAIL_UNAVAILABLE)
        return AIStatusView(status=self._last, detail=detail)

    def _fallback(self, status: AIDraftStatus, code: str, rule_text: str) -> DraftResult:
        self._last = status
        return DraftResult(status, rule_text, DETAIL_REJECTED if status is S.REJECTED_FALLBACK else DETAIL_UNAVAILABLE, code)

    def _unavailable(self, code: str, rule_text: str) -> DraftResult:
        with self._lock:
            self._breaker.failures += 1
            if self._breaker.failures >= self.config.breaker_failures:
                self._breaker.open_until = self.clock() + self.config.breaker_cooldown_s
                self._breaker.failures = 0
        return self._fallback(S.UNAVAILABLE_FALLBACK, code, rule_text)

    def draft(self, flag: Flag, registry: TermRegistry, *, known_names: Iterable[str] = ()) -> DraftResult:
        rule_text = flag.reason
        if not self.config.enabled:
            return DraftResult(S.DISABLED, rule_text, DETAIL_DISABLED)
        if self.clock() < self._breaker.open_until:
            return self._fallback(S.UNAVAILABLE_FALLBACK, CIRCUIT_OPEN, rule_text)
        try:
            cluster = build_cluster(flag)
        except ValueError:
            return self._fallback(S.UNAVAILABLE_FALLBACK, QUOTE_HASH_MISMATCH, rule_text)
        if not cluster:
            return self._fallback(S.UNAVAILABLE_FALLBACK, EMPTY_CLUSTER, rule_text)
        try:
            payload = self._egress(build_prompt(flag, cluster), known_names)
        except ValueError:
            return self._fallback(S.UNAVAILABLE_FALLBACK, EGRESS_NOT_QUALIFIED, rule_text)
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-draft")
        try:
            raw = pool.submit(self.provider.draft, payload, timeout_s=self.config.timeout_s).result(
                timeout=self.config.timeout_s)
        except FutureTimeout:
            return self._unavailable(TIMEOUT, rule_text)
        except Exception:  # noqa: BLE001 - any provider failure (5xx, network, refusal) -> rule text
            return self._unavailable(PROVIDER_ERROR, rule_text)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            self._breaker.failures = 0
        sentences, code = validate_output(raw, cluster, registry)
        if sentences is None:
            return self._fallback(S.REJECTED_FALLBACK, code, rule_text)
        self._last = S.VALIDATED
        cited = tuple(dict.fromkeys(c for _, cs in sentences for c in cs))
        return DraftResult(S.VALIDATED, " ".join(s for s, _ in sentences), DETAIL_VALIDATED, None, cited)

    def _egress(self, text: str, known_names: Iterable[str]) -> QualifiedRedactedText:
        from noteguard.redaction import get_redactor, prepare_egress

        factory = self.redactor_factory or get_redactor
        return prepare_egress(text, redactor=factory(tuple(known_names)))
