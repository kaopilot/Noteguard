"""Governance and the AI gate (B4). Nothing here learns online (L13, Section 11).

- ``approval``: the approval check at ruleset load; the runtime reads only a pinned, approved bundle.
- ``propose``: offline RuleProposals from exported feedback; refuses protected-floor changes.
- ``evaluate``: offline per-rule evaluation on labelled fixtures; the Tier 1 recall release gate.
- ``aggregate``: PHI-minimised aggregate risk cells (no content, no ids, small cells "<5").
- ``ai_drafting``: optional drafting over a verified evidence cluster; off by default (Section 9).
"""
