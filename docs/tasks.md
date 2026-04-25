# Tasks: AndyJuan Personal Portfolio Radar — v0.1

> Phase 3 of spec-driven-development. Companion to `docs/spec.md` and `docs/plan.md`.
> The spec is **what + done**. The plan is **how + in what order**. This is **what to do, in single-session chunks**.
> Status: approved.

## Overview

41 tasks across 8 phases. Each task is sized S (1–2 files) or M (3–5 files), has explicit
acceptance criteria, a verification command, named dependencies, and a file list. Workflow
assumes Codex (or another implementing agent) picks tasks in order, and the planner/reviewer
verifies each task before marking it complete.

**Sizing legend:**
- **S** — 1–2 files, single focused session, < 1h
- **M** — 3–5 files, single session, ~1–2h

**Status legend:**
- `[ ]` not started · `[~]` in progress · `[x]` done + verified

---

## Architecture Decisions (recap from plan)

- **D1** yfinance for v0.1 pricing (free, no key, covers UCITS + US + crypto + FX)
- **D2** EUR is reporting base currency
- **D3** Cost tracking in USD (OpenRouter bills in USD)
- **D4** Theme tiebreaker: `primary_theme` per entity in `themes.yaml`; "Affects" badges surface secondary themes inline
- **D5** LLM test fixtures captured via one-time spike day (Phase 3)
- **D6** Initial `portfolio.yaml` is seeded from the Snowball snapshot; importer is validated against a real Snowball transaction export
- **D7** CI runs pytest only; no live API calls

---

## Phase 0 — Foundation

Sequential. All Phase 1+ work depends on Phase 0 completing.

#### Task 0.1: Repo scaffolding + package skeleton [x]
**Description:** Create the project skeleton: `pyproject.toml` with all v0.1 deps, `.env.example`, `.gitignore`, `README.md`, `CLAUDE.md`, byte-for-byte-identical `AGENTS.md`, and empty `src/` package with all subdirectory `__init__.py` files. Also create `tests/conftest.py` and an empty `tests/fixtures/` tree.
**Acceptance:**
- [x] `pip install -e ".[dev]"` succeeds on a clean Python 3.11+ venv
- [x] `python -c "import src; from src import portfolio, lookthrough, exposure, pnl, fetcher, entity_match, analyzer, renderer, sender, storage, pipeline, utils"` exits 0
- [x] `diff CLAUDE.md AGENTS.md` produces no output
**Verify:** `pip install -e ".[dev]" && python -c "import src" && diff CLAUDE.md AGENTS.md && pytest tests/ -v`
**Dependencies:** None
**Files:** `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`, `CLAUDE.md`, `AGENTS.md`, `src/__init__.py`, all `src/*/__init__.py`, `tests/conftest.py`
**Scope:** M

#### Task 0.2: Logging utility (`src/utils/log.py`) [x]
**Description:** Configure structlog to emit JSONL to `data/logs/andyjuan.jsonl` and stdout in dev. Expose `get_logger(name=None)` that returns a configured `BoundLogger`.
**Acceptance:**
- [x] `from src.utils.log import get_logger; log = get_logger()` works
- [x] `log.info("test_event", foo="bar")` writes a JSONL line with `event`, `foo`, `timestamp`, `level`
- [x] Log file path is configurable via env var `LOG_FILE`
**Verify:** `pytest tests/test_log.py -v`
**Dependencies:** Task 0.1
**Files:** `src/utils/log.py`, `tests/test_log.py`
**Scope:** S

#### Task 0.3: HTTP utility (`src/utils/http.py`) [x]
**Description:** Provide a shared `httpx.AsyncClient` factory with HTTP/2, timeouts, and retry on 5xx + 429 (3 attempts, exponential backoff).
**Acceptance:**
- [x] `from src.utils.http import get_async_client` returns a configured `httpx.AsyncClient`
- [x] Retries 3 times on 503; gives up cleanly on 4xx (except 429)
- [x] Tested with respx mocking
**Verify:** `pytest tests/test_http.py -v`
**Dependencies:** Task 0.1
**Files:** `src/utils/http.py`, `tests/test_http.py`
**Scope:** S

#### Task 0.4: LLM utility (`src/utils/llm.py`) — OpenRouter wrapper [x]
**Description:** Wrap the `openai` SDK pointed at OpenRouter's base URL. Expose `call_openrouter(prompt, model, max_tokens, fallback_model=None) -> LLMResponse`. Track tokens + cost in USD per call. Fall back to `fallback_model` on first-call failure.
**Acceptance:**
- [x] `LLMResponse` dataclass exposes `content`, `model`, `tokens_in`, `tokens_out`, `cost_usd`
- [x] Falls back to `fallback_model` when primary raises
- [x] Per-call data is also written to the SQLite `llm_calls` table (created in Task 0.6)
- [x] Tested with mocked openai client
**Verify:** `pytest tests/test_llm.py -v`
**Dependencies:** Task 0.1, 0.6 (for `llm_calls` table)
**Files:** `src/utils/llm.py`, `tests/test_llm.py`
**Scope:** M

