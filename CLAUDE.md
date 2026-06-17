# AndyJuan Personal Portfolio Radar Agent Context

> **Canonical agent context file.** `AGENTS.md` and `.hermes.md` are symlinks
> to this file (`CLAUDE.md`). Edit `CLAUDE.md` directly — never edit the
> other two independently.

## Canonical Docs

- `docs/spec.md` is the source of truth for product behavior and done criteria.
- `docs/plan.md` is the source of truth for implementation order and major
  technical decisions.
- `docs/tasks.md` is the execution checklist for session-sized work.
- If these docs conflict with ad hoc assumptions, follow the docs.

## Product Summary

Build a Python newsletter pipeline that:

- computes direct holdings and ETF look-through exposure
- fetches portfolio-relevant company news plus macro items
- produces a daily morning HTML email and a Saturday deep brief
- labels AI commentary clearly and keeps it grounded in input data

Primary readers are Juan and Andrea. Content is identical for both.

## v0.1 Success Criteria

The intended v0.1 outcome is:

- Mon-Fri daily email at 07:30 CET
- Saturday deep brief at 08:00 CET
- the documented email section flow rendered in order:
  - P&L Scoreboard
  - Concentrated Exposures
  - Theme Groups
  - AI Synthesis + Suggestions
  - Macro Footer
- every news item includes a clickable source URL
- AI blocks render with clear labeling:
  - `🤖 AI-generated · not investment advice`
- total rendered word count stays at or under 1,000 words
- per-run cost is stored and queryable

## Scope Guardrails

Stay inside v0.1 unless the user explicitly asks otherwise.

In scope:

- `portfolio.yaml` as canonical internal holdings format
- Snowball CSV import and merge flow
- hybrid ETF look-through via scrapers plus YAML fallback
- NewsData.io for company news
- RSS feeds for macro
- OpenRouter-backed LLM calls for ranking, flashes, synthesis, and fact-checking
- AgentMail sending
- SQLite-backed local state and cost tracking
- GitHub Actions scheduling path

Out of scope for v0.1 unless explicitly requested:

- SnapTrade live integration
- Binance live integration
- production observability beyond current plan
- speculative new data providers or major architecture rewrites

## Implementation Shape

Important repo areas:

- `config/` for portfolio, ETF fallback holdings, recipients, themes, macro
  feeds, and settings
- `scripts/` for operator workflows such as manual runs, Snowball import,
  ETF refresh, and debug helpers
- `src/portfolio/`, `src/lookthrough/`, `src/exposure/`, `src/pricing/`,
  `src/pnl/`, `src/fetcher/`, `src/entity_match/`, `src/analyzer/`,
  `src/renderer/`, `src/sender/`, `src/pipeline/`, `src/storage/`, `src/utils/`
- `templates/` for email HTML
- `tests/fixtures/` for canned API, scraper, and LLM inputs/outputs

When adding code, keep module boundaries aligned with the plan instead of
smearing logic across unrelated packages.

## Key Plan Decisions

These decisions come from `docs/plan.md` and should be treated as active unless
the user changes them:

- Use `yfinance` for v0.1 pricing.
- EUR is the reporting base currency.
- LLM/API cost tracking is stored in USD and only converted for display if
  needed.
- Multi-theme article rendering uses a primary theme tiebreaker; articles do
  not duplicate across theme sections.
- CI should rely on fixtures and mocks, not live API calls.
- LLM tests should use captured fixture responses after a one-time spike.

## AI and Content Guardrails

- AI commentary must be explicitly labeled.
- AI output should add synthesis, not invent new facts.
- Fact-check flow is fail-closed for novel claims: if the checker rejects an AI
  block, omit that AI section and keep the rest of the email sendable.
- Keep the email concise enough for the 90-second read target.
- Exposure weighting drives relevance; generic market chatter should not crowd
  out portfolio-linked items.

## Working Norms For Agents

- Keep changes narrow, spec-aligned, and phase-aware.
- Prefer extending the planned scaffold over inventing alternate patterns.
- Preserve `CLAUDE.md`, `AGENTS.md`, and `.hermes.md` as exact copies when
  editing any of them → **superseded**: `AGENTS.md` and `.hermes.md` are now
  symlinks to `CLAUDE.md`. Edit `CLAUDE.md` directly only.
- Favor deterministic tests with fixtures, `respx`, and mocked LLM/provider
  clients.
- Do not wire CI or tests to live network dependencies.
- If changing email presentation, preserve Gmail-safe constraints:
  inline-friendly CSS, table-based layout where needed, and compatibility with
  `premailer`.
- If adding config or schema fields, update the relevant docs and fixtures in
  the same change when practical.

## Verification Expectations

Minimum common checks:

```bash
ruff check .
pytest tests/ -v
```

Useful project commands:

```bash
pip install -e ".[dev]"
python scripts/run_manual.py --dry-run
python scripts/run_manual.py --preview
python scripts/import_snowball.py tests/fixtures/snowball-export.csv --dry-run
python scripts/debug_exposure.py
python scripts/refresh_etf_holdings.py
python -m src.main --mode=daily
python -m src.main --mode=deep
```

For targeted work, run the smallest relevant test subset first, then broaden if
the change touches shared infrastructure.

## Default Change Heuristics

- If a request touches behavior, check `docs/spec.md` first.
- If a request touches architecture, sequencing, or tradeoffs, check
  `docs/plan.md`.
- If a request looks like a concrete implementation task, check `docs/tasks.md`
  for the nearest matching unit of work.
- If you notice drift between code and docs, prefer documenting or flagging it
  rather than silently choosing a new direction.

## Cross-Project Context

For durable cross-project learnings, conventions, and decisions, see the
shared memory vault at `/home/hermes/wiki/`. Read `index.md` and `log.md` for
orientation. Project-specific context (above) is separate from vault context.

## Agent Learnings

Agent-learned facts propagated from the shared vault by vaultwatch appear below.
Do not edit this section manually — it is managed by the vaultwatch cron.

-(2026-06-04) [hermes] closed-loop-agent-context-sync — see vault `vault-protocol`
- (2026-06-05) [hermes] agent-context-canonical-convention — see vault `AGENTS.md`
- (2026-06-07) [claude-code] claude-code-notion-mcp-setup — see vault `claude-code-notion-mcp`
- (2026-06-11) [claude-code] snowball-replica-phase-b-shipped — see vault `snowball-replica`
- (2026-06-11) [claude-code] snowball-replica-phase-c-shipped — see vault `snowball-replica`
- (2026-06-12) [claude-code] snowball-replica-phase-d-implemented — see vault `snowball-replica`
- (2026-06-12) [claude-code] incremental-implementation-preference — see vault `juan`
- (2026-06-12) [claude-code] snowball-replica-checkpoint-4-complete — see vault `snowball-replica`
- (2026-06-12) [claude-code] snowball-replica-phase-e-shipped — see vault `snowball-replica`
- (2026-06-12) [claude-code] snowball-replica-phase-f-shipped — see vault `snowball-replica`
- (2026-06-12) [claude-code] gh-watchdog-direct-push-to-pr-branch — see vault `gh-watchdog`
- (2026-06-17) [claude-code] hermes-vm-laptop-launcher — see vault `hermes-desktop-remote-mode`
