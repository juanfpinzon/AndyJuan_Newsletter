# Plan: AndyJuan Personal Portfolio Radar — v0.1 Implementation

> Phase 2 of spec-driven-development. Companion to `docs/spec.md`.
> The spec is **what + done**. This plan is **how + in what order**.
> Status: approved.

---

## 1. Approach Overview

Eight phases, sequential at the boundaries, parallel inside the middle (Phases
2a / 2b / 2c). Critical path runs through ETF look-through → exposure resolver
→ analysis → renderer; that path is what determines ship date.

We build **scaffolding + foundation first** (Phase 0–1), then fork into three
parallel data-gathering tracks (Phase 2a/b/c), converge into analysis (Phase
3), then sequential render → send → schedule (Phases 4–6).

Total target: **2–3 weeks of focused work** (~12–14 days), aligned with the
spec's v0.1 timeline.

---

## 2. Plan-Time Decisions (not in the spec — flag if wrong)

These are calls I'm making in the plan. They aren't in `docs/spec.md`. Push
back on any of them before we move to Phase 3 task breakdown.

| # | Decision | Why |
|---|---|---|
| D1 | **Use `yfinance` for v0.1 pricing** (yesterday's close + today's snapshot + EUR conversion) | Free, no API key, covers UCITS tickers, US stocks, crypto, and FX in one library. Unofficial Yahoo wrapper — fragile but acceptable for personal-use v0.1. v0.2 SnapTrade replaces it for IBKR side. |
| D2 | **EUR is the reporting base currency** | Matches Snowball portfolio. yfinance handles forex (`EURUSD=X`, etc.) on the same path as ticker prices. |
| D3 | **Cost tracking in USD** (OpenRouter bills in USD) | Convert to EUR at display time only, using the same yfinance FX call already in flight for portfolio P&L. |
| D4 | **Theme tiebreaker for multi-theme news** | Each entity has a `primary_theme` in `themes.yaml`. Articles render once under their primary theme; an "Affects" badge surfaces secondary-theme exposures inline. No dedup, just attribution. |
| D5 | **Test LLM fixtures captured from a one-time spike** | Phase 3 starts with a manual "spike day" where we run the real ranker / flash / synthesis / fact-checker against a small fixed input, save outputs to `tests/fixtures/llm/`, and use them as canned responses for all subsequent CI runs. |
| D6 | **`config/portfolio.yaml` initial population is seeded from Snowball, then validated from transactions** | Bootstrap from the Snowball snapshot (10 positions). The CSV importer is then validated by re-running it against Snowball's transaction export and asserting the merged result preserves the seeded file's enrichment. |
| D7 | **CI runs `pytest` only on PR; no live API calls** | Live spikes happen locally before merge. CI uses fixtures + mocks only. |

---

## 3. Component Dependency Graph

```
                     ┌────────────────────────┐
                     │ Phase 0: Foundation    │
                     │ scaffolding, utils,    │
                     │ storage, config loader │
                     └────────────┬───────────┘
                                  │
                     ┌────────────▼───────────┐
                     │ Phase 1: Portfolio +   │
                     │ config files + import_ │
                     │ snowball + tests       │
                     └────────────┬───────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
  ┌─────────▼────────┐  ┌─────────▼────────┐  ┌─────────▼─────────┐
  │ Phase 2a:        │  │ Phase 2b:        │  │ Phase 2c:         │
  │ Look-through +   │  │ Pricing + P&L    │  │ News fetch +      │
  │ exposure         │  │ (yfinance)       │  │ entity match      │
  │ (CRITICAL PATH)  │  │                  │  │                   │
  └─────────┬────────┘  └─────────┬────────┘  └─────────┬─────────┘
            │                     │                     │
            └─────────────────────┼─────────────────────┘
                                  │
                     ┌────────────▼───────────┐
                     │ Phase 3: Analysis      │
                     │ (ranker, flashes,      │
                     │ synthesis, fact-check) │
                     └────────────┬───────────┘
                                  │
                     ┌────────────▼───────────┐
                     │ Phase 4: Renderer      │
                     │ (templates, theme      │
                     │ groups, dark CSS)      │
                     └────────────┬───────────┘
                                  │
                     ┌────────────▼───────────┐
                     │ Phase 5: Sender +      │
                     │ pipeline orchestration │
                     │ + run_manual.py        │
                     └────────────┬───────────┘
                                  │
                     ┌────────────▼───────────┐
                     │ Phase 6: Schedule +    │
                     │ deploy (GH Actions +   │
                     │ cron-job.org)          │
                     └────────────────────────┘
```