#### Task 0.5: Config loader (`src/config.py`) [x]
**Description:** Load `config/settings.yaml`, allow env-var overrides per key. Return a frozen `Settings` dataclass typed against the keys we use.
**Acceptance:**
- [x] `from src.config import load_settings; s = load_settings()` returns a frozen dataclass
- [x] env var override works (e.g., `LLM_SCORING_MODEL=foo` overrides yaml value)
- [x] Missing required keys raise a clear `ConfigError`
**Verify:** `pytest tests/test_config.py -v`
**Dependencies:** Task 0.1, 1.2 (settings.yaml exists)
**Files:** `src/config.py`, `tests/test_config.py`
**Scope:** S

#### Task 0.6: SQLite storage scaffolding (`src/storage/`) [x]
**Description:** Define schemas for `runs`, `articles_seen`, `exposure_snapshots`, `llm_calls`. Provide `init_db(path) -> Database` that creates tables idempotently.
**Acceptance:**
- [x] `from src.storage.db import init_db; db = init_db(":memory:")` creates all 4 tables
- [x] Tables are idempotent (calling `init_db` twice doesn't error or duplicate)
- [x] Tested
**Verify:** `pytest tests/test_db.py -v`
**Dependencies:** Task 0.1
**Files:** `src/storage/db.py`, `src/storage/schemas.py`, `tests/test_db.py`
**Scope:** S

#### Task 0.7: GitHub Actions workflow + CI skeleton [x]
**Description:** Create `.github/workflows/daily-radar.yml` with `workflow_dispatch` + `repository_dispatch` triggers (job body is stub for now). Create `.github/workflows/ci.yml` that runs `ruff check` + `pytest` on PRs.
**Acceptance:**
- [x] CI workflow runs on PR open/sync against main
- [x] daily-radar workflow accepts `mode` and `dry_run` inputs (defaults: daily, false)
- [x] Both workflows are syntactically valid (verify locally with `actionlint` or by pushing a draft PR)
**Verify:** Push a draft PR; CI runs and passes; manually trigger daily-radar with `dry_run=true` (job currently stubs out)
**Dependencies:** Task 0.1
**Files:** `.github/workflows/daily-radar.yml`, `.github/workflows/ci.yml`
**Scope:** S

### Checkpoint: Phase 0 complete [x]
- [x] All Phase 0 tasks pass their verification commands
- [x] `pytest tests/ -v` shows passing tests for all utility modules
- [x] CI workflow on a draft PR passes
- [x] Reviewer signs off before Phase 1

---

## Phase 1 — Portfolio + Configs + Importer

Sequential within phase; gates Phase 2.

#### Task 1.1: `Position` dataclass + `portfolio.yaml` loader
**Description:** Define `Position` (frozen dataclass, Decimal money fields) and `load_portfolio(path) -> list[Position]`. Validate required fields.
**Acceptance:**
- [x] `Position` has: `ticker`, `isin`, `asset_type`, `issuer`, `shares (Decimal)`, `cost_basis_eur (Decimal)`, `currency`
- [x] `load_portfolio(Path("tests/fixtures/portfolio.yaml"))` returns `list[Position]`
- [x] Loader raises `PortfolioLoadError` on schema violations with a clear message
**Verify:** `pytest tests/test_portfolio.py -v`
**Dependencies:** Task 0.1
**Files:** `src/portfolio/models.py`, `src/portfolio/loader.py`, `tests/test_portfolio.py`, `tests/fixtures/portfolio.yaml`
**Scope:** M

#### Task 1.2: Initial config files (settings, recipients, themes, macro_feeds)
**Description:** Create `config/settings.yaml` (initial thresholds + model assignments + cadence flags), `config/recipients.yaml` (juan + andrea placeholder), `config/themes.yaml` (6 themes + entity → theme mapping with `primary_theme`), `config/macro_feeds.yaml` (ECB, Fed, FT macro, Reuters macro RSS URLs).
**Acceptance:**
- [x] All 4 yaml files load via `yaml.safe_load` with no errors
- [x] `themes.yaml` covers Defense, AI/Semis, Precious Metals, EU Banks, US Megacaps, Macro/FX
- [x] Every entity in the seed `portfolio.yaml` has a `primary_theme` assignment in `themes.yaml`
**Verify:** `python -c "import yaml; [yaml.safe_load(open(f)) for f in ['config/settings.yaml','config/recipients.yaml','config/themes.yaml','config/macro_feeds.yaml']]"` exits 0
**Dependencies:** Task 0.1
**Files:** `config/settings.yaml`, `config/recipients.yaml`, `config/themes.yaml`, `config/macro_feeds.yaml`
**Scope:** S

#### Task 1.3: Initial `config/portfolio.yaml` from Snowball snapshot
**Description:** Seed the 10 positions from the Snowball snapshot: BNKE, DFEN, EGLN (Gold), GDX, GOOGL, NVDA, PPFD (Silver), QDVE, SILV, SPYY. Include ticker, ISIN (lookup as needed), asset_type, issuer, shares, cost_basis_eur, currency.
**Acceptance:**
- [x] `load_portfolio()` on this file returns exactly 10 positions
- [x] Sum of `shares × cost_basis_per_share` matches Snowball total cost basis (€2,693.16) within €0.01
- [x] All ETF positions have non-null `issuer`
**Verify:** `python -c "from src.portfolio.loader import load_portfolio; from pathlib import Path; print(len(load_portfolio(Path('config/portfolio.yaml'))))"` prints `10`
**Dependencies:** Task 1.1
**Files:** `config/portfolio.yaml`
**Scope:** S

#### Task 1.4: `config/etf_holdings.yaml` (manual top-10 fallback per ETF)
**Description:** For each of the 8 ETFs in `portfolio.yaml`, hand-build a `top_10` list of `{ticker, isin, weight}` entries from the issuer's latest fact sheet. This is the fallback used when the scraper for that issuer fails.
**Acceptance:**
- [x] Each of 8 ETFs has exactly 10 holdings entries
- [x] Weights for each ETF sum to a sane concentration level; narrow ETFs should generally exceed 30%, broad-index ETFs may be lower if documented in a `note`
- [x] All ticker fields are non-empty
**Verify:** `python -c "import yaml; d = yaml.safe_load(open('config/etf_holdings.yaml')); assert all(len(d[k]['top_10']) == 10 for k in d), [k for k in d if len(d[k]['top_10']) != 10]"` exits 0
**Dependencies:** Task 1.3
**Files:** `config/etf_holdings.yaml`
**Scope:** M

#### Task 1.5: Snowball CSV importer (`scripts/import_snowball.py`)
**Description:** Read either a Snowball holdings snapshot CSV or Snowball's transaction export, merge into `config/portfolio.yaml`, and aggregate transactions into current holdings when needed. Preserve enrichment on existing tickers; scaffold new tickers with `asset_type: stock` defaulted; warn (don't auto-remove) on tickers missing from the CSV; fail loudly on column-header schema drift or currency mismatch in holdings snapshots. Support `--dry-run` for diff preview.
**Acceptance:**
- [x] `python scripts/import_snowball.py tests/fixtures/snowball-export.csv --dry-run` shows diff without writing
- [x] `python scripts/import_snowball.py tests/fixtures/snowball-transactions.csv --dry-run` aggregates transactions into current holdings without writing
- [x] Existing tickers preserve `asset_type`, `issuer`, `isin`, `theme`, etc.
- [x] New tickers are scaffolded with `asset_type: stock` and a logged warning
- [x] Missing column headers raise a clear `SnowballSchemaError`
**Verify:** `pytest tests/test_import_snowball.py -v`
**Dependencies:** Task 1.1, 1.3
**Files:** `scripts/import_snowball.py`, `tests/test_import_snowball.py`, `tests/fixtures/snowball-export.csv`, `tests/fixtures/snowball-transactions.csv`
**Scope:** M

