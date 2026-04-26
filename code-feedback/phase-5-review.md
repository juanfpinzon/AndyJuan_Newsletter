# Phase 5 Review — Sender + Pipeline Orchestration

**Reviewer:** Lead Planner/Reviewer (worktree: `phase5`)
**Date:** 2026-04-26
**Scope:** Tasks 5.1–5.4 from `docs/tasks.md`
**Verdict:** **Approve with minor suggestions** — Phase 5 acceptance criteria are met. No blocking issues.

---

## 1. Verification Summary

| Check | Result |
|---|---|
| `pytest tests/test_sender.py tests/test_pipeline_daily.py tests/test_pipeline_deep.py tests/test_run_manual.py tests/test_main.py -v` | **15/15 passed** (1.73s) |
| `pytest tests/` (full suite, regression) | **111/111 passed** (4.93s) |
| `ruff check` on all Phase 5 files | **clean** |
| Mutually-exclusive flag combos error | confirmed via `test_run_manual_rejects_*` |
| `runs` table persists `mode`, `status`, `recipient_count`, `tokens_in`, `tokens_out`, `cost_usd` | confirmed in `test_run_daily_orchestrates_and_persists_run_metadata` |
| Fact-check failure path omits AI Take, still sends email | confirmed in `test_run_daily_omits_ai_take_when_fact_check_blocks_it` |
| `data-section="week-ahead"` rendered in deep mode | confirmed in `test_run_deep_uses_deep_template_and_week_ahead_items` |

---

## 2. Acceptance Criteria — Task by Task

### Task 5.1 — `src/sender/agentmail.py` ✅
- Sends HTML + plain-text via `inboxes.messages.send` with `headers={"From": from_addr}`. ✅
- Returns `SendResult(message_id=...)`; logs `email_sent` event with message id + recipients. ✅
- `EmailSendError` raised on any AgentMail SDK exception (verified by `test_send_email_wraps_agentmail_errors`). ✅
- Inbox id resolved from kwarg → `AGENTMAIL_INBOX_ID` env; missing key raises `EmailSendError`. ✅

### Task 5.2 — `src/pipeline/daily.py` ✅
- `run_daily(send: bool = True)` orchestrates the full pipeline (positions → lookthrough → exposure → prices → P&L → news → macro → matcher → ranker → theme flashes → synthesis → fact-check → render → send). ✅
- Fact-check failure path: `_filter_theme_flashes` and `_filter_synthesis` drop AI content; the rest of the email still ships. ✅
- Run metadata written to `runs` table with `started_at`, `completed_at`, `status` (`running` → `success`/`failed`), `error`, `recipient_count`, `tokens_in`, `tokens_out`, `cost_usd`. ✅ Cost summary uses an `id > baseline` window over `llm_calls` — clean and correct.
- Failure path: outer `try/except` updates the run row to `status="failed"` with the exception message, then re-raises. ✅

### Task 5.3 — `src/pipeline/deep.py` ✅
- Thin delegate to `run_daily(mode="deep", week_ahead_items=...)`. ✅
- Saturday template + week-ahead block confirmed in test output. ✅
- See **Architecture finding A4** below regarding scope vs. spec wording.

### Task 5.4 — `src/main.py` + `scripts/run_manual.py` ✅
- Production `python -m src.main --mode={daily|deep}` works. ✅
- Operator `scripts/run_manual.py` supports `--dry-run`, `--preview`, `--test-email`, `--reuse-seen-db`, `--ignore-seen-db`, `--mode={daily|deep}`. ✅
- Mutually-exclusive group for `{--dry-run, --preview, --test-email}`; explicit conflict rejection for `--reuse-seen-db + --ignore-seen-db`. ✅
- Subprocess-based smoke tests for flag combos via the `ANDYJUAN_PIPELINE_STUB_CAPTURE` injection — clean isolation, no real I/O in CI. ✅

---

## 3. Five-Axis Review

### 3.1 Correctness

**Strengths**
- The `run_id` lifecycle is sound: insert with `status="running"`, capture `llm_call_baseline` *before* execution, update on success/failure with usage delta. This guarantees no row leaks from a panicked run.
- `_resolve_now()` is consistently re-evaluated for `started_at` and `completed_at`, so wall-clock measurement is correct.
- The double-render pattern (`rendered_factual` → fact-check → `rendered_email`) is the right shape for a fact-checker that needs the rendered body as ground truth, with the second render reflecting the redacted AI content. ✅
- `_filter_synthesis` returns `synthesis.paragraphs` only when `filter_ai_take` returns non-`None`. Currently safe because `filter_ai_take` either returns the verbatim text or `None` (never a partial redaction). See **Optional finding C1**.

