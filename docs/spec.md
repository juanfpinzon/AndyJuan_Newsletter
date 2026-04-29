# Spec: AndyJuan Personal Portfolio Radar

> Companion to `andyjuan-portfolio-radar.md` (the aligned one-pager).
> The one-pager is **what + why**. This spec is **how + done**.
> Status: v0.1 MVP. Reviewed: approved.

---

## 1. Objective

Build a daily morning HTML email (and Saturday deep brief) for two readers
(Juan, Andrea) that ranks market news by their actual portfolio exposure —
looking through ETFs to top-10 constituents — and reports yesterday's P&L,
in a Gmail-rendered dark-themed brief with clearly-labeled AI commentary
that respects a 90-second read budget.

**Users:** Juan (`juancho704@gmail.com`), Andrea (`andrea.aliciap@gmail.com`). Identical content.

**Why:** Personalized portfolio news radar with exposure-weighted ranking is
not available off-the-shelf. Snowball Analytics tracks performance but
does not surface news. Generic financial newsletters don't know our exposures.

**Success looks like (v0.1):**
- A daily 07:30 CET email lands in both inboxes Mon–Fri
- A Saturday 08:00 CET deep brief lands in both inboxes
- Email contains all 6 sections in order: P&L Scoreboard → Concentrated
  Exposures → Theme Groups (with cards + news + per-theme AI flash) →
  AI Synthesis + Suggestions → Macro Footer
- AI Take blocks render with accent color + `🤖 AI-generated · not investment advice` chip
- Every news item has a clickable source URL
- Rendered word count ≤ 1,000 words (≈ 90s read at 240wpm)
- Cost per run is tracked and queryable

---

## 2. Phasing (this spec scopes v0.1)

| Version | Scope | Target |
|---|---|---|
| **v0.1** | `portfolio.yaml` (canonical internal format) + `scripts/import_snowball.py` to merge Snowball CSV exports, hybrid ETF look-through, NewsData.io free tier, Haiku ranker + Sonnet AI Take + Haiku fact-checker, daily + Saturday templates, AgentMail send, GitHub Actions schedule | 2–3 weeks |
| v0.2 | SnapTrade live integration, Binance read-only API, sparklines (inline SVG/CSS bars), enhanced exposure-map deltas | +2 weeks |
| v0.3 | Cost optimization for prod (entity-level caching, article dedup, RSS-first macro), monitoring + alerting | +1–2 weeks |
| v1.0 | Hardening, observability, performance tuning, post-mortem-driven fixes | continuous |

---

## 3. Tech Stack

**Language:** Python 3.11+

**Runtime dependencies (lifted from DP_news_scout unless marked NEW):**
- `httpx[http2]` — HTTP client (NewsData.io, ETF scrapers, OpenRouter)
- `feedparser` — macro RSS feeds
- `beautifulsoup4`, `lxml` — ETF scraper HTML parsing
- `jinja2`, `premailer` — email templating + CSS inlining for Gmail
- `openai` — used to call OpenRouter (gateway for Haiku + Sonnet + fallback)
- `agentmail` — email sending
- `pyyaml` — config loading
- `sqlite-utils` — local state (run history, dedup, exposure snapshots, cost tracking)
- `python-dotenv` — env loading
- `structlog` — structured JSONL logging
- **NEW** `rapidfuzz` — fuzzy match articles → entity universe (NewsData.io tagging is weak)

**Deferred (added in v0.2):**
- `snaptrade-python-sdk` — IBKR positions + daily P&L
- `python-binance` — read-only spot holdings (Read Info key only, IP-whitelisted)

**Dev dependencies:**
- `pytest >= 8.0`
- `pytest-asyncio` — async test support
- `respx` — httpx mocking

**LLM gateway:** OpenRouter (single API key routes to Anthropic models).
- Ranker: `anthropic/claude-haiku-4.5`
- AI Flashes + AI Synthesis: `anthropic/claude-sonnet-4-6`
- Fact-checker: `anthropic/claude-haiku-4.5`
- Fallback: `anthropic/claude-haiku-4.5`

**News:** NewsData.io (free tier 200 reqs/day for v0.1; ~$20/mo Basic for prod).

**Email:** AgentMail.

**Scheduling:** cron-job.org → GitHub `repository_dispatch` (event `run-daily-radar`)
→ GitHub Actions workflow → `python -m src.main --mode {daily|deep}`.

**Storage:** SQLite at `data/andyjuan.db`.

---

## 4. Commands