### Checkpoint: Phase 1 complete
- [x] All config files load cleanly
- [x] Portfolio loader passes all tests
- [x] Importer round-trips a real Snowball transaction export without losing enrichment fields
- [x] Reviewer signs off before Phase 2

---

## Phase 2a — Look-through + Exposure Resolver *(critical path)*

Sequential within phase. Phases 2b and 2c can run in parallel with 2a if implementer capacity allows.

#### Task 2a.1: `Holding` model + adapter base interface
**Description:** Define `Holding(ticker, isin, weight)` dataclass and `BaseAdapter` abstract class with `async fetch(etf_id) -> list[Holding]`.
**Acceptance:**
- [x] `BaseAdapter` is abstract; raises `NotImplementedError` if subclass forgets `fetch`
- [x] `Holding` is frozen, Decimal weight
**Verify:** `pytest tests/test_lookthrough_base.py -v`
**Dependencies:** Phase 0 done
**Files:** `src/lookthrough/models.py`, `src/lookthrough/adapters/base.py`, `tests/test_lookthrough_base.py`
**Scope:** S

#### Task 2a.2: iShares adapter
**Description:** Build an iShares fund-page adapter that fetches top-10 holdings (typically via their JSON API or downloadable CSV). Use respx for tests.
**Acceptance:**
- [x] Returns top-10 `Holding` objects for IUIT (iShares S&P 500 Information Technology) and EGLN (iShares Physical Silver) test cases
- [x] Handles HTTP errors → raises `LookthroughFailure(issuer="ishares", etf_id=...)`
- [x] Tested with canned fixture
**Verify:** `pytest tests/test_lookthrough_ishares.py -v`
**Dependencies:** Task 2a.1
**Files:** `src/lookthrough/adapters/ishares.py`, `tests/test_lookthrough_ishares.py`, `tests/fixtures/etf_holdings/ishares/*.json`
**Scope:** M

#### Task 2a.3: VanEck + SSgA + Global X adapters (CSV-based)
**Description:** These three issuers commonly ship CSV holdings. Build adapters with shared CSV-parsing helper if it cuts code.
**Acceptance:**
- [x] Each of the 3 adapters returns top-10 for at least one ETF in our portfolio (DFEN, GDX, SPYY, SIL)
- [x] Each adapter handles HTTP errors with `LookthroughFailure(issuer=...)`
- [x] Tested with canned CSV fixtures
**Verify:** `pytest tests/test_lookthrough_vaneck.py tests/test_lookthrough_ssga.py tests/test_lookthrough_globalx.py -v`
**Dependencies:** Task 2a.1
**Files:** `src/lookthrough/adapters/{vaneck,ssga,globalx}.py`, 3 corresponding test files, 3 fixture CSVs
**Scope:** M

