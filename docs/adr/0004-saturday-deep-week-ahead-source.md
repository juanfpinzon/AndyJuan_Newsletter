# ADR 0004: Saturday Deep Week-Ahead Items Are Caller-Supplied in v0.1

## Status

Accepted

## Context

Phase 5 introduces `run_deep()` as the Saturday orchestration entry point. The spec notes that
the deep flow "fetches week-ahead calendar (likely from a separate prompt or static config),"
which leaves the source open-ended for v0.1.

The current system already needs a stable deep-mode template and delivery path, but it does not
yet have a validated internal fetcher for week-ahead macro and earnings events. Adding one inside
Phase 5 would expand scope into a new data source and a new failure mode.

## Decision

Keep `src/pipeline/deep.py` as a thin delegate to `run_daily(mode="deep", ...)` and require
`week_ahead_items` to be supplied by the caller in v0.1. That caller can be:

- an operator using `scripts/run_manual.py`
- a future scheduler wrapper
- a later internal fetcher introduced in a separate phase

## Consequences

- Phase 5 stays focused on orchestration and rendering rather than inventing a new calendar data
  source.
- The deep-template contract is explicit: if week-ahead items are available, the template renders
  them; if not, the rest of the Saturday flow still works.
- A later phase can add an internal calendar fetcher without changing the public `run_deep()`
  signature.