```bash
# install
pip install -e ".[dev]"

# tests
pytest tests/ -v
pytest tests/test_exposure.py -v          # focused
pytest tests/ -v --cov=src --cov-report=term-missing  # with coverage

# lint (no formatter wars — ruff format + ruff check)
ruff format .
ruff check .

# manual operator runs
python scripts/run_manual.py --dry-run                      # full pipeline, no send
python scripts/run_manual.py --preview                      # render HTML + open in browser
python scripts/run_manual.py --test-email you@example.com   # send to one address
python scripts/run_manual.py --mode=deep --dry-run          # Saturday deep brief
python scripts/run_manual.py --reuse-seen-db --preview      # rerender from stored articles
python scripts/run_manual.py --ignore-seen-db               # refetch ignoring dedup

# debug + dev tools
python scripts/debug_exposure.py                            # print entity → composite weight + paths
python scripts/refresh_etf_holdings.py                      # update ETF cache via scrapers
python scripts/test_email.py                                # mock-render with canned data
python scripts/import_snowball.py snowball-export.csv       # merge Snowball CSV → portfolio.yaml
python scripts/import_snowball.py snowball-export.csv --dry-run  # show diff without writing

# production entry point (run from cron via GH Actions)
python -m src.main --mode=daily
python -m src.main --mode=deep
```

---

## 5. Project Structure

```
AndyJuan_Newsletter/
├── pyproject.toml
├── .env.example
├── README.md
├── CLAUDE.md                             # Claude Code agent context
├── AGENTS.md                             # byte-for-byte copy of CLAUDE.md, for Codex
├── andyjuan-portfolio-radar.md           # one-pager (already exists)
├── .github/
│   └── workflows/
│       └── daily-radar.yml               # repository_dispatch + workflow_dispatch
├── docs/
│   ├── spec.md                           # this file
│   └── adr/                              # architecture decision records
├── config/
│   ├── settings.yaml                     # thresholds, models, cadence flags
│   ├── recipients.yaml                   # juan + andrea
│   ├── portfolio.yaml                    # holdings (v0.1 source of truth)
│   ├── etf_holdings.yaml                 # manual fallback per ETF (hybrid)
│   ├── themes.yaml                       # theme definitions + entity → theme mapping
│   └── macro_feeds.yaml                  # RSS feeds for macro/FX/rates
├── prompts/
│   ├── news_ranker.md                    # Haiku — middle-aggression filter
│   ├── theme_flash.md                    # Sonnet — 1-2 sentences per theme
│   ├── ai_synthesis.md                   # Sonnet — bottom paragraphs + suggestions
│   └── fact_checker.md                   # Haiku — flag novel facts
├── templates/
│   ├── daily_email.html.j2               # Mon-Fri
│   └── saturday_deep.html.j2             # Saturday
├── scripts/
│   ├── run_manual.py                     # operator entry, all flags
│   ├── test_email.py                     # mock-render preview
│   ├── debug_exposure.py                 # exposure map dump
│   ├── refresh_etf_holdings.py           # update ETF scraper cache
│   └── import_snowball.py                # merge Snowball CSV → portfolio.yaml (preserves enrichment)
├── src/
│   ├── __init__.py
│   ├── main.py                           # pipeline orchestrator (CLI entry)
│   ├── portfolio/                        # v0.1: yaml loader; v0.2: SnapTrade + Binance
│   │   ├── __init__.py
│   │   ├── loader.py                     # portfolio.yaml → Position[]
│   │   └── models.py                     # Position dataclass
│   ├── lookthrough/                      # ETF top-10 (hybrid: scrapers + yaml fallback)
│   │   ├── __init__.py
│   │   ├── resolver.py                   # orchestrator: try scraper, fall back to yaml
│   │   └── adapters/                     # one file per issuer
│   │       ├── ishares.py
│   │       ├── vaneck.py
│   │       ├── ssga.py
│   │       ├── globalx.py
│   │       └── lyxor.py
│   ├── exposure/                         # composite exposure map computation
│   │   ├── __init__.py
│   │   ├── resolver.py                   # positions + lookthrough → exposure map
│   │   └── models.py                     # ExposureEntry dataclass
│   ├── pnl/                              # daily gain/loss + total P&L
│   │   ├── __init__.py
│   │   ├── calculator.py
│   │   └── models.py
│   ├── fetcher/                          # news + macro RSS
│   │   ├── __init__.py
│   │   ├── newsdata.py                   # NewsData.io client
│   │   └── macro_rss.py                  # feedparser-based macro feeds
│   ├── entity_match/                     # rapidfuzz article → entity universe
│   │   ├── __init__.py
│   │   └── matcher.py
│   ├── analyzer/                         # ranker + AI Take + fact-check
│   │   ├── __init__.py
│   │   ├── ranker.py                     # Haiku — middle-aggression filter
│   │   ├── theme_flash.py                # Sonnet — per-theme flashes
│   │   ├── synthesis.py                  # Sonnet — bottom synthesis + suggestions
│   │   └── fact_checker.py               # Haiku — fail-closed novel-fact guard
│   ├── renderer/
│   │   ├── __init__.py
│   │   ├── render.py                     # jinja2 + premailer
│   │   └── theme_groups.py               # group news + cards by theme
│   ├── sender/
│   │   ├── __init__.py
│   │   └── agentmail.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                         # sqlite-utils wrapper
│   │   └── schemas.py                    # table schemas
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── daily.py                      # daily mode orchestration
│   │   └── deep.py                       # Saturday deep mode orchestration
│   └── utils/
│       ├── __init__.py
│       ├── http.py                       # shared httpx client + retries
│       ├── llm.py                        # OpenRouter wrapper + cost tracking
│       └── log.py                        # structlog config
├── tests/
│   ├── conftest.py
│   ├── fixtures/                         # canned API responses, ETF CSVs, news payloads
│   ├── test_portfolio.py
│   ├── test_lookthrough.py
│   ├── test_exposure.py
│   ├── test_pnl.py
│   ├── test_fetcher.py
│   ├── test_entity_match.py
│   ├── test_ranker.py
│   ├── test_theme_flash.py
│   ├── test_synthesis.py
│   ├── test_fact_checker.py
│   ├── test_renderer.py
│   ├── test_sender.py
│   ├── test_pipeline_daily.py
│   ├── test_pipeline_deep.py
│   ├── test_run_manual.py
│   └── test_import_snowball.py
└── data/
    ├── andyjuan.db                       # SQLite (gitignored)
    └── logs/
        └── andyjuan.jsonl                # structlog output (gitignored)
```