#### Task 2a.4: Lyxor (Amundi) adapter — degraded mode acceptable
**Description:** Lyxor (Amundi) pages are known to be hard to crawl. Attempt a clean adapter; if it proves uncrawlable, document the failure mode and let the resolver fall back to `etf_holdings.yaml`. The adapter must still raise a typed exception so the resolver knows to fall back.
**Acceptance:**
- [x] Adapter exists and follows `BaseAdapter` interface
- [x] If unable to scrape, raises `LookthroughFailure(issuer="lyxor")` cleanly
- [x] If scraping works for BNKE, returns top-10
- [x] Decision documented in `docs/adr/0001-lyxor-lookthrough.md`
**Verify:** `pytest tests/test_lookthrough_lyxor.py -v`
**Dependencies:** Task 2a.1
**Files:** `src/lookthrough/adapters/lyxor.py`, `tests/test_lookthrough_lyxor.py`, `docs/adr/0001-lyxor-lookthrough.md`
**Scope:** M

#### Task 2a.5: Lookthrough resolver (orchestrator with yaml fallback)
**Description:** `resolve_lookthrough(portfolio) -> dict[etf_ticker, list[Holding]]` — for each ETF, try the issuer's adapter; if it raises `LookthroughFailure`, fall back to `config/etf_holdings.yaml` and log `lookthrough_fallback_used` with issuer name.
**Acceptance:**
- [x] Returns successful scrape data when adapter succeeds
- [x] Falls back to yaml on `LookthroughFailure`
- [x] Logs `lookthrough_fallback_used` event with `issuer` field
- [x] If both scraper and yaml are unavailable, raises `LookthroughExhausted`
**Verify:** `pytest tests/test_lookthrough_resolver.py -v`
**Dependencies:** Task 2a.2, 2a.3, 2a.4, Task 1.4 (etf_holdings.yaml)
**Files:** `src/lookthrough/resolver.py`, `tests/test_lookthrough_resolver.py`
**Scope:** M

#### Task 2a.6: Refresh ETF holdings script (`scripts/refresh_etf_holdings.py`)
**Description:** Run all adapters once, cache successful results in SQLite (`exposure_snapshots` or new `etf_holdings_cache` table), print per-issuer success/failure summary.
**Acceptance:**
- [x] Runs all 5 adapters, prints summary table
- [x] Caches successful results into SQLite with timestamp
- [x] Returns nonzero exit code if all 5 issuers fail (sanity guardrail)
**Verify:** `python scripts/refresh_etf_holdings.py` runs and prints summary
**Dependencies:** Task 2a.5
**Files:** `scripts/refresh_etf_holdings.py`
**Scope:** S