---

## 4. Phases

### Phase 0 — Foundation *(sequential, ~1 day)*

**Deliverables:**
- `pyproject.toml` with v0.1 deps (httpx[http2], jinja2, premailer, openai,
  agentmail, pyyaml, sqlite-utils, python-dotenv, structlog, feedparser,
  beautifulsoup4, lxml, rapidfuzz, **yfinance**) + dev deps (pytest,
  pytest-asyncio, respx)
- `.env.example` with all required keys (OPENROUTER_API_KEY,
  AGENTMAIL_API_KEY, AGENTMAIL_INBOX_ID, EMAIL_FROM, NEWSDATA_API_KEY)
- `.gitignore` (data/, .env, *.pyc, __pycache__, .pytest_cache, *.db)
- Empty package skeleton: `src/__init__.py` + all subdirectory `__init__.py`
- `src/utils/log.py` — structlog config (JSONL → `data/logs/andyjuan.jsonl`)
- `src/utils/http.py` — shared `httpx.AsyncClient` factory with retry policy
- `src/utils/llm.py` — OpenRouter wrapper using `openai` SDK with custom
  base URL; per-call cost tracking; model fallback logic
- `src/storage/db.py` + `src/storage/schemas.py` — SQLite tables: `runs`,
  `articles_seen`, `exposure_snapshots`, `llm_calls`
- `src/config.py` — settings.yaml + env override loader
- `.github/workflows/daily-radar.yml` — empty skeleton with workflow_dispatch
  + repository_dispatch triggers
- `README.md` (operator-oriented quickstart) + `CLAUDE.md` (Claude Code agent-oriented) + `AGENTS.md` (byte-for-byte copy of `CLAUDE.md` so Codex picks up the same context — keep them in sync going forward)

**Verification checkpoint:**
- [ ] `pip install -e ".[dev]"` succeeds on a clean venv
- [ ] `pytest tests/` passes (empty tests directory; just confirms collection works)
- [ ] `python -c "import src; from src.utils import log, http, llm"` succeeds
- [ ] `ruff check .` passes

---

### Phase 1 — Portfolio + Configs + Importer *(sequential, ~1 day)*

**Deliverables:**
- `src/portfolio/models.py` — `Position` dataclass (frozen, Decimal fields)
- `src/portfolio/loader.py` — `load_portfolio(path) -> list[Position]`
- `scripts/import_snowball.py` — CSV → yaml merge with:
  - Supports both holdings snapshots and Snowball transaction exports
  - Preserve enrichment on existing tickers
  - Scaffold new tickers with `asset_type: stock` defaulted
  - `--dry-run` flag for diff preview
  - Loud failure on schema drift / currency mismatch
  - Non-destructive on removed tickers (warn only)
- `config/portfolio.yaml` — initial 10-position file from the Snowball snapshot
- `config/etf_holdings.yaml` — manual fallback top-10 for each of 8 ETFs
  (one-time setup; ~80 entries total)
- `config/themes.yaml` — themes (Defense, AI/Semis, Precious Metals, EU
  Banks, US Megacaps, Macro/FX) + entity → theme mapping with `primary_theme`
