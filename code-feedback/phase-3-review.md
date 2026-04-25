# Phase 3 Review — branch `phase3`

**Date:** 2026-04-26
**Reviewer:** Lead Planner/Reviewer (Claude)
**Engineer:** Codex
**Scope:** Tasks 3.0–3.4 per `docs/tasks.md` (LLM analyzer layer)
**Verdict:** **Approve** — all acceptance criteria met, tests green, coverage exceeds spec. A few non-blocking suggestions below.

---

## Verification

| Check | Spec | Result |
|---|---|---|
| Phase 3 tests (`test_ranker`, `test_theme_flash`, `test_synthesis`, `test_fact_checker`) | pass | **16 passed** in 0.92s |
| Full suite `pytest tests/ -v` | no regressions | **79 passed** in 4.36s |
| `ruff check` on Phase 3 files | clean | **All checks passed** |
| Coverage on `src/analyzer/fact_checker.py` (spec: ≥90%) | ≥90% | **100%** (47 stmts, 0 missing) |
| Fixture sets in `tests/fixtures/llm/` | 4 directories, ≥2 scenarios each | ✅ ranker (2), theme_flash (2), synthesis (2), fact_checker (2) |
| Spike spend documented | yes | ✅ `tests/fixtures/llm/spike_report.json` — total **$0.023605 USD** across 8 captures |

---

## Acceptance Criteria — Per Task

### Task 3.0 — LLM spike day ✅
- [x] 4 fixture sets present under `tests/fixtures/llm/{ranker,theme_flash,synthesis,fact_checker}/`
- [x] Each fixture set ships 2 scenarios (input + response + live capture + capture_metadata)
- [x] Total spike spend ($0.0236) documented in `spike_report.json` with per-capture model, tokens, and cost

### Task 3.1 — Ranker (`prompts/news_ranker.md`, `src/analyzer/ranker.py`) ✅
- [x] Jinja-templated prompt parameterized on `news_item_limit` and `exposure_threshold_percent`
- [x] `rank_news(articles, exposure_map) -> list[RankedArticle]` produces structured output
- [x] Threshold rule verified by `threshold_boundary` fixture: BNKE (composite 6%) is included via `included_by="threshold"` despite being outside the top-2 LLM ranking window
- [x] Hallucinated `article_id` rejected (`int(article_id) >= article_count` raises `RankerResponseError`)
- [x] Uses `llm_scoring_model` (Haiku) per cost requirement

### Task 3.2 — Theme flash (`prompts/theme_flash.md`, `src/analyzer/theme_flash.py`) ✅
- [x] Sentence-count enforcement: `count_sentences(text) not in (1, 2)` raises `ThemeFlashFormatError`
- [x] Both 1- and 2-sentence outputs accepted (covered by `ai_semis` and `defense_macro_mix` fixtures)
- [x] Uses `llm_synthesis_model` (Sonnet)
- [x] Prompt explicitly says "Use only the provided article context" + "Do not introduce novel facts" — passes downstream fact-checker validation

### Task 3.3 — Synthesis (`prompts/ai_synthesis.md`, `src/analyzer/synthesis.py`) ✅
- [x] Output is paragraphs ≥3 (`SynthesisFormatError` otherwise)
- [x] Final paragraph must match `\b(?:Watch|Note)\b` (case-insensitive) — verified by `balanced_day` fixture and a negative test
- [x] Cross-theme: prompt receives `theme_flashes_json`, `ranked_articles_json`, and `exposure_map_json`
- [x] No-novel-facts rule confirmed by inclusion of "no novel facts" in prompt + downstream fact-checker pass

### Task 3.4 — Fact-checker (`prompts/fact_checker.md`, `src/analyzer/fact_checker.py`) ✅
- [x] Blocks "NVDA acquired AMD" planted novel fact (`test_filter_ai_take_blocks_planted_novel_fact_and_logs_it` passes; warning log emits `ai_take_blocked` with verbatim flagged claim)
- [x] Passes grounded output (`clean_pass` fixture)
- [x] **Fail-closed** behavior: invalid JSON → `ok=False` with `"Invalid fact-checker response"`; non-mapping payload → same; missing claims with `ok=false` → `"Unverified AI take"` default
- [x] **100%** coverage (exceeds ≥90% spec)

---

## Quality — Five-Axis Review

### Correctness ✅
- Ranker correctly composes the rank-window union with the exposure-threshold floor and de-duplicates via dict lookup
- Sort stability: `(-llm_score, -composite_weight, published_at, title)` is deterministic
- Fact-checker is genuinely fail-closed across all malformed-payload paths
- All tuple/Decimal fields in dataclasses are immutable (`frozen=True`)

### Readability & Simplicity ✅
- `_prompting.py` is a tight 74-line helper module with three orthogonal utilities (render, sentence/paragraph split, JSON-with-fences parse). Earns its complexity.
- Public API per module is small (1–2 functions + 1 dataclass + 1 error). No speculative abstractions.
- Naming is consistent: `*FormatError`, `*ResponseError`, `generate_*`, `*_json` prompt vars.

### Architecture ✅
- Clean dependency direction: `analyzer/*` → `config`, `fetcher.models`, `exposure.models`, `utils.{llm,log}`. No cycles.
- Dependency-injection seam (`llm_caller` parameter) on every analyzer function makes fixture-based testing trivial — the right design choice for an LLM-backed module.
- Prompt files in `prompts/` cleanly separated from code.

### Security ✅
- Jinja env uses `autoescape=False` — acceptable here because outputs go to LLMs, not HTML. `StrictUndefined` prevents silent template typos.
- No PII or secrets in prompts; no shell exec; no user input rendered without serialization.
- LLM responses parsed defensively (typed coercion in `_parse_ranking_response`, fail-closed in fact-checker).