#### Task 2a.7: `ExposureEntry` model + composite exposure resolver
**Description:** Define `ExposureEntry(entity, composite_weight, paths)`. Implement `compute_exposure(positions, lookthrough_data) -> dict[entity, ExposureEntry]`. Each `path` records `{source: 'direct' | 'etf:<ticker>', weight}` so the renderer can show the full attribution.
**Acceptance:**
- [x] For NVDA test scenario (10% direct + 30% of an ETF that's 10% of book), composite weight matches hand-calc
- [x] Result is reproducible (same input → same output)
- [x] **100% test coverage on `src/exposure/`**
**Verify:** `pytest tests/test_exposure.py -v --cov=src/exposure --cov-report=term-missing` shows 100%
**Dependencies:** Task 2a.5, Task 1.1
**Files:** `src/exposure/models.py`, `src/exposure/resolver.py`, `tests/test_exposure.py`
**Scope:** M

#### Task 2a.8: Debug exposure script (`scripts/debug_exposure.py`)
**Description:** Pretty-print the composite exposure map: entity, composite weight, paths. Support `--costs` flag to print the LLM cost summary from the SQLite `llm_calls` table.
**Acceptance:**
- [x] Default mode prints exposure map sorted by composite weight desc
- [x] `--costs` flag prints recent run costs in USD and EUR (via FX from yfinance)
**Verify:** `python scripts/debug_exposure.py` prints something readable
**Dependencies:** Task 2a.7
**Files:** `scripts/debug_exposure.py`
**Scope:** S

### Checkpoint: Phase 2a complete
- [x] All adapters either work or fall back cleanly
- [x] Coverage on `src/exposure/` = 100%
- [x] `python scripts/debug_exposure.py` shows a sane map
- [x] Reviewer signs off before Phase 3

---

## Phase 2b — Pricing + P&L *(parallelizable with 2a)*

#### Task 2b.1: yfinance pricing client (`src/pricing/yfinance_client.py`)
**Description:** Wrap yfinance: `fetch_prices(tickers, base_currency='EUR') -> dict[ticker, PriceSnapshot]`. Handle weekend/holiday fallback to last trading day. Convert all prices to EUR via FX (e.g., `EURUSD=X`).
**Acceptance:**
- [x] Returns `PriceSnapshot(ticker, last, previous_close, currency_native, last_eur, change_pct)`
- [x] Weekend run uses Friday close as "today"
- [x] FX conversion is single-pass (don't fetch USD price then EUR FX twice for the same call batch)
- [x] Tested with canned yfinance JSON fixtures
**Verify:** `pytest tests/test_pricing.py -v`
**Dependencies:** Task 0.3
**Files:** `src/pricing/yfinance_client.py`, `src/pricing/__init__.py`, `tests/test_pricing.py`, `tests/fixtures/yfinance/*.json`
**Scope:** M

#### Task 2b.2: P&L calculator (`src/pnl/`)
**Description:** Define `PnLSnapshot` and `DailyDelta` dataclasses. Implement `compute_pnl(positions, prices) -> dict[ticker, PnLSnapshot]` and `compute_total(snapshots) -> TotalPnL`.
**Acceptance:**
- [x] P&L per position matches Snowball screenshot within €0.01
- [x] Total P&L matches Snowball total profit (~€69.66 in screenshot)
- [x] **100% test coverage on `src/pnl/`**
**Verify:** `pytest tests/test_pnl.py -v --cov=src/pnl --cov-report=term-missing` shows 100%
**Dependencies:** Task 2b.1, Task 1.1
**Files:** `src/pnl/models.py`, `src/pnl/calculator.py`, `tests/test_pnl.py`
**Scope:** M

### Checkpoint: Phase 2b complete
- [x] yfinance live spike returns prices for sample tickers
- [x] P&L numbers tie to Snowball screenshot
- [x] Coverage 100% on `src/pnl/`

---

## Phase 2c — News Fetch + Entity Matching *(parallelizable with 2a/2b)*

#### Task 2c.1: NewsData.io client (`src/fetcher/newsdata.py`)
**Description:** Wrap NewsData.io API: paginated fetch over a 24-hour window, dedup against `articles_seen` SQLite table, retry on 429 with backoff, return structured `Article(title, body, url, source, published_at, raw_tags)`.
**Acceptance:**
- [x] `fetch_news(entity_query, hours=24) -> list[Article]` returns deduped articles
- [x] Persists seen URLs into `articles_seen` for future dedup
- [x] Retries once on 429 (NewsData free tier rate-limits aggressively)
- [x] Tested with respx mocking
**Verify:** `pytest tests/test_fetcher_newsdata.py -v`
**Dependencies:** Task 0.3, 0.6
**Files:** `src/fetcher/newsdata.py`, `tests/test_fetcher_newsdata.py`, `tests/fixtures/news/newsdata/*.json`
**Scope:** M

#### Task 2c.2: Macro RSS reader (`src/fetcher/macro_rss.py`)
**Description:** Read RSS feeds from `config/macro_feeds.yaml` using feedparser. ETag-aware so we don't re-fetch unchanged feeds within a day.
**Acceptance:**
- [x] `fetch_macro() -> list[Article]` returns last-24h items from configured feeds
- [x] ETag/Last-Modified honored (validate via fixture)
- [x] Tested
**Verify:** `pytest tests/test_fetcher_macro_rss.py -v`
**Dependencies:** Task 0.3, Task 1.2
**Files:** `src/fetcher/macro_rss.py`, `tests/test_fetcher_macro_rss.py`, `tests/fixtures/news/rss/*.xml`
**Scope:** S

#### Task 2c.3: Entity matcher (`src/entity_match/matcher.py`) — rapidfuzz
**Description:** Given an article (title + body) and the entity universe (from portfolio + lookthrough), return `list[EntityMatch(entity, score, method)]` for entities mentioned. Use rapidfuzz for fuzzy ticker + company-name matching.
**Acceptance:**
- [x] On a 30-article hand-labeled fixture, ≥80% of articles correctly match to the right primary entity
- [x] Both ticker patterns ("$NVDA", "NVDA") and company names ("Nvidia", "NVIDIA Corporation") match
- [x] Score threshold tunable via settings
**Verify:** `pytest tests/test_entity_match.py -v`
**Dependencies:** Task 0.1, 1.1, 1.2
**Files:** `src/entity_match/matcher.py`, `tests/test_entity_match.py`, `tests/fixtures/news/labeled_30.json`
**Scope:** M

### Checkpoint: Phase 2 complete (2a + 2b + 2c)
- [x] Live NewsData.io spike returns articles for at least one of our tickers
- [x] Entity matcher hits ≥80% on labeled fixture
- [x] yfinance P&L matches Snowball
- [x] All exposure-map math verified at 100% coverage
- [x] Reviewer signs off before Phase 3

---

## Phase 3 — Analysis (LLM)

Phase 3 begins with a "spike day" to capture LLM fixtures (per D5).

#### Task 3.0: LLM spike day — capture fixtures
**Description:** With a working Phase 2 pipeline (real NewsData fetch → real exposure map), run real OpenRouter calls for each prompt (ranker, theme flash, synthesis, fact-checker) against a fixed input. Save outputs to `tests/fixtures/llm/`. Document spend in the PR.
**Acceptance:**
- [ ] 4 fixture sets saved: `tests/fixtures/llm/{ranker,theme_flash,synthesis,fact_checker}/`
- [ ] Each fixture set includes the input + output for at least 2 representative scenarios
- [ ] Total spike spend documented
**Verify:** `ls tests/fixtures/llm/` shows 4 directories with content
**Dependencies:** Phase 2 complete
**Files:** `tests/fixtures/llm/**/*` (data files only)
**Scope:** S (research, not code)

#### Task 3.1: Ranker prompt + module (`prompts/news_ranker.md`, `src/analyzer/ranker.py`)
**Description:** Prompt takes candidate articles + exposure map JSON. Output: ranked list (top-15 OR ≥5% composite, whichever is more). Use Haiku for cost.
**Acceptance:**
- [ ] Prompt is in `prompts/news_ranker.md`, parameterized with jinja
- [ ] `rank_news(articles, exposure_map) -> list[RankedArticle]` produces structured output
- [ ] Output respects threshold rule on canned fixture input
- [ ] Tested with fixtures (no live calls)
**Verify:** `pytest tests/test_ranker.py -v`
**Dependencies:** Task 0.4, Task 3.0
**Files:** `prompts/news_ranker.md`, `src/analyzer/ranker.py`, `tests/test_ranker.py`
**Scope:** M

#### Task 3.2: Theme flash prompt + module
**Description:** For each theme group in the rendered email, generate 1–2 sentences. Sonnet model.
**Acceptance:**
- [ ] Output is consistently 1–2 sentences (validate by sentence count regex on fixture output)
- [ ] No novel facts (manual eyeball + fact-checker pass in Task 3.4)
- [ ] Tested with fixtures
**Verify:** `pytest tests/test_theme_flash.py -v`
**Dependencies:** Task 0.4, Task 3.0
**Files:** `prompts/theme_flash.md`, `src/analyzer/theme_flash.py`, `tests/test_theme_flash.py`
**Scope:** S

#### Task 3.3: Synthesis prompt + module
**Description:** Bottom-of-email synthesis: 2–3 paragraphs cross-referencing themes + a final paragraph of suggestions ("Watch X earnings", "EUR/USD move tilts USD ETFs +1.2%"). Sonnet model.
**Acceptance:**
- [ ] Output respects "no novel facts" rule (validated by Task 3.4 fact-checker on fixture output)
- [ ] Final paragraph contains at least one "Watch" or "Note" suggestion
- [ ] Tested
**Verify:** `pytest tests/test_synthesis.py -v`
**Dependencies:** Task 0.4, Task 3.0
**Files:** `prompts/ai_synthesis.md`, `src/analyzer/synthesis.py`, `tests/test_synthesis.py`
**Scope:** M

#### Task 3.4: Fact-checker prompt + module (fail-closed)
**Description:** Post-render Haiku pass. Input: rendered email content + AI Take blocks. Output: `{ok: bool, flagged_claims: list[str]}`. On `ok=false`, the AI Take is omitted from final email and a warning is logged.
**Acceptance:**
- [ ] Blocks AI Take when input contains "NVDA acquired AMD" planted into a Sonnet output (test scenario)
- [ ] Passes when AI Take only synthesizes from facts in the rendered content
- [ ] Warning log includes flagged claims with verbatim text
- [ ] **≥90% test coverage on `src/analyzer/fact_checker.py`**
**Verify:** `pytest tests/test_fact_checker.py -v --cov=src/analyzer/fact_checker --cov-report=term-missing` shows ≥90%
**Dependencies:** Task 0.4, Task 3.0
**Files:** `prompts/fact_checker.md`, `src/analyzer/fact_checker.py`, `tests/test_fact_checker.py`
**Scope:** M

### Checkpoint: Phase 3 complete
- [ ] All 4 LLM fixtures captured and tests pass
- [ ] Fact-checker blocks the planted "NVDA acquired AMD" novel fact
- [ ] Spike-day spend documented
- [ ] Reviewer signs off before Phase 4

---

## Phase 4 — Renderer

Sequential within phase. Phase 4 can begin in parallel with late Phase 3 once data shapes (`RankedArticle`, `ThemeFlash`, `Synthesis`) are stable.

#### Task 4.1: Theme groups + Concentrated Exposures widget (`src/renderer/theme_groups.py`)
**Description:** Group ranked news + position cards by `primary_theme`. Apply 5-item-per-theme cap. Compute the Concentrated Exposures widget rows (entities with composite weight ≥5%).
**Acceptance:**
- [ ] Each theme has ≤5 news items after capping
- [ ] An item with multiple theme tags renders only under its `primary_theme`
- [ ] Concentrated Exposures rows include `entity, composite_weight, path_count`
**Verify:** `pytest tests/test_theme_groups.py -v`
**Dependencies:** Task 2a.7, Task 1.2 (themes.yaml)
**Files:** `src/renderer/theme_groups.py`, `tests/test_theme_groups.py`
**Scope:** M

#### Task 4.2: Daily email template + dark CSS (`templates/daily_email.html.j2`)
**Description:** Build the daily Mon-Fri layout with all 6 sections. Inline CSS (premailer will run later). Dark Binance/IBKR-inspired palette: deep navy/charcoal base (#0b0e11/#1e2329), green gain (#0ecb81), red loss (#f6465d), muted gold AI accent (#f0b90b), high-contrast off-white text (#eaecef). Include AI chip macro.
**Acceptance:**
- [ ] All 6 sections present in correct order
- [ ] AI chip macro reusable across per-theme flashes and bottom synthesis
- [ ] Renders in Gmail web (paste-into-draft visual check)
**Verify:** `python scripts/test_email.py` (after Task 4.5) opens preview that visually reviews
**Dependencies:** Task 4.1
**Files:** `templates/daily_email.html.j2`
**Scope:** M

#### Task 4.3: Saturday deep template (`templates/saturday_deep.html.j2`)
**Description:** Extends `daily_email.html.j2` (jinja inheritance). Adds: longer synthesis section, week-ahead earnings/macro calendar.
**Acceptance:**
- [ ] Inherits from `daily_email.html.j2` cleanly
- [ ] Adds `{% block week_ahead %}` and longer synthesis block
- [ ] Renders without breaking the daily layout
**Verify:** Mock-render a Saturday preview via `python scripts/test_email.py --mode=deep`
**Dependencies:** Task 4.2
**Files:** `templates/saturday_deep.html.j2`
**Scope:** M

#### Task 4.4: Renderer assembly (`src/renderer/render.py`) + tests
**Description:** Compose: load template → render with context → premailer inline CSS → also produce plain-text fallback. Public API: `render_email(context, mode='daily') -> RenderedEmail(html, text, word_count)`.
**Acceptance:**
- [ ] Word count of rendered HTML body text ≤ 1,000 on a representative input
- [ ] Every news item has a non-empty `href`
- [ ] AI chip is present on every AI Take block
- [ ] Plain-text fallback is generated alongside HTML
**Verify:** `pytest tests/test_renderer.py -v`
**Dependencies:** Task 4.2, 4.3
**Files:** `src/renderer/render.py`, `tests/test_renderer.py`
**Scope:** M

#### Task 4.5: Mock-render preview (`scripts/test_email.py`)
**Description:** Render with canned data fixtures, write HTML to `/tmp/preview.html`, open in browser. Support `--mode=deep` flag.
**Acceptance:**
- [ ] `python scripts/test_email.py` opens HTML preview in default browser
- [ ] `python scripts/test_email.py --mode=deep` opens Saturday preview
**Verify:** Manual browser check
**Dependencies:** Task 4.4
**Files:** `scripts/test_email.py`
**Scope:** S

### Checkpoint: Phase 4 complete
- [ ] Visual review in Gmail web — looks right (paste rendered HTML into a draft)
- [ ] Visual review in Gmail iOS — looks right (forward draft to test inbox)
- [ ] Word-count test passes on canned input
- [ ] Reviewer signs off before Phase 5

---

## Phase 5 — Sender + Pipeline Orchestration

Sequential. All Phase 4 outputs must be stable.

#### Task 5.1: AgentMail sender (`src/sender/agentmail.py`)
**Description:** Wrap AgentMail SDK. `send_email(to, subject, html, text, from_addr) -> SendResult(message_id)`. Log `email_sent` with message id + recipients.
**Acceptance:**
- [ ] Sends HTML + plain-text alternative
- [ ] Returns message id; logs success
- [ ] On AgentMail error, raises `EmailSendError` (don't swallow)
**Verify:** `pytest tests/test_sender.py -v` with mocked AgentMail SDK
**Dependencies:** Task 0.4
**Files:** `src/sender/agentmail.py`, `tests/test_sender.py`
**Scope:** S

#### Task 5.2: Daily pipeline orchestration (`src/pipeline/daily.py`)
**Description:** Chain Phase 1 → 2 → 3 → 4 → 5 for Mon-Fri. Handle fact-check failure gracefully (omit AI Take, send rest). Persist run metadata into `runs` table with cost summary.
**Acceptance:**
- [ ] `run_daily(send=True/False)` orchestrates the full pipeline
- [ ] On fact-check failure, AI Take section is omitted; warning logged; email still sent
- [ ] Run metadata (start, end, model spend, recipient count, success/fail) written to `runs` table
- [ ] Integration test with all I/O mocked passes
**Verify:** `pytest tests/test_pipeline_daily.py -v`
**Dependencies:** Tasks 1.x, 2.x, 3.x, 4.x, 5.1
**Files:** `src/pipeline/daily.py`, `tests/test_pipeline_daily.py`
**Scope:** M

#### Task 5.3: Saturday deep pipeline (`src/pipeline/deep.py`)
**Description:** Mostly reuses `daily.py`; swaps template, fetches week-ahead calendar (likely from a separate prompt or static config), uses the longer synthesis prompt variant if any.
**Acceptance:**
- [ ] `run_deep(send=True/False)` orchestrates Saturday flow
- [ ] Uses `saturday_deep.html.j2`
- [ ] Integration test passes
**Verify:** `pytest tests/test_pipeline_deep.py -v`
**Dependencies:** Task 5.2
**Files:** `src/pipeline/deep.py`, `tests/test_pipeline_deep.py`
**Scope:** M

#### Task 5.4: Main CLI + operator script
**Description:** `src/main.py` is the production CLI: `python -m src.main --mode={daily|deep}`. `scripts/run_manual.py` is the operator entry with all the spec's flags: `--dry-run`, `--preview`, `--test-email`, `--reuse-seen-db`, `--ignore-seen-db`, `--mode={daily|deep}`. Subprocess-based smoke tests for flag combos.
**Acceptance:**
- [ ] All flag combinations from spec Section 4 work
- [ ] Mutually-exclusive combos error cleanly (e.g., `--dry-run` + `--test-email`)
- [ ] `--dry-run` end-to-end completes < 60s
- [ ] Subprocess smoke tests for all flag combos pass
**Verify:** `pytest tests/test_run_manual.py -v && time python scripts/run_manual.py --dry-run`
**Dependencies:** Task 5.2, 5.3
**Files:** `src/main.py`, `scripts/run_manual.py`, `tests/test_run_manual.py`
**Scope:** M

### Checkpoint: Phase 5 complete
- [ ] `python scripts/run_manual.py --dry-run` completes < 60s
- [ ] `python scripts/run_manual.py --test-email juan@gmail.com` lands an email in inbox
- [ ] `python scripts/run_manual.py --mode=deep --dry-run` works
- [ ] Reviewer signs off before Phase 6

---

## Phase 6 — Schedule + Deploy

#### Task 6.1: Complete GitHub Actions workflow body
**Description:** Fill in `daily-radar.yml` job: install deps, run `python -m src.main --mode=$MODE`, surface logs. Wire all secrets (OPENROUTER_API_KEY, AGENTMAIL_API_KEY, AGENTMAIL_INBOX_ID, EMAIL_FROM, NEWSDATA_API_KEY).
**Acceptance:**
- [ ] Manual `workflow_dispatch` with `dry_run=true` completes successfully on a real run
- [ ] Manual `workflow_dispatch` with `dry_run=false` lands a real email in juan's inbox
**Verify:** Trigger via GitHub UI; check job logs and inbox
**Dependencies:** Task 5.4, configured secrets in GitHub
**Files:** `.github/workflows/daily-radar.yml`
**Scope:** S

#### Task 6.2: cron-job.org config + README ops section
**Description:** Document the cron-job.org dispatch configuration in `README.md`: schedule (Mon-Fri 06:30 UTC for 07:30 CET CEST-aware; Sat 07:00 UTC for 08:00 CET CEST-aware), payload format, GitHub PAT requirements. Set up the actual cron jobs on cron-job.org.
**Acceptance:**
- [ ] README has a complete "Operations" section with cron-job.org setup steps
- [ ] cron-job.org dispatches successfully (test trigger from cron-job.org UI fires the workflow)
**Verify:** Trigger cron-job.org test; observe GH Actions run start
**Dependencies:** Task 6.1
**Files:** `README.md`
**Scope:** S

#### Task 6.3: Production smoke tests + go-live
**Description:** First real production sends. Smoke test daily at the next weekday 07:30 CET. Smoke test Saturday at 08:00 CET.
**Acceptance:**
- [ ] Mon-Fri 07:30 CET: real email lands in both inboxes
- [ ] Saturday 08:00 CET: deep email lands in both inboxes
- [ ] Run summary in `runs` table shows expected costs
**Verify:** Inbox check + `python scripts/debug_exposure.py --costs`
**Dependencies:** Task 6.2
**Files:** None (operational)
**Scope:** S

### Checkpoint: v0.1 launched
- [ ] Both readers receive daily and Saturday emails on schedule
- [ ] Cost-per-run is below ~$0.50/day (sanity threshold)
- [ ] No silent failures in `runs` table over first week
- [ ] Move to v0.2 planning when stable for 2 weeks

---

## Risks (recap from plan, Phase-3 perspective)

| Risk | Tasks affected | Mitigation |
|---|---|---|
| Lyxor adapter uncrawlable | 2a.4 | Hybrid resolver falls back to yaml; document in ADR |
| yfinance breaks | 2b.1 | Pin version; cache prices in SQLite; pricing-stale warning footer |
| NewsData.io entity tagging weak | 2c.3 | rapidfuzz matcher; +0.5d buffer if accuracy < 80% |
| Fact-checker false positives | 3.4 | Tunable on spike day; `--debug-ai-take` flag for inspection |
| Email rendering breaks in Gmail iOS | 4.x | Test in Phase 4 not Phase 5 |
| AgentMail outage | 5.1 | Document SMTP fallback in README |
| cron-job.org auth breaks | 6.1 | Test workflow_dispatch path manually first |

---

## Open Questions

- Andrea's email address (placeholder until provided)
- Final accent color hex for AI Take (design pass after Phase 4 first render)
- Whether Phase 3 spike day uses real-money OpenRouter or a free credit; document spend per run from spike

---

## Verification Checklist (before starting implementation)

- [x] Every task has acceptance criteria (3 or fewer bullets where possible)
- [x] Every task has a verification command
- [x] Task dependencies are identified and ordered
- [x] No task touches more than ~5 files
- [x] Checkpoints exist between every phase
- [x] Saved to `docs/tasks.md`
- [ ] Human has reviewed and approved this task breakdown
