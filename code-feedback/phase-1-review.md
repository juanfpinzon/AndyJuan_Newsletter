# Phase 1 Review — Portfolio + Configs + Importer

**Reviewer:** Lead Planner/Reviewer (Claude Opus 4.7, xhigh)
**Date:** 2026-04-25
**Branch:** `phase1` (base: `main`)
**Scope:** Tasks 1.1 – 1.5 from `docs/tasks.md`
**Verdict:** **Approve with required changes** — implementation is solid and all tests/verify commands pass, but two issues must be addressed before Phase 2 (one critical, one important). A handful of nits/suggestions are optional.

---

## Summary

Codex delivered Phase 1 cleanly. All five tasks meet their literal acceptance criteria, all 24 tests pass, ruff is clean, and every spec verify command exits 0. The portfolio total cost basis matches the Snowball screenshot to **€0.0000** (exact). Code quality is high: dataclasses are frozen, money is `Decimal`, errors are typed, validation is at the boundary, and the diff is sized appropriately (~720 LOC across 13 files).

Two findings need attention before Phase 1 is signed off:

1. **Critical — D6 validation will fail on a real Snowball export.** The importer expects a *holdings snapshot* schema (`Ticker, Shares, Average cost, Currency`), but the actual Snowball export at `Snowball-extracts/Snowball_Export_Andrea-Juan_25_04_2026.csv` is *transactional* (`Event, Date, Symbol, Price, Quantity, …`). D6's whole point — "validate the importer by re-importing a real Snowball CSV" — cannot be performed as built.
2. **Important — `Snowball-extracts/` is untracked but present in working tree** and contains real broker fills. It should be added to `.gitignore` before any commit, or risk leaking personal trading data.

Everything else below is sized as nit/optional — the build is releasable to Phase 2 once 1 + 2 are resolved.

---

## Verification Story

| Check | Command | Result |
|---|---|---|
| Full test suite | `pytest tests/ -v` | **24 passed** in 1.15s |
| Lint | `ruff check src tests scripts` | **All checks passed** |
| Task 1.2 verify | `python -c "import yaml; [yaml.safe_load(open(f)) for f in [...]]"` | OK |
| Task 1.3 verify | `python -c "...print(len(load_portfolio(Path('config/portfolio.yaml'))))"` | `10` |
| Task 1.4 verify | `python -c "...assert all(len(d[k]['top_10']) == 10 for k in d)"` | OK |
| Cost basis tie-out | `Σ(shares × cost_basis_eur)` vs €2,693.16 | **diff = €0.0000** |
| ETF coverage | every ETF in portfolio has top_10 fallback | OK (8/8) |
| Theme coverage | every portfolio ticker has `primary_theme` | OK (10/10) |

---

## Findings by Task

### Task 1.1 — Position dataclass + loader  ✅

`src/portfolio/models.py` (20 LOC) and `src/portfolio/loader.py` (139 LOC) meet all acceptance criteria.

- `Position` is `@dataclass(frozen=True)`, money fields are `Decimal`, `AssetType` is `Literal["stock","etf","crypto"]`. ✅
- Loader returns `list[Position]`, raises `PortfolioLoadError` with a clear message on missing fields, invalid decimals, unsupported asset types, and non-positive amounts. ✅
- Tests cover happy path, missing-field, invalid-decimal, and `FrozenInstanceError`. ✅

**Nit (optional):** `_coerce_decimal` rejects `<= 0`. This is conservative and correct for shares/cost_basis today, but blocks a future "closed position" row (0 shares). Not in scope to fix now — flagging for awareness when the importer feeds in real exports.

**Nit (optional):** loader silently drops unknown keys (e.g., the `name` field present on every entry in `config/portfolio.yaml`). That's fine for forward-compat; just don't expect strict-schema enforcement here.

---

### Task 1.2 — Initial config files  ✅

`config/settings.yaml`, `recipients.yaml`, `themes.yaml`, `macro_feeds.yaml` all load cleanly and meet criteria.

- All 6 themes present: Defense, AI/Semis, Precious Metals, EU Banks, US Megacaps, Macro/FX. ✅
- Every portfolio entity has a `primary_theme`. ✅ (Test `test_repository_theme_assignments_cover_seed_positions` enforces this.)
- `themes.yaml` also seeds macro entities (ECB, FED, EURUSD, DXY) under Macro/FX — nice forward-looking touch for the Phase 2c entity matcher.
- `settings.yaml` adds 5 new keys beyond what was needed for Task 1.2 (`theme_item_cap`, send-time keys, `ai_commentary_enabled`). They're not yet wired into `src/config.py`'s `Settings` dataclass — that's fine because they'll be consumed in later phases, but **be aware** the next agent touching `config.py` will need to add fields for them or `load_settings()` will continue to ignore them silently.

**Critical:** `config/recipients.yaml` contains Andrea's email as `andrea.placeholder@example.com`. This matches the spec's "Open Question — Andrea's email address (placeholder until provided)" — leave as-is, but the ship checklist for Phase 6 must catch this.

