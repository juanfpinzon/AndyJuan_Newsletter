# Phase 2 (a + b + c) Review — branch `phase2-a-b-c`

**Date:** 2026-04-25
**Reviewer:** Lead Planner/Reviewer (Claude)
**Engineer:** Codex
**Scope:** Tasks 2a.1–2a.8, 2b.1–2b.2, 2c.1–2c.3 per `docs/tasks.md`
**Verdict:** **Request changes** — one Critical correctness bug must be fixed before merge; otherwise the implementation is solid and well structured.

---

## Verification

| Check | Result |
|---|---|
| `pytest tests/ -v` | **58 passed** in 4.6s |
| `ruff check src/ scripts/ tests/` | **All checks passed** |
| Coverage on `src/exposure/` (spec: 100%) | **100%** (42 stmts) |
| Coverage on `src/pnl/` (spec: 100%) | **100%** (51 stmts) |
| Entity matcher 30-article fixture (spec: ≥80%) | Passes (test asserts ≥0.8) |
| Snowball totals tie-out (€2,693.16 cost basis) | Passes (`test_portfolio_fixture_matches_seeded_screenshot_totals`) |

> **Note:** `pytest-cov` was missing from the dev environment but is correctly added to `pyproject.toml` `[dev]` extras. Re-running `pip install -e ".[dev]"` will pick it up.

---

## Critical (blocks merge)

### C1. `compute_exposure` ignores `position.shares` — weights are wrong on real portfolio

**File:** `src/exposure/resolver.py:20-27`

```python
total_cost = sum(
    (position.cost_basis_eur for position in positions),     # ← per-share number
    start=Decimal("0"),
)
exposures: dict[str, dict[str, object]] = {}

for position in positions:
    position_weight = position.cost_basis_eur / total_cost   # ← per-share / sum-of-per-share
```

`cost_basis_eur` in `config/portfolio.yaml` is the **per-share** cost basis (verified: `Σ shares × cost_basis_eur = €2,693.16` matches Snowball, exactly what `tests/test_pnl.py::test_portfolio_fixture_matches_seeded_screenshot_totals` asserts). `compute_exposure` divides per-share cost by a sum of per-share costs, which produces incorrect weights for any portfolio with non-uniform share counts.

**Numeric impact on the seed portfolio:**

| Position | Buggy weight | Correct weight |
|---|---|---|
| SPYY | 18.3% | **20.3%** |
| BNKE | 22.1% | **12.3%** |
| QDVE | 2.6% | **13.0%** |
| Sum of weights | sums to wrong total | sums to 1.0 |

(Reproduced via hand calc: see "Verify" appendix below.)

**Why the test suite missed it:** every `make_position` helper in `tests/test_exposure.py` and `tests/test_lookthrough_resolver.py` defaults `shares=Decimal("1")`. The bug is silenced by uniform shares.

**Required fix:**

```python
total_cost = sum(
    (position.shares * position.cost_basis_eur for position in positions),
    start=Decimal("0"),
)
...
for position in positions:
    position_weight = (position.shares * position.cost_basis_eur) / total_cost
```

**Required test addition:** add at least one exposure test that uses non-unit `shares` and seeds two positions where the per-share cost basis disagrees with shares-weighted cost basis (e.g., one position with `shares=2, cost_basis_eur=100` and another with `shares=10, cost_basis_eur=10`). The buggy code would compute equal 50/50 weights; the correct code would yield ~67/33.

---

## Important (should address before merge)

### I1. Exposure uses cost basis, not market value — confirm this is intentional

**File:** `src/exposure/resolver.py`

`compute_exposure(positions, lookthrough_data)` deliberately takes no prices. Concentration is therefore reported on **cost basis** rather than current **market value**. This is a defensible v0.1 choice (no price dependency, deterministic), but it diverges from how investor dashboards typically present exposure. The spec doesn't state which to use.