**Findings**
- **(Nit) C1 — Coupling between `_filter_synthesis` and `filter_ai_take`'s contract.** `_filter_synthesis` ignores the returned `filtered_text` and uses `synthesis.paragraphs` directly. This is correct *today* (filter is binary: pass-through or `None`), but if the contract ever evolves to redact-and-return, the redaction would be silently dropped. Either:
  - Add a one-line comment in `_filter_synthesis` documenting the assumption, **or**
  - Rebuild paragraphs from the filtered text when filtering becomes non-trivial.
  Cheap to address now; very hard to debug if it regresses.
- **(Nit) C2 — `runs` row is updated with `recipient_count=0` when `send=False`.** Spec accepts this, but a successful `--dry-run` will look identical to a no-op send in metrics. Consider persisting the *resolved* recipient count regardless of send, or adding a `dry_run` boolean column. Optional.

### 3.2 Readability & Simplicity

**Strengths**
- `daily.py` reads top-down: public entry point → async core → small focused helpers. Helpers are pure (`_build_news_queries`, `_build_position_rows`, `_format_*`).
- `_PipelineState` and `PipelineResult` separate "internal pipeline output" from "public return shape" — good boundary.

**Findings**
- **(Nit) R1 — `daily.py` is ~700 LOC and pulls 30+ symbols from across `src/`.** The orchestrator's job is to *be* a wiring layer, so this is largely unavoidable, but the run-table helpers (`_insert_run_start`, `_update_run`, `_last_llm_call_id`, `_summarize_llm_usage_since`) feel like they belong in `src/storage/runs.py`. Would let `daily.py` focus on pipeline glue. Optional.
- **(Nit) R2 — `PORTFOLIO_MARKET_SYMBOLS` is hardcoded in `daily.py`** (lines 46–55). It's portfolio config, not pipeline logic. Consider moving to `config/portfolio.yaml` (per-position `market_symbol` field) or `config/settings.yaml`. As is, swapping a position requires a code change, which contradicts the YAML-driven portfolio approach.
- **(Nit) R3 — `tests/test_pipeline_deep.py` imports private helpers from `tests/test_pipeline_daily.py`** (`_async_return`, `_StubMacroRSSReader`, `_StubMatcher`, `_StubNewsDataClient`, `_fake_*`). Test-to-test imports create fragile coupling. Move shared stubs into `tests/conftest.py` or a `tests/_pipeline_helpers.py` module. Optional but standard hygiene.

### 3.3 Architecture

**Strengths**
- Pipeline orchestrator is async-aware at the right boundary: `run_daily` is sync; it calls `asyncio.run(_run_pipeline_async(...))` once. Sub-tasks (lookthrough, NewsData, macro RSS) are async-native and composed naturally inside.
- `scripts/run_manual.py` uses an env-var-driven runner stub (`ANDYJUAN_PIPELINE_STUB_CAPTURE`) so subprocess tests don't have to monkey-patch the real pipeline. Clean separation between CLI wiring and pipeline behavior.

**Findings**
- **(Important) A1 — `--dry-run` end-to-end <60s is not exercised in CI.** Spec acceptance: "`--dry-run` end-to-end completes < 60s". Tests only verify the CLI wiring via the stub runner; the *real* pipeline (live yfinance, NewsData, OpenRouter, AgentMail mocked or skipped) isn't timed. This is a Phase 5 checkpoint item ("`python scripts/run_manual.py --dry-run` completes < 60s"); please run it manually before signing off the checkpoint.
- **(Optional/Consider) A2 — Run-table writers re-open the DB four times per run.** `_insert_run_start`, `_last_llm_call_id`, `_summarize_llm_usage_since`, and `_update_run` each call `init_db(db_path)`. Each call does `open → check schema → ensure columns`. Negligible at scale (single-digit ms), but caching the `Database` object once in `run_daily` and threading it through is cheap and reduces ambiguity about idempotency.
- **(Optional) A3 — `_build_news_queries` hardcodes `NOISE_NEWS_QUERY_TERMS = {"GOLD", "SILVER"}`.** This is a workaround for noisy precious-metals exposure entities surfacing as news queries. Reasonable, but it should be either:
  - documented in a code comment with the rationale, or
  - lifted into `config/settings.yaml` as `news.noise_query_terms` so it's reviewable without a code change.
- **(Optional) A4 — `pipeline/deep.py` is a 5-line delegate.** Spec wording: *"Mostly reuses daily.py; swaps template, fetches week-ahead calendar (likely from a separate prompt or static config), uses the longer synthesis prompt variant if any."* Current implementation: only swaps `mode="deep"` and forwards `week_ahead_items` from the caller. This is fine if the team's intent is "operator/cron supplies the week-ahead items"; but if the spec's "fetches week-ahead calendar" implied an internal fetcher, this is a partial implementation. **Please confirm intent** — probably worth a 1-line ADR if simplification is deliberate.