### Performance ✅
- Each analyzer makes a single LLM call. No N+1.
- Token caps on every call (`MAX_RANKER_TOKENS=1200`, `MAX_THEME_FLASH_TOKENS=300`, `MAX_SYNTHESIS_TOKENS=700`, `MAX_FACT_CHECK_TOKENS=400`) — prevents runaway spend.
- JSON serialization uses `sort_keys=True` where determinism matters (ranker, exposure map) — good for prompt-cache hits.

---

## Suggestions (non-blocking)

### Optional: Out-of-scope change to `src/__init__.py`
**File:** `src/__init__.py`

The diff removes the eager submodule import block. Task 0.1's literal verification (`from src import portfolio, lookthrough, ...`) still passes because Python's import system resolves submodules on demand, but `import src; src.analyzer` no longer works after this change.

```python
# Before
from . import (analyzer, entity_match, exposure, ...)
__all__ = [...]

# After
__all__ = [...]   # eager imports removed
```

This is a reasonable cleanup (avoids paying analyzer's transitive import cost on every `import src`), but it is **orthogonal to Phase 3** and should ideally have shipped as a separate commit. Per Karpathy's "surgical changes" guideline: every changed line should trace to the user's request. Not a regression — flagging for hygiene.

### Optional: `LLMCaller` type alias duplicated 4×
**Files:** `ranker.py:41`, `theme_flash.py:29`, `synthesis.py:32`, `fact_checker.py:26`

Same definition (`Callable[[str, str, int, str | None], LLMResponse]`) appears in all four analyzer modules. Consider hoisting to `_prompting.py` (or a new `_types.py`):

```python
# in src/analyzer/_prompting.py
LLMCaller = Callable[[str, str, int, str | None], LLMResponse]
```

Trivial future maintenance win. Skip if you prefer keeping each module standalone-readable.

### Optional: Synthesis prompt-vs-validator drift
**File:** `prompts/ai_synthesis.md:7` vs. `src/analyzer/synthesis.py:19`

The prompt says *"must include at least one **sentence starting with** 'Watch' or 'Note'"* but the validator regex (`\b(?:Watch|Note)\b`, `IGNORECASE`) accepts the keyword anywhere in the final paragraph. The looser check matches the task's acceptance criterion ("contains at least one suggestion"), so this is functional, but the prompt over-promises relative to what the code enforces. Either tighten the regex (e.g., `^(?:Watch|Note)\b` per sentence) or relax the prompt to "must contain 'Watch' or 'Note'".

### Optional: Decimal-as-percent serialization is noisy
**Files:** `ranker.py:147,162`, `synthesis.py:103,119`

`str(Decimal('0.04') * 100)` produces `"4.00"` — fine, but in real exposure data (with paths' weights summed from many sources), the result can have 20+ trailing zeros, polluting the prompt. Consider `(weight * 100).quantize(Decimal('0.01'))` for prompt readability. Token cost impact: negligible, but cleaner.

### FYI: `synthesis._serialize_exposure_map` vs. `ranker._serialize_exposure_map` are not identical
**Files:** `ranker.py:153–168` vs. `synthesis.py:110–125`

`ranker` defensively wraps `Decimal(str(path["weight"]))` before multiplying; `synthesis` assumes `path["weight"]` is already a Decimal. Both are correct given current callers (the resolver always populates Decimal weights), but the divergence is a small consistency wart. If extracted to a shared helper later, pick one approach.

### FYI: `settings.yaml` has keys not declared in `Settings`
**Files:** `config/settings.yaml`, `src/config.py`

`theme_item_cap`, `daily_send_time_cet`, `deep_brief_send_time_cet`, `deep_brief_day`, `ai_commentary_enabled` are present in YAML but not in the `Settings` dataclass. The loader silently ignores them (only `fields(Settings)` are read). Likely intentional placeholders for Phases 4–6. No Phase 3 impact — just noting for future task work.

---

## Dead Code Check
None identified. All new modules are wired through `src/analyzer/__init__.py` and exercised by tests.

---

## Verdict

**Approve.**

Phase 3 implementation cleanly satisfies every acceptance criterion in `docs/tasks.md`:

- 4 LLM fixtures captured with documented spend
- Ranker honors both top-N and exposure-threshold inclusion rules
- Theme flash enforces 1–2 sentence shape
- Synthesis enforces 3+ paragraphs with a "Watch/Note" suggestion
- Fact-checker is fail-closed, blocks the planted "NVDA acquired AMD" novel fact, and hits 100% coverage

The dependency-injection seam on every analyzer function is the right design — it enables fixture-only test runs, fast CI, and zero live-API exposure (per D5/D7). Code is small, readable, and free of speculative abstraction.

Once the optional items above are addressed (or explicitly deferred), the branch is ready to merge into main and unblock Phase 4 (renderer).

### Before merge
- [x] Verify `pytest tests/ -v` is green on a clean checkout (79 passed)
- [x] Verify `ruff check` is clean
- [x] Verify fact-checker coverage ≥ 90% (actual: 100%)
- [ ] Decide on the `src/__init__.py` change — keep as-is or split into a separate commit
- [ ] (Optional) Apply the three minor cleanups above

### Phase 3 checkpoint sign-off
- [x] All 4 LLM fixtures captured and tests pass
- [x] Fact-checker blocks the planted "NVDA acquired AMD" novel fact
- [x] Spike-day spend documented ($0.023605)
- [x] Reviewer approval recorded (this document)