**Approach:** Copy DP_news_scout's directory shapes (utility modules, scripts
patterns, config patterns) into this repo as scaffolding, then write fresh
domain code. No git-history carryover.

### 5.1 Portfolio data flow (Snowball CSV ↔ `portfolio.yaml`)

`config/portfolio.yaml` is the **canonical internal source of truth**. Snowball
CSV is the **inbound update channel**.

**Why YAML and not CSV directly:** Snowball's CSV export carries shares, cost
basis, and current value, but not `asset_type`, `issuer`, `isin`, or theme
assignments — fields the ETF look-through and theme grouping require. YAML
lets us layer that enrichment without forking Snowball's schema.

**Update workflow:**
1. Export holdings CSV from Snowball
2. Run `python scripts/import_snowball.py snowball-export.csv`
3. The importer merges into `portfolio.yaml`:
   - **Existing tickers:** updates `shares` + `cost_basis_eur` only; preserves
     `asset_type`, `issuer`, `isin`, `theme`, and any other enrichment fields
   - **New tickers:** scaffolds an entry with `asset_type: stock` defaulted
     and `issuer: null`; logs a warning so you remember to enrich ETF entries
4. `--dry-run` mode shows the diff without writing

**Failure modes the importer must handle:**
- Snowball changes their CSV column headers → importer logs a clear error and
  refuses to write; never silently corrupts `portfolio.yaml`
- A ticker exists in `portfolio.yaml` but no longer in CSV → flagged as
  "no longer in Snowball" but **not** auto-removed (manual confirmation only;
  you might still hold it in Binance off-Snowball)
- Currency mismatch → fail loudly; don't auto-convert

`portfolio.yaml` should be checked into git so trade history is reviewable in
PRs. Treat schema changes as breaking and bump a version field on the file.

---

## 6. Code Style

Python 3.11+ with type hints, `Decimal` for money, `frozen=True` dataclasses
for value types, `structlog` for all log events. Async where it helps
(httpx, parallel API calls), sync where it doesn't.

**Example — domain model + loader:**

```python
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

import structlog
import yaml

log = structlog.get_logger()

AssetType = Literal["stock", "etf", "crypto"]


@dataclass(frozen=True)
class Position:
    ticker: str
    isin: str | None
    asset_type: AssetType
    issuer: str | None
    shares: Decimal
    cost_basis_eur: Decimal


def load_portfolio(path: Path) -> list[Position]:
    """Parse portfolio.yaml into a flat list of Position records."""
    raw = yaml.safe_load(path.read_text())
    positions = [
        Position(
            ticker=entry["ticker"],
            isin=entry.get("isin"),
            asset_type=entry["asset_type"],
            issuer=entry.get("issuer"),
            shares=Decimal(str(entry["shares"])),
            cost_basis_eur=Decimal(str(entry["cost_basis_eur"])),
        )
        for entry in raw["positions"]
    ]
    log.info("portfolio_loaded", count=len(positions), source=str(path))
    return positions
```

