# ADR 0002: Exposure Weights Use Invested Cost Basis

## Status

Accepted

## Context

Phase 2 needs deterministic exposure math before live pricing is threaded through the broader
pipeline. The portfolio model already stores `shares` and per-share `cost_basis_eur`, and the
seeded Snowball fixture reconciles exactly on invested cost basis.

## Decision

`src/exposure/resolver.py` computes portfolio weights from `shares × cost_basis_eur`, not from
current market value. This keeps exposure calculation independent from the pricing phase while
still reflecting actual capital allocated to each position.

## Consequences

- Exposure output is stable even when price snapshots are unavailable.
- Reported concentration reflects invested capital, not intraday market drift.
- A future market-value view remains possible once the renderer has a concrete need for both.
