# CCR-04 — Aggregate view: declare it in OpenAPI; add owner response time
Raised by: B4, session B4.1   Date: 23 Sep 2026

What changes (files, fields, values):
  1. `noteguard/api/routes/aggregate.py` (B4): `response_model=AggregateView` (today `response_model=None`
     so that `docs/openapi.json` stays in sync). Integrator: `make types` (openapi.json, schema.gen.ts).
     Additive: new component schemas `AggregateView`, `AggregateCell`; the 200 response gains a `$ref`.
  2. `noteguard/contracts/api_models.py` `AggregateCell`: add
     `response_time_bucket: str | None = None` — time from `created_at` to the first human decision,
     bucketed `"<1h" | "1-4h" | ">4h"`, or `"none_yet"` when no decision exists. Additive, optional.
Why (the failing case or missing capability):
  - Section 11 lists "owner response time" as an aggregate dimension; REVIEW_STANDARD_OBSERVATIONS §4.2
    lists "time to adjudicate". B2's `AggregateRow` already carries `first_decision_at`, but the frozen
    `AggregateCell` has no field for it, so B4 cannot report it. Disposition is already visible through
    `state` (dismissed, resolved, accepted, ...).
  - `AggregateView` is absent from `docs/openapi.json` (B0's stub never declared it), so
    `schema.gen.ts` has no type for B3's aggregate page.
Lanes affected and what each must do:
  - Integrator: land (2), then `make types`.
  - B4: set `response_model=AggregateView`, fill `response_time_bucket` in `governance/aggregate.py`
    (the bucket joins the cell key, so "<5" suppression still applies), and extend
    `test_aggregate_no_content_or_ids`.
  - B3: build the aggregate page against the generated type (cut order allows endpoint-only).
  - B2: none for this CCR. (Separately, see the B4 handoff: B2's
    `test_aggregate_route_is_b4_placeholder_behind_b2_authz` asserts the 501 placeholder and fails
    once B4 lands.)
Golden fixture impact: none.
Status: approved (@k, 23 Sep 2026); part 1 landed; part 2 with B4