**Nit:** `macro_feeds.yaml` lists `https://feeds.reuters.com/reuters/businessNews`. Reuters discontinued public RSS feeds a while ago and most of those URLs return 404 / empty. Worth a live-fetch sanity check during Phase 2c rather than discovering it at runtime.

---

### Task 1.3 — `config/portfolio.yaml`  ✅ (with one spec deviation worth noting)

10 positions, total cost basis €2,693.1600 vs Snowball target €2,693.16 — exact match to the cent.

**Deviations from the literal task description (acceptable, but documenting):**

- Task spec lists `IUIT, SIL`. Implementation uses `QDVE, SILV`. These are the same funds (QDVE is the EUR-listing of IUIT; SILV is the same Global X Silver Miners as SIL). `themes.yaml` correctly registers IUIT and SIL as `aliases`. ✅
- Task spec describes `EGLN` as "Silver" but EGLN ISIN `IE00B4ND3602` is actually iShares Physical **Gold** ETC. The task itself acknowledged this with "PPFD (or actual silver ETC)", and PPFD ISIN `IE00B4NCWG09` is iShares Physical Silver ETC. So the assignment of metals across positions is correct — the spec's parenthetical was just wrong. Worth a one-line correction in `docs/tasks.md` so future readers don't get confused.

**Critical:** Verify the `name` field per position is informational only and not consumed elsewhere — the loader drops it. If anything downstream is going to grep against display names, surface that need now.

---

### Task 1.4 — `config/etf_holdings.yaml`  ✅ (with two pragmatic compromises)

All 8 ETFs have exactly 10 entries; all tickers non-empty.

**Compromise 1 — SPYY weight sum is 23.62%, not >30%.**

The spec acceptance criterion ("Weights for each ETF sum to a value > 30%") is a sanity check that doesn't hold for broad market funds. SPYY (SPDR MSCI ACWI) genuinely has a top-10 concentration of ~23.6%. The implementer:
- Documented the deviation with a `note:` field in the yaml ("The actual ACWI fund is less concentrated than the Phase 1 >30% heuristic; the live top_10 is about 23.6%.")
- Relaxed the per-ETF test to `>20%` for SPYY only (`tests/test_portfolio.py:159`).