**Conventions:**
- `Decimal` (never `float`) for monetary amounts and weights
- `frozen=True` dataclasses for value types; mutable dataclasses only when needed
- Type hints on all public functions and dataclasses
- `log.<event>(snake_case_event_name, **fields)` — never f-string log messages
- All settings come from `config/settings.yaml`, with env var override; never hardcode tickers, recipients, or thresholds
- Async: use `httpx.AsyncClient` for parallel I/O; sync stdlib for everything else
- Errors: raise typed exceptions (`PortfolioLoadError`, `LookthroughFailure`); catch at pipeline boundaries
- File naming: `snake_case.py`; class `PascalCase`; functions/vars `snake_case`
- Imports: stdlib → third-party → first-party, separated by blank lines
- Lint/format: `ruff check` + `ruff format`

---

## 7. Testing Strategy

**Framework:** pytest with `pytest-asyncio` for async tests and `respx`
for mocking httpx.

**Layout:** `tests/` mirrors `src/` — one test module per domain module.

**Test levels:**
- **Unit:** every domain module (`portfolio`, `exposure`, `pnl`,
  `entity_match`, `ranker` logic) — pure-function tests with fixtures
- **Integration:** `pipeline/daily` and `pipeline/deep` — full pipeline with all
  external I/O mocked, asserts on rendered output structure
- **LLM tests:** canned response fixtures stored under `tests/fixtures/llm/`;
  no live model calls in CI; one `--live` opt-in suite for manual smoke tests
- **Renderer tests:** assert on key DOM elements (section presence, AI chip
  rendered, P&L numbers correctly formatted) + word-count budget assertion
- **Operator script tests:** subprocess-based smoke tests for `run_manual.py`
  flag combinations

**Coverage targets:**
- 80% overall on `src/`
- **100% on `src/exposure/`** — math correctness is critical
- **100% on `src/pnl/`** — same reason
- 90% on `src/analyzer/fact_checker.py` — guardrail integrity

**Fixtures:**
- `tests/fixtures/portfolio.yaml` — small reference portfolio
- `tests/fixtures/etf_holdings/` — sample CSVs + JSONs from each issuer
- `tests/fixtures/news/` — canned NewsData.io responses
- `tests/fixtures/llm/` — canned ranker, flash, synthesis, fact-checker outputs

**CI:**
- GitHub Actions runs `ruff check && ruff format --check && pytest tests/ -v --cov=src` on every PR
- LLM live tests are excluded from CI; run manually before release

---

## 8. Boundaries

**Always do:**
- Run `pytest tests/` and `ruff check` before any commit
- Type-hint all new public functions and dataclasses
- Use `structlog` (`log.<event>(**fields)`) for every notable event
- Cite source URL on every news item rendered to the email
- Render the `🤖 AI-generated · not investment advice` chip on every AI Take block
- Use `Decimal` for any monetary or percentage value
- Run `--dry-run` before any real send when changing analyzer or renderer code
- Update this spec when scope or architecture decisions change
- Keep `CLAUDE.md` and `AGENTS.md` byte-for-byte identical — when either is edited, mirror the change to the other in the same commit so Claude Code and Codex always see the same context

**Ask first:**
- Changing the schedule (cron time, frequency, recipient list)
- Adding LLM calls per pipeline run (cost impact)
- Changing model assignments (Haiku ↔ Sonnet ↔ Opus)
- `portfolio.yaml` schema changes (additive vs breaking)
- Adding new external API integrations
- Loosening AI Take fact-check fail-closed behavior
- Adjusting filter thresholds beyond ±20% of current defaults
- Adding new prompt files or substantially restructuring existing ones