- `config/macro_feeds.yaml` — RSS URLs for ECB, Fed, FT macro, Reuters macro
- `config/recipients.yaml` — juan + andrea
- `config/settings.yaml` — initial thresholds, model assignments, cadence
- `tests/fixtures/portfolio.yaml` — small reference portfolio
- `tests/fixtures/snowball-export.csv` — sample Snowball CSV for importer test
- `tests/fixtures/snowball-transactions.csv` — redacted Snowball transaction export for importer aggregation tests
- `tests/test_portfolio.py` — loader unit tests
- `tests/test_import_snowball.py` — importer tests (preserve enrichment,
  scaffold new, dry-run, transaction aggregation, schema-drift error,
  currency-mismatch error)

**Verification checkpoint:**
- [ ] `python scripts/import_snowball.py tests/fixtures/snowball-export.csv --dry-run` shows expected diff
- [ ] `python scripts/import_snowball.py tests/fixtures/snowball-transactions.csv --dry-run` shows expected diff
- [ ] `pytest tests/test_portfolio.py tests/test_import_snowball.py -v` passes
- [ ] `config/portfolio.yaml` loads cleanly (no schema errors)

---

### Phase 2a — Look-through + Exposure Resolver *(parallel, ~2 days, CRITICAL PATH)*

**Deliverables:**
- `src/lookthrough/adapters/{ishares,vaneck,ssga,globalx,lyxor}.py` — one
  scraper per issuer with consistent return type `list[Holding]`
- `src/lookthrough/resolver.py` — orchestrator: try scraper, fall back to
  `etf_holdings.yaml`, log `lookthrough_fallback_used` with issuer name
- `src/exposure/models.py` — `ExposureEntry(entity, composite_weight, paths)`
  dataclass
- `src/exposure/resolver.py` — `compute_exposure(positions, lookthrough_data)
  -> dict[entity, ExposureEntry]`
- `scripts/refresh_etf_holdings.py` — runs all scrapers, caches results to
  SQLite, prints success/failure summary
- `scripts/debug_exposure.py` — dump exposure map as table; supports
  `--costs` flag for LLM cost summary
- `tests/fixtures/etf_holdings/{ishares,vaneck,ssga,globalx,lyxor}/*.{csv,json,html}`
  — canned responses
- `tests/test_lookthrough.py` — adapter unit tests with respx mocking +
  fallback behavior test (patch scraper to raise, verify yaml fallback used)
- `tests/test_exposure.py` — math tests at **100% coverage** (this is the
  load-bearing math; correctness is non-negotiable)

**Verification checkpoint:**
- [ ] `python scripts/refresh_etf_holdings.py` returns success for all 5
  issuers OR cleanly falls back to yaml with logged warnings
- [ ] `python scripts/debug_exposure.py` prints a sane exposure map
- [ ] Coverage on `src/exposure/` = 100%
- [ ] NVDA composite weight in test scenario matches hand-calculated value

---

### Phase 2b — Pricing + P&L *(parallel, ~1 day)*

**Deliverables:**
- `src/pricing/yfinance_client.py` — wraps yfinance with retry + EUR
  conversion via `EURUSD=X`, `EURGBP=X` etc. as needed
- `src/pnl/models.py` — `PnLSnapshot` and `DailyDelta` dataclasses
- `src/pnl/calculator.py` — `compute_pnl(positions, prices_today,
  prices_yesterday) -> dict[ticker, PnLSnapshot]`; handles weekend/holiday
  fallback (uses last trading day close)
- `tests/fixtures/yfinance/*.json` — canned yfinance responses
- `tests/test_pricing.py` — yfinance wrapper tests (mocked)
- `tests/test_pnl.py` — math tests at **100% coverage**; reference numbers
  match the Snowball screenshot to within €0.01

**Verification checkpoint:**
- [ ] `python -c "from src.pricing.yfinance_client import fetch; print(fetch(['NVDA','GOOGL'], 'EUR'))"` returns prices in EUR
- [ ] P&L for the test portfolio matches Snowball screenshot within rounding
- [ ] Coverage on `src/pnl/` = 100%

---

### Phase 2c — News Fetch + Entity Matching *(parallel, ~2 days)*

**Deliverables:**
- `src/fetcher/newsdata.py` — NewsData.io client: paginated fetch, dedup
  against `articles_seen` SQLite table, retry on 429, structured output