**This is the right engineering call** (faking weights would defeat the lookthrough fallback's purpose), but it deviates from the literal spec. Recommend updating `docs/tasks.md:166` to read something like *"Weights for narrow ETFs sum > 30%; broad-index ETFs may be lower — document in yaml `note`."*

**Compromise 2 — EGLN/PPFD use 10 × 10% synthetic rows of `GOLD` / `SILVER`.**

Physical-metal ETCs don't have 10 underlying issuers — they hold bars. The implementer preserved the schema by repeating `{ticker: GOLD, weight: 10.0}` ten times (and same for SILVER). A `note:` documents it.

**Phase 2 implication:** the lookthrough resolver and exposure resolver will need to special-case "physical commodity" entries, or the composite-exposure map will show weird `path: etf:EGLN, weight: 100% to GOLD` rows. Better to surface this now than discover it in Phase 2a.5. Recommend either (a) leaving GOLD/SILVER as a single-row 100% entry (changing the schema slightly) or (b) tagging the entry with `asset_type: physical_metal` so the resolver can collapse it. Worth a one-line ADR.

**Optional:** Several `aliases:` entries (e.g., `DFEN -> [DFNS]`, `QDVE -> [IUIT]`, `SILV -> [SIL]`) duplicate what's in `themes.yaml`'s `aliases:` lists. Consider one canonical home for ticker aliases in Phase 2 to avoid drift.

---

### Task 1.5 — Snowball CSV importer  ⚠️

`scripts/import_snowball.py` (254 LOC) and `tests/test_import_snowball.py` (146 LOC).

**All four acceptance criteria pass against the bundled fixture.** Tests cover:
- `--dry-run` prints diff to stdout, doesn't write
- Existing tickers preserve `theme`/`issuer`/`isin`/`asset_type` enrichment ✅
- New tickers scaffolded with `asset_type: stock`, warning logged to stderr ✅
- Missing column header → `SnowballSchemaError` ✅
- Currency mismatch → `SnowballImportError` ✅

**Critical (must fix before Phase 2): the importer cannot read a real Snowball export.**

The fixture at `tests/fixtures/snowball-export.csv` uses headers `Ticker, Shares, Average cost, Currency` — a **holdings snapshot** format. The actual Snowball export at `Snowball-extracts/Snowball_Export_Andrea-Juan_25_04_2026.csv` uses headers `Event, Date, Symbol, Price, Quantity, Currency, FeeTax, Exchange, …` — a **transactional** format with 138 BUY/CASH_IN/etc. rows that need to be aggregated before they look like a holdings snapshot.

D6 in `docs/plan.md` says: *"The CSV importer is then validated by re-running it against a Snowball export and asserting the result matches the manual file."* That validation step **cannot be performed as built**. The Phase 1 checkpoint in `docs/tasks.md:188` says *"Importer round-trips a real Snowball CSV without losing enrichment fields"* — same problem.

Three resolution paths, in order of preference:

1. **Confirm Snowball has a holdings-export mode** and re-export to that format. If yes, swap `Snowball-extracts/...csv` and call D6 done.
2. **Add a transaction → holdings aggregator** to the importer (group by Symbol, sum signed Quantity, weighted-average price → cost_basis_per_share). Roughly 30–60 LOC; needs care on currency handling and on the "balance adjustment" rows (which carry "Automatically generated" notes and should probably be ignored).
3. **Defer to Phase 2** by explicitly marking D6's validation as N/A for v0.1 — but that means the importer is shipping untested against the actual data shape it's supposed to consume, which is risky.

Whichever path: please update `docs/tasks.md` Phase 1 checkpoint and `docs/plan.md` D6 to reflect the resolved state.

**Important: `Snowball-extracts/` should be `.gitignore`d.**

The directory is untracked today, so nothing has leaked yet — but the file contains real broker fills (real prices, real share counts, real timestamps, real exchange codes). `git add .` would commit it. Add `Snowball-extracts/` to `.gitignore` *before* the next commit.

**Nit (optional):** `import_snowball()` reads the portfolio path from a module-level global `DEFAULT_PORTFOLIO_PATH`, and tests monkey-patch that global (`module.DEFAULT_PORTFOLIO_PATH = portfolio_path`). Cleaner: accept `portfolio_path: Path | None = None` as a parameter, default to the global. Two-line change, makes the function pure and the tests stop reaching into internals.

**Nit (optional):** The output flow at lines 52–58 has a slight tangle (one `if/elif`, then a separate `if not args.dry_run and not diff_text`). The four cases collapse to:
```python
print(diff_text or "No changes.", end="")
```
Same behavior, six fewer lines.

**Nit (optional):** `_normalize_decimal` rejects 0 — same flag as Task 1.1. A real Snowball holdings export *might* include zeroed-out positions; worth confirming behavior before that's a Phase 2 surprise.

**Nit (optional):** `_normalize_string` upper-cases everything (currency + ticker). Correct for these fields, but the function name doesn't telegraph that side effect. A minor rename to `_normalize_uppercase_string` (or split into two helpers) would be friendlier. Not blocking.

---

## Five-Axis Summary

| Axis | Verdict | Notes |
|---|---|---|
| **Correctness** | ✅ All tests + verify commands pass; portfolio totals tie to the cent. ⚠️ Importer untested against real Snowball schema. |
| **Readability** | ✅ Clear names, typed coercion helpers, no clever tricks. Two minor simplifications possible. |
| **Architecture** | ✅ Loader/models split clean, validation at the boundary, typed exceptions. Module-level `DEFAULT_PORTFOLIO_PATH` mutation in tests is the only smell. |
| **Security** | ⚠️ `Snowball-extracts/` must be gitignored before any commit. Otherwise no input-validation gaps. |
| **Performance** | ✅ N/A — file-load + dict-merge, all O(n). |

---

## Required Before Merging Phase 1

1. **Add `Snowball-extracts/` to `.gitignore`.** (1 line)
2. **Resolve the real-Snowball-CSV mismatch** — pick one of the three paths above and update `docs/tasks.md:188` + `docs/plan.md` D6 to match. If you adopt option 2 (transaction aggregator), add a test using the real CSV (with the file gitignored, paste a small redacted snippet into `tests/fixtures/snowball-transactions.csv`).

## Recommended (not blocking)

3. Update `docs/tasks.md:152` to reflect the actual ticker set (`QDVE, SILV` not `IUIT, SIL`) and fix the `EGLN (Silver)` → `EGLN (Gold) / PPFD (Silver)` mislabel.
4. Update `docs/tasks.md:166` to allow broad-index ETFs to fall below the 30% sum heuristic (with a documented `note`).
5. Wire the 5 new keys in `settings.yaml` (`theme_item_cap`, `daily_send_time_cet`, `deep_brief_send_time_cet`, `deep_brief_day`, `ai_commentary_enabled`) into `Settings` so `load_settings()` doesn't ignore them. Optional now, mandatory before they're consumed.
6. Add a one-line ADR (`docs/adr/0002-physical-metal-lookthrough.md`) documenting the GOLD/SILVER × 10 convention so the Phase 2 lookthrough resolver author knows to special-case it.

## Optional / Nits

7. Simplify `import_snowball.main` print logic (line ~52–58) to `print(diff_text or "No changes.", end="")`.
8. Pass `portfolio_path` as a parameter to `import_snowball()` rather than mutating the module global from tests.
9. Confirm `https://feeds.reuters.com/reuters/businessNews` still serves content (likely 404).
10. Decide canonical home for ticker aliases (`themes.yaml` vs `etf_holdings.yaml`) before Phase 2c.

---

## Sign-off

Once items 1 and 2 land, Phase 1 is approved. The build is otherwise in good shape — Codex executed the spec faithfully, the tests are well-scoped, and the deviations are honestly documented in the yaml notes. Recommend a single commit for the Phase 1 work plus a separate small commit for the gitignore + Snowball-CSV fix so the history reads cleanly.

— Reviewer
