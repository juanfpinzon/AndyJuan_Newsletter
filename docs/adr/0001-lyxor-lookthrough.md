# ADR 0001: Lyxor / Amundi Look-through Strategy

## Status

Accepted

## Context

The BNKE holding source sits behind markup that has changed repeatedly and is not as stable as
the iShares, VanEck, SSgA, or Global X feeds. Phase 2a still needs deterministic exposure
resolution for the current portfolio.

## Decision

Implement a minimal Lyxor adapter that can parse a simple holdings table when the markup is
present, but treat parse failure as a normal degraded mode. The adapter raises a typed
`LookthroughFailure(issuer="lyxor", etf_id=...)` so the resolver can fall back to
`config/etf_holdings.yaml` without hiding the source failure.

## Consequences

- The portfolio keeps producing complete exposure data even when Amundi pages drift.
- Lyxor scraping stays intentionally narrow instead of chasing brittle page variants.
- Operational visibility is preserved because the resolver logs `lookthrough_fallback_used`.