- `src/fetcher/macro_rss.py` — feedparser-based macro RSS reader, ETag-aware
- `src/entity_match/matcher.py` — rapidfuzz-based article body + title →
  entity universe matcher; returns confidence-scored matches
- `tests/fixtures/news/{newsdata,rss}/*.json` — canned API responses
- `tests/test_fetcher.py` — respx-mocked NewsData.io + RSS tests
- `tests/test_entity_match.py` — matcher accuracy on hand-labeled fixtures
  (target: 80%+ correct entity tagging on a 30-article test set)

**Verification checkpoint:**
- [ ] Live spike: `python -c "from src.fetcher.newsdata import fetch; print(len(fetch('NVDA', hours=24)))"` returns at least one article
- [ ] Matcher correctly tags ≥ 80% of hand-labeled test articles to the right entity
- [ ] Macro RSS feeds parse without errors

---

### Phase 3 — Analysis *(sequential after 2a/b/c, ~3 days)*

**Spike day at start of phase (D5):** Run real OpenRouter calls against a
small fixed input, save outputs to `tests/fixtures/llm/` for canned-response
tests.

**Deliverables:**
- `prompts/news_ranker.md` — middle-aggression filter prompt (Haiku);
  inputs: candidate articles + exposure map JSON; output: ranked list with
  composite-exposure weighting, top-15 OR ≥5%
- `prompts/theme_flash.md` — Sonnet, 1–2 sentences per theme
- `prompts/ai_synthesis.md` — Sonnet, bottom paragraphs + suggestions;
  hard rule: "no novel facts beyond input"
- `prompts/fact_checker.md` — Haiku, fail-closed; output: `{ok: bool,
  flagged_claims: [str]}`
- `src/analyzer/ranker.py` — wraps Haiku call with structured input/output
- `src/analyzer/theme_flash.py` — per-theme Sonnet call
- `src/analyzer/synthesis.py` — bottom Sonnet call
- `src/analyzer/fact_checker.py` — post-render Haiku check; on `ok=false`,
  the AI Take is omitted and a warning is logged; the rest of the email
  still sends
- `tests/fixtures/llm/` — captured responses (ranker, flash, synthesis,
  fact-checker) from spike-day
- `tests/test_ranker.py`, `tests/test_theme_flash.py`,
  `tests/test_synthesis.py`, `tests/test_fact_checker.py` — fixture-based;
  fact-checker tests include a planted-novel-fact test (target: blocks the
  AI Take, logs the warning)

**Verification checkpoint:**
- [ ] Ranker output respects threshold rule (top-15 OR ≥5% composite) on
      canned input
- [ ] Per-theme flashes are 1–2 sentences each
- [ ] Synthesis cites only items in the rendered input
- [ ] Fact-checker blocks AI Take on `"NVDA acquired AMD"` planted into
      Sonnet output; warning logged with claim text
- [ ] Coverage on `src/analyzer/fact_checker.py` ≥ 90%

---

### Phase 4 — Renderer *(sequential, ~3 days)*

**Deliverables:**
- `src/renderer/theme_groups.py` — group news + cards by theme; apply per-
  theme cap (5 items max); attach per-theme AI flash; compute the
  Concentrated Exposures widget rows
- `src/renderer/render.py` — jinja2 + premailer; produces inline-styled HTML
  + plain-text fallback
- `templates/daily_email.html.j2` — Mon–Fri layout
- `templates/saturday_deep.html.j2` — Saturday deep layout (extends daily;
  adds week-ahead earnings/macro calendar section + longer synthesis)
