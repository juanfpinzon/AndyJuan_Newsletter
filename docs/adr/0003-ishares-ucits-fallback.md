# ADR 0003: iShares UCITS Funds Use YAML Fallback for v0.1

## Status

Accepted

## Context

The seeded portfolio holds iShares UCITS products such as QDVE, EGLN, and PPFD. Their live
holdings pages do not share the same stable JSON path as the simple US fixture used in tests, and
Phase 2 does not include a validated production-safe scrape for those regional variants.

## Decision

Keep the narrow US JSON adapter used by the existing fixtures and treat `config/etf_holdings.yaml`
as the authoritative source for iShares UCITS funds in v0.1. When the live request fails, the
resolver falls back to YAML and logs `lookthrough_fallback_used`.

## Consequences

- Phase 2 remains deterministic for the current portfolio without pretending the UCITS scrape is
  production-ready.
- Operational visibility is preserved because fallback usage is logged.
- A future phase can replace the fallback with a validated international endpoint without changing
  the resolver contract.