**Action:** Either (a) confirm cost-basis is intentional and add a one-line ADR (`docs/adr/0002-exposure-on-cost-basis.md`) explaining the choice, or (b) thread `prices: dict[str, PriceSnapshot]` through `compute_exposure` and use `shares × last_eur`.

### I2. iShares URL pattern points at US site — UCITS funds will silently always 404

**File:** `src/lookthrough/adapters/ishares.py:17,20`

```python
base_url = "https://www.ishares.com/us/products"
url = f"{self.base_url}/{etf_id.lower()}/holdings.json"
```

The portfolio's iShares positions (QDVE, EGLN, PPFD) are UCITS-domiciled (Ireland) and live under a different URL hierarchy (typically `www.ishares.com/uk/individual/en/products/...` or `www.ishares.com/de/individual/de/products/...`). The adapter will hit 404 in production for every UCITS fund and silently fall through to `etf_holdings.yaml`. That's not a hard failure (the fallback is by design), but it means the scraper provides ~zero real value for the seed portfolio.

**Action:** Either (a) update the URL pattern + adapter logic to handle UCITS endpoints (and re-test against a real live URL during the spike), or (b) explicitly document this in the Lyxor ADR (or a new one) as an accepted "fallback always wins for iShares UCITS" trade-off so a reader doesn't expect this code to actually run live.

### I3. `refresh_etf_holdings.py` returns 0 when no ETFs are processed

**File:** `scripts/refresh_etf_holdings.py:68-70`

```python
if issuer_totals and all(stats["ok"] == 0 for stats in issuer_totals.values()):
    return 1
return 0
```

The spec acceptance says: *"Returns nonzero exit code if all 5 issuers fail (sanity guardrail)."* When no ETFs are present (or none have a recognized issuer), `issuer_totals` is empty and the script returns 0. That's the wrong signal for ops monitoring. Drop the `issuer_totals and` guard so empty/all-fail both surface as `1`.

---

## Suggestions / Nits

- **N1** `_to_decimal_text` in `src/lookthrough/resolver.py:155-158` performs an inline `from decimal import Decimal` inside the function. Move it to the top with the other imports.
- **N2** `src/lookthrough/adapters/lyxor.py:61` parses `Decimal(text)` directly. Real Amundi pages render weights as `"14.00%"` — the fixture (`bnke.html`) uses bare numbers. Worth stripping `%` for resilience even though the ADR accepts degraded scraping.
- **N3** `src/exposure/models.py:13` types `paths` as `tuple[dict[str, object], ...]`. A `@dataclass(frozen=True) class ExposurePath: source: str; weight: Decimal` would make consumers (renderer in Phase 4) safer to write and easier to read. Consider before Phase 4 starts.
- **N4** `src/pnl/calculator.py:58-65` uses bare `sum(snapshot... for ...)` (no `start=Decimal("0")`). Empty input would return Python `0` (int) and downstream divisions would still work, but explicit `start=Decimal("0")` is the established convention elsewhere in the file and is more defensive.
- **N5** `src/storage/db.py` — `cache_etf_holdings`, `record_llm_call`, and `summarize_llm_costs` each call `init_db(db_path)` independently. For the current call counts this is fine; if `refresh_etf_holdings.py` grows to N≫10 ETFs or runs concurrently, switch to a shared `Database` handle.
- **N6** `src/lookthrough/resolver.py:126-138` and `scripts/refresh_etf_holdings.py:83-95` duplicate `_normalize_issuer`. Factor it to `src/lookthrough/issuers.py` (or similar) so both call sites stay in sync.

---

## Per-task spec compliance