### 3.4 Security

**Findings — none blocking.**
- No secrets in source. `OPENROUTER_API_KEY`, `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID`, `EMAIL_FROM`, `NEWSDATA_API_KEY` all read via `os.getenv`. ✅
- `EmailSendError` is the single boundary for AgentMail SDK exceptions — prevents leaking SDK internals to callers. ✅
- `# noqa: BLE001` on the broad `except Exception` in `run_daily` is justified (the pattern is "always update run row before re-raising"). It does re-raise, so no silent swallow. ✅
- `# noqa: BLE001` in `agentmail.py` is similarly justified — heterogeneous SDK errors funneled into one typed exception.
- `recipients_path` and `themes_path` are `Path | str`, both read via `yaml.safe_load`. ✅ No `yaml.load`, no shell expansion. ✅
- `webbrowser.open(preview_path.as_uri())` in `run_manual.py` opens a local `file://` URL — no remote URL injection risk.

### 3.5 Performance

**Findings — none blocking.**
- Double-render is necessary; cost is ~1ms each on canned data.
- News queries are bounded by `MAX_NEWS_QUERY_TERMS = 6`. ✅
- `_fetch_news_batches` deduplicates by URL across queries — avoids reprocessing. ✅
- LLM cost summary is a single SQL aggregate over `id > baseline` — efficient. ✅

---

## 4. Karpathy-Lens Notes

| Guideline | Observation |
|---|---|
| **Surface assumptions** | `_filter_synthesis` quietly assumes `filter_ai_take` is binary (pass-through or `None`). Document or restructure. (See C1.) |
| **Simplicity first** | `pipeline/deep.py` is appropriately minimal. `daily.py` is necessarily large but stays linear; no premature abstraction. |
| **Surgical changes** | Phase 5 work is concentrated in the 5 spec'd files. Collateral edits to `src/pricing/yfinance_client.py` (added `market_symbols`), `src/fetcher/newsdata.py` (added `load_cached_articles`, `ignore_seen_db`), `src/fetcher/macro_rss.py` (added `hours`/`now` kwargs), and `src/storage/schemas.py` (added `recipient_count`, `tokens_in`, `tokens_out` to `runs`; backfill columns to `articles_seen`) are all *direct dependencies* of the orchestrator's API needs. Acceptable scope. **Worth flagging in the commit message.** |
| **Goal-driven execution** | Verification steps ran clean. Acceptance bullets traced 1:1 to tests. |

---

## 5. Punch List (Author Action)

### Required before checkpoint sign-off
1. **Run `python scripts/run_manual.py --dry-run` in a real environment and confirm <60s.** (Spec acceptance, not currently in CI.)
2. **Run `python scripts/run_manual.py --test-email <addr>` against AgentMail** and confirm the email lands. (Spec checkpoint.)
3. **Run `python scripts/run_manual.py --mode=deep --dry-run`** and confirm the Saturday template renders. (Spec checkpoint.)

### Recommended (not blocking)
4. **A4** — Confirm the `pipeline/deep.py` simplification (no internal week-ahead fetcher) is deliberate; if so, add `docs/adr/0002-saturday-deep-week-ahead-source.md` describing where `week_ahead_items` comes from.
5. **R2** — Move `PORTFOLIO_MARKET_SYMBOLS` from `src/pipeline/daily.py` to YAML config.
6. **C1** — Add a one-line comment in `_filter_synthesis` documenting the binary contract assumption with `filter_ai_take`.

### Optional (nice-to-have)
7. **R1** — Extract `runs`-table helpers from `daily.py` into `src/storage/runs.py`.
8. **R3** — Move shared test stubs into a `tests/conftest.py` or `tests/_pipeline_helpers.py` to avoid `tests/test_pipeline_deep.py` importing from `tests/test_pipeline_daily.py`.
9. **A2** — Cache `Database` once in `run_daily` instead of re-opening per run-table operation.
10. **A3** — Promote `NOISE_NEWS_QUERY_TERMS` to `config/settings.yaml`.

---

## 6. Verdict

**Approve.** Phase 5 implementation meets the task acceptance criteria, all 111 tests pass with clean ruff, the run/cost lifecycle is correctly persisted, and the fact-check failure path is properly handled. The findings above are predominantly Nits and Optionals; the only **Important** item (A1) is a manual operational verification that belongs to the Phase 5 checkpoint, not the code itself.

Once items 1–3 in the punch list are confirmed against real services, Phase 5 is ready to merge into `main` and proceed to Phase 6.