**Never do:**
- Commit secrets (API keys, tokens, passwords) — `.env` is gitignored; use `.env.example` for templates
- Hardcode tickers, recipients, ETF holdings, or thresholds in `src/`
- Send an email without the AI disclaimer chip on AI Take blocks
- Allow the AI Take to introduce novel facts not present in the rendered email or exposure map
- Render a recommendation framed as a trade action ("buy", "sell", "increase position")
- Skip the fact-checker pass on AI Take in production (it's fail-closed by design)
- Edit DP_news_scout from this repo — it stays on its own branch in its own repo
- Remove or weaken a failing test without explicit approval

---

## 9. Success Criteria (v0.1 — testable conditions)

**Functional:**
- [ ] `python scripts/run_manual.py --dry-run` completes end-to-end in < 60s without sending
- [ ] `python scripts/run_manual.py --preview` writes valid HTML to `/tmp/preview.html` and opens it in browser
- [ ] Daily email contains all 6 sections in correct order (P&L Scoreboard → Concentrated Exposures → Theme Groups → AI Synthesis → Macro Footer); pixel-style "Theme Groups" each contain cards + news + per-theme AI flash
- [ ] Saturday deep email uses the deep template and includes a week-ahead earnings/macro calendar section
- [ ] Every news item rendered has a clickable source URL
- [ ] Every AI Take block (per-theme flash + bottom synthesis) renders with accent color + `🤖 AI-generated · not investment advice` chip
- [ ] Email word count ≤ 1,000 words on a representative day (validated by automated word-count test in renderer suite)
- [ ] Both `juancho704@gmail.com` and `andrea.aliciap@gmail.com` receive the daily and Saturday emails on schedule

**Correctness:**
- [ ] Exposure map for the current `portfolio.yaml` computes within 1s; output validated by `tests/test_exposure.py`
- [ ] P&L numbers tie out with manual calculation for the test portfolio (within €0.01 rounding)
- [ ] ETF look-through hybrid: when a scraper raises, the resolver falls back to `etf_holdings.yaml` and logs `lookthrough_fallback_used` with the issuer name
- [ ] Fact-checker blocks AI Take when input contains a planted novel fact (test: inject "NVDA acquired AMD" into Sonnet output; assert AI Take section omitted, warning logged)
- [ ] Concentrated Exposures widget shows entities with composite weight ≥ 5%
- [ ] News inclusion: top 15 items OR composite-exposure ≥ 5%, whichever is more

**Operational:**
- [ ] `pytest tests/ -v` passes in < 60s on a clean checkout
- [ ] Coverage: ≥ 80% overall, 100% on `src/exposure/` and `src/pnl/`, ≥ 90% on `src/analyzer/fact_checker.py`
- [ ] Cost-per-run tracked in SQLite (`runs` table with `tokens_in`, `tokens_out`, `cost_usd` per LLM call); queryable via `python scripts/debug_exposure.py --costs`
- [ ] Mon-Fri 07:30 CET cron-job.org trigger fires, GH Actions workflow completes, AgentMail send succeeds, log records `pipeline_complete` with non-empty `email_id`
- [ ] Saturday 08:00 CET trigger uses `--mode=deep` and emits the deep template

---

## 10. Open Questions

- [ ] Exact NewsData.io plan for prod — free + heavy caching may suffice; if not, $20/mo Basic. Settle during the v0.1 NewsData spike.
- [ ] Accent color hex for AI Take — design pass after first render lands
- [ ] AI Take prompt length tuning — iterate after week-1 review when we see real outputs
- [ ] Should `portfolio.yaml` carry historical cost basis per lot (FIFO accounting), or just averaged cost basis per ticker? Snowball owns lot accounting, so v0.1 default is averaged; revisit only if AI Take suggestions need lot-level granularity.

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| NewsData.io entity tagging weak | High | Medium | Build rapidfuzz matcher in v0.1; budget 2-3 hours |
| ETF issuer page format change | Medium | Medium | Hybrid resolver falls back to `etf_holdings.yaml`; weekly refresh script logs failures |
| AI Take hallucination | Medium | High | Hard prompt constraint + Haiku fact-checker; fail-closed; chip + disclaimer |
| News API cost spiral | Low (v0.1) | Medium | v0.1 stays in free tier; v0.3 adds entity-level caching |
| AgentMail rate limit / outage | Low | High | Log + retry once; surface failure to operator via run summary |
| GitHub Actions runner failure | Low | Medium | cron-job.org will retry the dispatch; add manual `workflow_dispatch` fallback |
| Email word-count exceeds budget | Medium (week 1) | Low | Automated word-count assertion in renderer test; tighten thresholds if breached |
| 90s read budget vs maximum scope | Medium | Medium | Per-theme item cap (5 max); tune ranker thresholds in week 1 |

---

## 12. Verification Checklist (before exiting Phase 1)

- [x] Spec covers Objective, Tech Stack, Commands, Project Structure, Code Style, Testing Strategy, Boundaries, Success Criteria, Open Questions
- [x] Success criteria are specific and testable
- [x] Boundaries (Always / Ask first / Never) are defined
- [x] Spec saved to `docs/spec.md`
- [ ] Human has reviewed and approved this spec