| Task | Acceptance | Status |
|---|---|---|
| **2a.1** Holding + BaseAdapter | Frozen Decimal weight, abstract base | ✅ |
| **2a.2** iShares adapter | IUIT + EGLN fixtures, HTTPError → LookthroughFailure | ✅ (but see I2) |
| **2a.3** VanEck / SSgA / Global X | Shared CSV helper, ≥1 ETF each, error wrapping | ✅ |
| **2a.4** Lyxor adapter + ADR | Degraded mode, typed exception, ADR 0001 written | ✅ |
| **2a.5** Lookthrough resolver | Try-adapter→yaml→raise, `lookthrough_fallback_used` log | ✅ |
| **2a.6** Refresh script | Runs adapters, prints summary, caches to SQLite | ⚠️ See I3 |
| **2a.7** ExposureEntry + resolver | Hand-calc match, reproducible, 100% coverage | ❌ See **C1** |
| **2a.8** Debug script | Default + `--costs` flag | ✅ |
| **2b.1** yfinance client | PriceSnapshot, weekend fallback, single FX pass | ✅ |
| **2b.2** P&L calculator | Per-position + total, ties to €2,693.16 cost basis & €67.52 P&L, 100% coverage | ✅ |
| **2c.1** NewsData.io | Pagination, dedup via `articles_seen`, 429 retry | ✅ |
| **2c.2** Macro RSS | feedparser + ETag/Last-Modified | ✅ |
| **2c.3** Entity matcher | Ticker + alias forms, threshold tunable, 30-article ≥80% | ✅ |

---

## What's good

- **Five-axis review highlights:**
  - *Correctness:* every adapter wraps `httpx.HTTPError` cleanly; resolver's fallback logic is precise; PnL math reconciles to the Snowball screenshot to the cent.
  - *Readability:* `_csv.py` is a clean shared helper; field-name normalization is small and obvious; `EntityMatcher` separates exact-symbol from fuzzy-alias paths with explicit metadata for tie-breaking.
  - *Architecture:* clean `models.py` / `resolver.py` / `adapters/` split per phase; typed exceptions (`LookthroughFailure`, `LookthroughExhausted`, `ExposureComputationError`) keep contracts visible.
  - *Security:* respx mocks all live calls; secrets stay in env; no string-concatenation SQL (sqlite-utils + parameterized `summarize_llm_costs`).
  - *Performance:* `fetch_prices` issues one `yf.download` covering symbols + FX (per spec); RSS reader threads ETags so unchanged feeds short-circuit on 304.
- ADR 0001 is appropriately scoped and documents the fallback contract.
- Frozen dataclasses with `Decimal` money throughout — no float drift surprises.
- 58 tests pass, ruff clean.

---

## Required actions before merge

1. **Fix C1** in `src/exposure/resolver.py` and add a regression test covering non-uniform `shares`.
2. **Address I3** (refresh script empty-totals guardrail) — one-line change.
3. **Resolve I1** with either a brief ADR or the market-value path (one or the other, your call).
4. **Resolve I2** — either fix the iShares URL or document the deferred-to-fallback decision.

Optional but recommended: N3 (typed `ExposurePath`) before Phase 4 renderer work begins.

---

## Verify (appendix)

Hand-calculation reproducing the C1 numeric impact:

```python
from decimal import Decimal
positions = [  # (ticker, shares, cost_basis_eur per share)
    ('BNKE',  '1.1023', '301.551302'),
    ('DFEN',  '6.4643',  '54.140433'),
    ('EGLN',  '0.9627',  '81.790797'),
    ('GDX',   '2.2003', '104.522111'),
    ('GOOGL', '0.5547', '269.713359'),
    ('NVDA',  '2.4932', '156.265041'),
    ('PPFD',  '0.5759',  '63.795798'),
    ('QDVE',  '9.9477',  '35.183007'),
    ('SILV',  '4.8716',  '47.212415'),
    ('SPYY',  '2.1875', '249.654857'),
]
buggy_total   = sum(Decimal(c) for _,_,c in positions)            # 1,363.83
correct_total = sum(Decimal(s)*Decimal(c) for _,s,c in positions) # 2,693.16 ✓ Snowball

# SPYY weight:
buggy   = Decimal('249.654857')                / buggy_total   # 18.3%
correct = Decimal('2.1875') * Decimal('249.654857') / correct_total  # 20.3%
```