- Dark Binance/IBKR-inspired CSS embedded in templates:
  - Base: deep navy/charcoal (#0b0e11 / #1e2329)
  - Gain: green accent (#0ecb81)
  - Loss: red accent (#f6465d)
  - AI accent: muted gold (#f0b90b or similar — design pass)
  - Card surfaces: slightly lighter than base (#1e2329)
  - Text: high-contrast off-white (#eaecef)
- `🤖 AI-generated · not investment advice` chip component (template macro)
- `scripts/test_email.py` — mock-render preview with canned data, opens in
  browser
- `tests/test_renderer.py` — assertions on:
  - All 6 sections present in correct order
  - AI chip present on every AI Take block
  - Word count ≤ 1,000 on canned input
  - Every `<a>` rendered for a news item has a non-empty `href`
  - "Affects" badge appears when applicable

**Verification checkpoint:**
- [ ] `python scripts/test_email.py` opens a rendered HTML preview in browser
- [ ] Visual review in Gmail web (paste rendered HTML into a draft) — looks right
- [ ] Visual review in Gmail iOS (forward draft to test inbox) — looks right
- [ ] Word-count test passes on canned input
- [ ] All renderer tests pass

---

### Phase 5 — Sender + Pipeline Orchestration *(sequential, ~1 day)*

**Deliverables:**
- `src/sender/agentmail.py` — wraps AgentMail SDK; logs `email_sent` with
  message id + recipient list
- `src/pipeline/daily.py` — Mon–Fri orchestration (chains all phases together)
- `src/pipeline/deep.py` — Saturday orchestration (uses deep template + extra
  data: week-ahead calendar, longer synthesis)
- `src/main.py` — CLI entry: `python -m src.main --mode={daily|deep}`
- `scripts/run_manual.py` — operator entry with all flags from spec Section 4
  (--dry-run, --preview, --test-email, --reuse-seen-db, --ignore-seen-db,
  --mode=deep)
- `tests/test_pipeline_daily.py` + `tests/test_pipeline_deep.py` —
  integration tests with all I/O mocked; assert end-to-end transform produces
  expected rendered output
- `tests/test_run_manual.py` — subprocess-based smoke tests for flag combos

**Verification checkpoint:**
- [ ] `python scripts/run_manual.py --dry-run` completes < 60s, no send
- [ ] `python scripts/run_manual.py --preview` writes valid HTML, opens in browser
- [ ] `python scripts/run_manual.py --test-email juan@gmail.com` sends one email
- [ ] `python scripts/run_manual.py --mode=deep --dry-run` works
- [ ] `python scripts/run_manual.py --reuse-seen-db --preview` rerenders without fetch

---

### Phase 6 — Schedule + Deploy *(sequential, ~1 day)*

**Deliverables:**
- `.github/workflows/daily-radar.yml` complete:
  - `workflow_dispatch` for manual UI/CLI runs
  - `repository_dispatch` (event: `run-daily-radar`) for cron-job.org
  - Inputs: `mode` (default: daily), `dry_run` (default: false)
  - Job: install deps, run `python -m src.main --mode=$MODE`
  - Secrets: OPENROUTER_API_KEY, AGENTMAIL_API_KEY, AGENTMAIL_INBOX_ID,
    EMAIL_FROM, NEWSDATA_API_KEY
- cron-job.org configuration documented in `README.md`:
  - Mon–Fri 06:30 UTC (= 07:30 CET CEST-aware)
  - Sat 07:00 UTC (= 08:00 CET CEST-aware)
  - POST to `/dispatches` with appropriate `client_payload`
- AgentMail inbox set up; `EMAIL_FROM` confirmed deliverable
- NewsData.io key set up
- OpenRouter key set up
- First production smoke test: trigger via `workflow_dispatch` with
  `dry_run: true`, verify pipeline completes without sending; second smoke
  test with `dry_run: false` to test inbox

**Verification checkpoint:**
- [ ] Manual `workflow_dispatch` with `dry_run: true` completes successfully
- [ ] Manual `workflow_dispatch` with `dry_run: false` lands an email in inbox
- [ ] cron-job.org dispatches successfully (test trigger from cron-job.org UI)
- [ ] Mon–Fri 07:30 CET trigger fires next business day; email lands in
      both inboxes
- [ ] Saturday 08:00 CET trigger fires; deep email lands

---

## 5. Critical Path & Parallelization

**Critical path (longest dependency chain):**

```
Phase 0 (1d) → Phase 1 (1d) → Phase 2a (2d) → Phase 3 (3d) → Phase 4 (3d) → Phase 5 (1d) → Phase 6 (1d)
                                                                                  
Total CP: 12 days
```

**Parallel work** during Phase 2 (after Phase 1 lands):
- Track A: Phase 2a (look-through + exposure) — 2 days, on critical path
- Track B: Phase 2b (pricing + P&L) — 1 day, slack
- Track C: Phase 2c (news + entity match) — 2 days, slack

If working solo: complete 2a first (critical path), then 2b/2c. If
paralellized (multiple agents / pair): all three in parallel collapses
Phase 2 to 2 days.

**Renderer overlap with Analysis:** once Phase 3 has stable output shapes
(`RankedNews`, `ThemeFlash`, `Synthesis`), Phase 4 can begin renderer template
work in parallel with prompt tuning — saves ~1 day. Recommended.

---

## 6. Risks (plan-execution specific)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | One ETF issuer's page is uncrawlable (likely Lyxor/Amundi based on past patterns) | High | Low | Hybrid resolver falls back to `etf_holdings.yaml` cleanly; that issuer just stays manual until v0.2 |
| R2 | yfinance breaks (Yahoo HTML changes) | Medium | Medium | Pin a known-good version; fall back to last cached price + a `pricing_stale` warning footer in the email |
| R3 | NewsData.io entity tagging worse than spec assumed | Medium | Medium | Phase 2c builds the rapidfuzz matcher to compensate; budget +0.5 day if accuracy < 80% on test set |
| R4 | Email rendering breaks in Gmail iOS (sparklines, custom fonts) | Medium | Low | v0.1 doesn't ship sparklines (text deltas only); test in Gmail web + iOS during Phase 4 not Phase 5 |
| R5 | OpenRouter cost reporting drifts from actual billing | Low | Low | Reconcile `llm_calls` SQLite table against OpenRouter dashboard weekly during v0.1 |
| R6 | Fact-checker false positives (legitimate synthesis flagged) | Medium | Medium | Tune prompt during spike day; allow operator to inspect flagged claims via a `--debug-ai-take` flag on `run_manual.py` |
| R7 | AgentMail rate limit / outage on first send | Low | High | Test with `--test-email` first; document fallback to direct SMTP if AgentMail bounces |
| R8 | cron-job.org → GitHub Actions dispatch authentication breaks | Low | High | Test workflow_dispatch path manually first; cron-job.org and dispatch token reset documented in README |

---

## 7. What This Plan Does NOT Cover

The following are **explicitly out of v0.1** and stay out of this plan:

- **SnapTrade live integration** → v0.2 plan
- **Binance read-only API** → v0.2 plan
- **Sparklines / inline SVG charts** → v0.2 plan
- **Cost optimization for prod** (entity-level caching, article dedup across
  entities, RSS-first macro to reduce news API calls) → v0.3 plan
- **Monitoring + alerting** (heartbeat, send-failure pages) → v0.3 plan
- **Andrea's email address resolution** — config edit, not engineering work
- **Lot-level cost basis (FIFO)** — averaged cost basis only; revisit only
  if AI Take needs lot-level granularity

---

## 8. Verification Checklist (before exiting Phase 2)

- [x] Components and their dependencies identified
- [x] Implementation order determined (8 phases, critical path mapped)
- [x] Plan-time decisions explicitly called out for review (D1–D7)
- [x] Risks named with likelihood/impact/mitigation
- [x] Parallel vs sequential work identified
- [x] Verification checkpoints defined per phase
- [x] Plan saved to `docs/plan.md`
- [ ] Human has reviewed and approved this plan

---

## 9. After Approval

On approval, Phase 3 (Tasks) takes each phase from this plan and breaks it
into discrete, single-session tasks with explicit acceptance criteria,
verification steps, and file lists. We use `agent-skills:planning-and-task-breakdown`
to drive that.
