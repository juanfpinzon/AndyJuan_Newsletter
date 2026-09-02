# Daily Radar Outage — Diagnosis & Fix Plan

**Status:** ✅ RESOLVED 2026-09-02 — see [§0 Resolution](#0-resolution-what-actually-happened) before reading further.
**Date of diagnosis:** 2026-09-02
**Scope:** Restore the AndyJuan Newsletter daily radar to full production operation.

> ⚠️ **The diagnosis below (§2) is partly incorrect and is retained for history.**
> §1–§8 record the original plan as written. §0 records what the evidence
> actually showed and what shipped. Where they disagree, §0 is authoritative.

---

## 0. Resolution — what actually happened

Shipped in [#28](https://github.com/juanfpinzon/AndyJuan_Newsletter/pull/28) (→ `dev`) and [#29](https://github.com/juanfpinzon/AndyJuan_Newsletter/pull/29) (→ `main`), 2026-09-02.

### Correction 1 — the 401 was not an auth failure at the positions call

§2.2 and §7.B attribute the Jul 22–27 401 to `_fetch_account_positions` (line 203) and conclude that SnapTrade auth broke. The Jul 22 run log (29893964700) shows the failure one frame deeper:

```
snaptrade_client.py:77   get_positions        → _map_position(...)
snaptrade_client.py:251  _map_position        → _fx_rate_to_eur(currency)
snaptrade_client.py:288  _fx_rate_to_eur      → reference_data.get_currency_exchange_rate_pair(...)
paths/currencies_rates_currency_pair/get.py:303 → ApiException (401)
```

**Positions fetched successfully and auth was working.** Only SnapTrade's currency-rates endpoint returned 401.

### Correction 2 — pinning to 11.0.212 would have fixed nothing

SnapTrade retired the currency-rates endpoint around 2026-07-21 and removed it from the SDK entirely in 13.x. Verified by package introspection:

| | 11.0.195 | 13.0.13 |
|---|---|---|
| `paths/currencies_rates_currency_pair` | present | **removed** |
| `reference_data` currency methods | `get_currency_exchange_rate_pair` | none (`get_stock_exchanges` only) |

The endpoint is dead server-side regardless of client version, so §3 Phase 1's pin-first strategy could not have restored live positions. **Risk #1 in §6 is not a risk — it is what happened.** The yfinance FX swap that §3 Phase 4 defers as an optional follow-up is the actual fix.

### Correction 3 — §4.1 names the wrong auth mode

Phase 4.1 prescribes `SnapTradeAuth.personal_api_key(...)`. Per the SDK's per-endpoint security schemes:

```
commercialApiKey: [PartnerClientId, PartnerTimestamp, userId, userSecret]
personalApiKey:   [PersonalClientId, PersonalTimestamp]
```

Every `account_information` call in this client passes `user_id`/`user_secret`, and the working pre-outage client signed with `PartnerClientId`. **`commercial_api_key` is correct**; `personal_api_key` would drop the user credentials and 401.

### Gaps the plan did not cover

- **`dev` was 8 commits *behind* `main`**, not ahead — hotfix PRs #25/#27 were based on `main` directly. §3 Phase 0 branches off `dev`, which would have tested code that was not production. `dev` was synced first.
- **Actions always runs `main`.** `repository_dispatch` uses the default branch, so `dev` was never exercised in production.
- **`get_daily_pnl` had two further escapes** past the `SnapTradeError` guard in `_load_snaptrade_daily_pnl`: a bare `KeyError` on a missing prior close, and a `ValueError` from the price fetch.
- **An all-skipped FX result must raise, not return `[]`.** §3 Phase 1.3 asks for a fail-soft skip, but `merge_positions(include_missing_canonical=False)` treats the live snapshot as authoritative — an empty "success" would silently wipe the portfolio.
- **The existing SnapTrade tests stubbed the retired endpoint.** Once it was removed the stub became dead code and the tests silently hit the live network, violating the repo's no-network-in-CI rule. They now stub yfinance.

### What shipped

- Pin `snaptrade-python-sdk==13.0.13` (the unpinned float is the original sin — §2.1 is correct on this).
- `_build_sdk`: `SnapTradeAuth.commercial_api_key` on SDK ≥ 12, legacy kwargs fallback below.
- `_fx_rate_to_eur`: yfinance `EUR{CCY}=X` via `src/pricing/fetch_fx_rate_to_eur`, same "units per EUR" semantics.
- `_sdk_boundary`: every SDK entry point re-raises as `SnapTradeError`. **This is the real fix** — §2.3 correctly identifies it as the root cause.
- Fail-soft on partial FX loss, raise on total loss.
- Broadened the loader and daily-P&L guards to `except Exception`.

### Verification

| Path | Run | Result |
|---|---|---|
| `workflow_dispatch` on fix branch | 33618962789 | ✅ 1m55s, live positions, no fallback |
| `workflow_dispatch` on `main` | 33622148117 | ✅ 1m34s, real `juan_only` send |
| `repository_dispatch` on `main` | 33622683857 | ✅ 1m50s, live positions |
| cron-job.org dispatch | 33623651098 | ✅ 1m38s |

First green scheduled runs since 2026-07-21. `ruff` clean, 172 tests pass.

**Layer 3 (§2.4) confirmed:** the cron-job.org GitHub PAT had expired. Both jobs re-credentialed with a classic PAT carrying the `repo` scope. Note §3 Phase 3.4 suggests "Contents: read" for a fine-grained token — GitHub does not publish fine-grained permissions for this endpoint; the documented requirement is the classic `repo` scope. A missing `Bearer ` prefix produces the same 401 as an expired token.

### Not done

- **Phase 4 (SDK 13.x migration)** — folded into this fix, since Phase 1 alone could not work.
- **Phase 5 (ops hardening)** — still open. See `docs/tasks.md` § Post-v0.1 Priorities.
- **Fact-checker rejecting every AI block** — discovered during verification, now the top open priority. See `docs/tasks.md`.

---

## 1. Executive Summary

The Daily Radar has been failing since **2026-07-22** and has produced **zero dispatches since 2026-07-27** — the last newsletter email Juan received dates from before that. The outage has **three independent failure layers**, which is why it looks "stuck": fixing any one of them alone would not bring the radar back.

| # | Layer | What happened | Fix effort |
|---|-------|---------------|-----------|
| 1 | **SnapTrade SDK breaking change** | Upstream `snaptrade-python-sdk` 11.0.213 → 12.0.0 (Jul 21–22) rewrote the SDK's auth model. Our dependency is **unpinned**, so CI silently picked up the new release overnight. | Medium — pin now, migrate to 13.x later |
| 2 | **Fail-soft fallback never engaged** | The loader catches `SnapTradeError`, but the SDK raises raw `snaptrade_client.exceptions.ApiException` / `TypeError`, which are NOT `SnapTradeError` subclasses. The documented "falls back to portfolio.yaml" safety net did not fire, so a SnapTrade failure killed the whole pipeline. | Small — exception wrapping at the SDK boundary |
| 3 | **cron-job.org trigger stopped** | Last `repository_dispatch` received **Jul 27**; nothing since. The external scheduler stopped calling GitHub. Needs manual login to cron-job.org to inspect. | Manual, ~5 min (Juan) |

**Recommended approach:** Pin the SDK to the last-known-good version **and** fix the exception wrapping (unblock production immediately — layers 1+2), then restore the trigger (layer 3). Migrate to SDK 13.x only as a separate, later PR.

---

## 2. Diagnosis Detail (evidence)

### 2.1 Failure timeline

```
Jul 16–21            CI green, daily radar delivers (runs 1m41s–2m1s)
Jul 21 11:58 UTC     PyPI: snaptrade-python-sdk 11.0.213 released
                     (the Jul 21 05:30 run predates it — still on 11.0.212)
Jul 22 05:30 UTC     FIRST FAILURE — SnapTrade 401 "Authentication
                     credentials were not provided." (run 29893964700)
Jul 22–27            6 consecutive failures, same 401 signature
Jul 27 05:30 UTC     Last repository_dispatch EVER received (run 30239933768)
Jul 27 → today       Zero dispatches — scheduler-side failure begins
Sep 02 (today)       Manual workflow_dispatch dry run confirms breakage
                     persists on SDK 13.0.13 with a NEW signature (B)
```

**Key fact:** The repo made **zero commits** between the last green run (Jul 21) and the first failure (Jul 22) — the trigger was dependency drift, not our code. Every CI run does a fresh `pip install`, and the unpinned `snaptrade-python-sdk` floated forward.

### 2.2 Two failure signatures

**Signature A (Jul 22–27 runs, SDK 11.0.213/12.0.0):**
```
snaptrade_client.exceptions.ApiException: (401)
HTTP response body: {'detail': 'Authentication credentials were not provided.',
                     'status_code': 401, 'code': '0000'}
```
Raised from `src/portfolio/snaptrade_client.py:203` (`_fetch_account_positions`).

**Signature B (today, SDK 13.0.13):**
```
TypeError: SnapTrade.__init__() missing 1 required keyword-only argument: 'auth'
```
Raised from `_build_sdk` at `src/portfolio/snaptrade_client.py:314`. The failure now happens **at client construction**, before any API call. SDK 12+/13 requires `SnapTrade(auth=SnapTradeAuth.personal_api_key(...))` instead of `SnapTrade(client_id=..., consumer_key=...)`.

### 2.3 Why the fail-soft fallback did not fire (root cause of the crash)

`src/portfolio/loader.py:140-146` is:

```python
try:
    snaptrade_client = SnapTradeClient(settings.snaptrade, logger=logger)
    live_positions = snaptrade_client.get_positions()
except SnapTradeError as exc:
    # → cached/YAML fallback, log `snaptrade_fallback_used`, radar keeps running
```

But the exceptions actually raised were `snaptrade_client.exceptions.ApiException` (Signature A) and `TypeError` (Signature B) — **neither is a `SnapTradeError` subclass**. The try/except passed the crash straight through and killed the whole pipeline.

The existing test (`tests/test_portfolio.py:344`, `FailingSnapTradeClient`) only ever raises `SnapTradeError` itself — a blind spot. The test proves the fallback works for the failure mode it simulates; production leaked a different one.

`src/portfolio/snaptrade_client.py` never imports or wraps ANY SDK exception. This is a class-level gap at the SDK boundary, not a single call-site bug.

### 2.4 Why the trigger stopped (Jul 27)

Runs stop entirely after Jul 27 05:30 UTC — a failure mode the repo has no visibility into, because the scheduler is an external cron-job.org account (per `docs/spec.md:83`). The acceptance criterion in `docs/spec.md:443` ("Mon-Fri 07:30 CET cron-job.org trigger fires") has been silently violated for over a month. Nothing in the repo or on the Hermes VM dispatches the trigger.

**Top hypothesis: the GitHub PAT stored in the cron-job.org job config expired ~Jul 27.** Fine-grained PATs have a max 1-year lifetime; a PAT created around Jul 2025 would expire exactly when dispatches stopped. Alternatives: job paused/purged (free accounts purge idle jobs), account plan lapse, or cron-job.org outage. Only inspectable in the cron-job.org UI — needs Juan.

### 2.5 Additional code gaps found during diagnosis (fix opportunistically)

Not part of restoring the radar, but discovered while tracing — listed so they don't get lost:

1. **FX method gone in 13.x:** `reference_data.get_currency_exchange_rate_pair` no longer exists in SDK 13.x (verified by introspection). Our `_fx_rate_to_eur` (`snaptrade_client.py:288`) calls it. Any 13.x migration must replace it — `src/pricing/yfinance_client.py` already fetches FX pairs (`_fx_symbol`, e.g. `EURUSD=X`) for the whole portfolio, so a yfinance fallback is natural.
2. **Endpoint signatures survive in 13.x:** `get_all_account_positions` / `get_account_balance_history` keep the same parameters (`account_id`, `user_id`, `user_secret`) in 13.x. The migration surface is therefore mainly: (a) `SnapTrade.__init__(auth=...)`, (b) exception wrapping, (c) FX replacement.
3. **`config/settings.yaml` has `snaptrade.enabled: false`** — this local default doesn't affect CI (`daily-radar.yml` sets `SNAPTRADE_ENABLED: "true"`), and it's why the PR-CI dry runs stayed green during the outage: `ci.yml`'s `run-radar` job never sets `SNAPTRADE_ENABLED`, so PR CI runs YAML-only mode and never touches SnapTrade. Worth a comment in the yaml so future readers don't trip on it.
4. **`merge_positions` drop-behavior:** on the live-success path, YAML-only positions are dropped (`include_missing_canonical=False`, `loader.py:167`). The fallback merge keeps all YAML positions. Fine as designed, but relevant if we ever extend the cache TTL.
5. **The morning-brief knew all along:** the Hermes VM morning brief has reported "CI Daily Radar FAILED" every day since Jul 27 (see `memories/JOURNAL.md`), but there is no escalation rule — the alert was always reported and never escalated. This outage class (5 weeks silent) is what Phase 5 fixes.

### 2.6 What is confirmed working

- GitHub repo + all 10 secrets present (OPENROUTER, NEWSDATA, AGENTMAIL x2, EMAIL_FROM, SNAPTRADE x5 — updated Apr/Jun 2026)
- `gh` CLI from this VM has admin on `juanfpinzon/AndyJuan_Newsletter`
- `workflow_dispatch` manual trigger works (used today for the repro)
- Fixture-backed CI jobs (`digest-check`) pass — no test debt from the outage
- Local repo clean; `main` aligned with `origin/main` @ 62aa633
- PR CI (`ci.yml`) is green — it doesn't exercise SnapTrade (see §2.5.3)

---

## 3. The Fix Plan

**Guiding decisions:**
- **Pin-first strategy:** restore production today with a known-good pin + the exception-wrapping guarantee; migrate to 13.x in a later PR. Never mix "unblock" and "migrate" in one change.
- **Fix the exception wrapping regardless of the pin.** The wrapping is the real fix: it converts "SnapTrade down" into "radar runs degraded on YAML/cached positions". The pin is a best-guess unblock; the wrapping is the guarantee.
- **Trigger restoration needs Juan** (cron-job.org login). Offer a VM-based scheduler as the alternative that removes the external dependency permanently.
- **PR base = `dev`** (repo convention: feature/fix PRs target `dev`; releases go `dev` → `main`).

### Phase 0 — Branch setup (Hermes, 2 min)

1. `git fetch origin && git checkout -b fix/snaptrade-sdk-pin-and-fallback origin/dev`

### Phase 1 — Immediate unblock: pin + wrap (Hermes, ~1.5 h)

**Goal:** the next scheduled run completes — with live positions if SnapTrade works, degraded-but-alive if it doesn't.

1. **Pin `snaptrade-python-sdk==11.0.212`** in `pyproject.toml` (last-known-good: all Jul 16–21 green runs installed it; released Jun 30, before the 12.0.0 auth rewrite line began).
2. **Wrap SDK exceptions at the boundary** in `src/portfolio/snaptrade_client.py`:
   - Catch `ApiException` (and `TypeError`/generic `Exception` at construction) in `_build_sdk`, `_fetch_account_positions`, `_historical_pnl`, and `_fx_rate_to_eur`; re-raise as `SnapTradeError` with the original reason preserved (`SnapTradeError(f"snaptrade api error: {exc}")`).
   - This is a class-fix at the SDK boundary, not scattered try/excepts at downstream call sites. After this, every SnapTrade failure — auth, network, malformed response, missing SDK method — surfaces as `SnapTradeError`, and the loader's existing fallback fires.
3. **FX resilience inside `_map_position`:** if the FX rate can't be fetched for a position's currency, skip that position with a logged warning (`snaptrade_position_skipped_fx`) instead of crashing — consistent with the existing fail-soft philosophy of PR #27.

### Phase 2 — Tests (Hermes, ~45 min)

1. **Raw-API-exception fallback test:** a fake client whose SDK layer raises `ApiException`-equivalent → loader falls back, emits `snaptrade_fallback_used`. This reproduces the Jul 22–27 production failure and makes it impossible to regress.
2. **Construction-failure fallback test:** client constructor raises `TypeError` (today's Signature B) → same fallback.
3. **FX-skip test:** FX rate unavailable → position skipped with warning, pipeline completes.
4. `ruff check .` + `pytest tests/ -v` green locally.
5. PR → `dev`; CI green (all three jobs); merge.
6. Release PR `dev` → `main`; merge after CI green.
7. **Manual verification:** `workflow_dispatch` dry run (`juan_only=true`, `dry_run=true`) → pipeline completes with either live positions or `snaptrade_fallback_used` in the log tail. Then one `--dry-run=false, juan_only=true` run to verify the AgentMail send path end-to-end before re-enabling the schedule.

### Phase 3 — Restore the trigger (Juan, ~5-10 min manual)

**Not automatable from this VM** — cron-job.org is an external web account only Juan can log into.

1. Log in to cron-job.org → find the two jobs (Mon–Fri 07:30 + Sat 08:00, timezone Europe/Madrid).
2. Check each job's **execution history**: last success/failure dates, enabled/paused status, and the auth header's PAT.
3. Most likely causes, in order: (a) stored GitHub PAT expired (matches the Jul 27 hard stop), (b) job paused or purged by the free plan, (c) account/plan lapse.
4. Fix per cause: regenerate a PAT with `repo` scope (classic) or a fine-grained PAT with **Contents: read** permission on `juanfpinzon/AndyJuan_Newsletter` (repository_dispatch requires contents read; verify exact scope against GitHub docs at fix time), paste into the job's headers, re-enable, and hit "run now".
5. **Verify:** the test dispatch appears in `gh run list` and completes green.

**Decision point — if you prefer, skip cron-job.org entirely and move the scheduler to the VM (Phase 3-alt). Recommended if the PAT is expired anyway** — one less external account, VM-side logs, and built-in alerting:

1. Hermes cron job (script-only, `no_agent`), dispatching via the VM's existing `gh` auth — no new PAT anywhere:
   - Daily: schedule both 05:30 and 06:30 UTC; script checks the Europe/Madrid local time and a `last-dispatch` state file, so exactly one dispatch fires at 07:30 Madrid year-round (DST-proof without cron timezone math).
   - Deep brief: same pattern for Sat 08:00 Madrid.
   - State file: `/home/hermes/.hermes/state/radar-dispatch-state.json`; failures (non-2xx POST) deliver an immediate Telegram alert to Juan (chat 7451469865).
2. If we do this: update `README.md` Operations section + `docs/spec.md:83` so docs match reality, and delete/disable the cron-job.org jobs.

### Phase 4 — SDK 13.x migration (optional follow-up, ~2-3 h, separate PR)

Only after production is stable ≥1 week on the pin:

1. `SnapTrade(auth=SnapTradeAuth.personal_api_key(consumer_key=..., client_id=...))` — the 12+/13 auth model.
2. Positions/balance-history calls keep the same signatures — mostly wiring changes.
3. Replace `_fx_rate_to_eur`'s SnapTrade FX call (gone in 13.x) with yfinance FX pairs via `src/pricing/yfinance_client.py`'s approach.
4. **Pin the exact version** (e.g. `13.0.13`) — the unpinned float is the original sin here. Note the 13.x line releases fast (13 releases in 3 weeks), so even pinned 13.x needs deliberate manual bumps.
5. Same fallback tests must pass on 13.x. PR → `dev` → CI green → merge → release to `main`.

### Phase 5 — Ops hardening (small, separate PR, ~1 h)

So a 5-week silent outage can never happen again:

1. **Escalation rule:** the VM morning brief already reports CI status; add: same CI failure ≥3 consecutive days → direct Telegram alert to Juan (not just a journal line).
2. **Silent-trigger-death detector:** VM-side script: if no `repository_dispatch` run appears in the repo within 24h of the last expected window → Telegram alert. This detects exactly the failure class the repo itself cannot see (§2.4).
3. **Optional repo-side:** a failed scheduled run could auto-create a GitHub issue — decide during implementation which surface(s) we want; don't build all of them.

---

## 4. Task Breakdown / Execution Order

| # | Task | Owner | Est. |
|---|------|-------|------|
| 0.1 | Create fix branch off `origin/dev` | Hermes | 2 min |
| 1.1 | Pin `snaptrade-python-sdk==11.0.212` in `pyproject.toml` | Hermes | 5 min |
| 1.2 | Wrap SDK exceptions → `SnapTradeError` at the boundary (init, positions, history, FX) | Hermes | 45 min |
| 1.3 | FX-unavailable → skip position with logged warning | Hermes | 20 min |
| 1.4 | Tests: raw-exception fallback, construction-failure fallback, FX-skip | Hermes | 40 min |
| 1.5 | `ruff check .` + `pytest tests/ -v` green | Hermes | 5 min |
| 1.6 | PR → `dev`, CI green, merge | Hermes | 15 min |
| 1.7 | Release PR `dev` → `main`, merge after green | Hermes | 10 min |
| 1.8 | Manual verification: dry run completes (fallback or live) + one `juan_only` real send | Hermes | 15 min |
| 3.1 | cron-job.org: inspect job status + history, identify why dispatches stopped | **Juan** | 5 min |
| 3.2 | Fix per cause (re-enable / regenerate PAT) — or approve Phase 3-alt VM scheduler | Juan (+Hermes) | 10 min |
| 3.3 | Verify test dispatch appears in `gh run list` and completes green | both | 5 min |
| 3.4 | Verify next scheduled run completes and the email lands in Juan's inbox | both | 5 min |
| 4.1 | *(Optional, later)* SDK 13.x migration PR (auth model, yfinance FX, exact pin, tests) | Hermes | 2-3 h |
| 5.1 | *(Optional)* Escalation rule: persistent CI failure → Telegram alert | Hermes | 30 min |
| 5.2 | *(Optional)* Silent-trigger-death detector (24h no-dispatch → alert) | Hermes | 30 min |

**Critical path: Phase 1 → Phase 2 → Phase 3.** Phases 4–5 are optional hardening, sequenced after production is stable.

**Time to first restored email: ~2 h Hermes + ~10 min Juan — same day / next morning.**

---

## 5. Verification checklist (production restored = all green)

- [ ] `ruff check .` green
- [ ] `pytest tests/ -v` green (incl. the 3 new fallback tests)
- [ ] Fix PR CI green (all 3 jobs) on `dev`
- [ ] Release merged to `main`
- [ ] Manual dry run completes: live positions OR `snaptrade_fallback_used` in log tail
- [ ] Manual `juan_only` real run: email arrives via AgentMail
- [ ] cron-job.org (or VM scheduler) test dispatch appears in `gh run list`
- [ ] Next scheduled run (07:30 Madrid) completes green
- [ ] Newsletter email delivered to Juan's inbox
- [ ] Morning brief reports "Daily Radar: green" the next day

---

## 6. Risks & Open Questions

**Risks:**
1. **Server-side deprecation:** pinning the client SDK doesn't control SnapTrade's server. The Jul 22–27 401s might be a server-side auth change affecting ALL SDK versions — in which case the pin restores nothing and live positions stay broken. **Mitigation: Phase 1.2 (exception wrapping) is the real guarantee** — worst case the radar runs degraded on YAML/cached positions and the emails still go out. We'll know within one run whether the pin restored live data.
2. **AgentMail credentials** (last rotated Apr 2026): if they lapsed, the send step fails even with a green pipeline. No current evidence of trouble (no runs reached the send step since Jul 27). Covered by the Phase 1.8 manual real-send verification.
3. **NewsData.io free tier** (200 req/day): if the plan lapsed, sends still work but content is thin. Low risk; watch the first restored run's log.
4. **cron-job.org may be unrecoverable** (lost login, purged account) → Phase 3-alt (VM scheduler) is the designed fallback; no timeline risk since Hermes can build it same-day.

**Open questions for Juan (decisions needed before/at execution):**
1. Pin-first (restore today, migrate later) vs. straight-to-13.x migration? **Recommend: pin first.**
2. Do you still have cron-job.org login access? (Determines Phase 3 vs 3-alt.)
3. If the PAT is expired anyway, move scheduling to the VM permanently? **Recommend: yes — one less external dependency, plus alerting.**
4. 13.x migration this cycle or defer? **Recommend: defer until production is stable 1 week.**

---

## 7. Evidence Appendix

### A. Run history (`gh run list --workflow daily-radar.yml`, Sep 2)

```
Jul 16–21   success (1m41s–2m1s)     repository_dispatch
Jul 22–27   failure (37s–50s) x6     repository_dispatch  ← SnapTrade 401
Jul 27 → today: NO RUNS AT ALL      ← trigger death
Sep 02      failure (34s)           workflow_dispatch (manual repro, SDK 13.0.13)
```

### B. Jul 27 run log (30239933768) — key excerpt

```
File "…/src/portfolio/snaptrade_client.py", line 203, in _fetch_account_positions
snaptrade_client.exceptions.ApiException: (401)
HTTP response body: {'detail': 'Authentication credentials were not provided.',
                     'status_code': 401, 'code': '0000'}
##[error]Process completed with exit code 1.
```

### C. Today's dry run (33615598457, SDK 13.0.13) — key excerpt

```
File "…/src/portfolio/snaptrade_client.py", line 314, in _build_sdk
    return SnapTrade(
TypeError: SnapTrade.__init__() missing 1 required keyword-only argument: 'auth'
```

### D. PyPI release timeline (snaptrade-python-sdk)

```
2026-06-30  11.0.212   ← last-known-good (all Jul 16–21 green runs used it)
2026-07-21  11.0.213   ← released 11:58 UTC, after that day's green 05:30 run
2026-07-22  12.0.0     ← auth-model rewrite; first CI failure same morning
2026-07-24  12.0.1
2026-07-27  12.0.2 / 12.0.3
2026-07-30  12.0.4
(… 13.0.13 current, Aug 31)
```

### E. Code path references

- `src/portfolio/loader.py:140-146` — `except SnapTradeError` (the catch that failed to catch the real exceptions)
- `src/portfolio/snaptrade_client.py:300-317` — `_build_sdk` (constructs `SnapTrade(client_id=..., consumer_key=...)`; breaks on SDK ≥12)
- `src/portfolio/snaptrade_client.py:202-215` — `_fetch_account_positions` (ApiException source, Signature A)
- `src/portfolio/snaptrade_client.py:283-297` — `_fx_rate_to_eur` (calls `get_currency_exchange_rate_pair`, gone in 13.x)
- `src/pipeline/daily.py:308-328` — `_load_snaptrade_daily_pnl` (secondary consumer; also catches only `SnapTradeError`)
- `tests/test_portfolio.py:344-364` — fallback test that only simulates `SnapTradeError` (the blind spot)
- `pyproject.toml:27` — `"snaptrade-python-sdk"` unpinned (the original sin)
- `docs/spec.md:83` — cron-job.org → repository_dispatch architecture
- `README.md:48-95` — Operations section (cron-job.org schedule + dispatch body)

---

## 8. Next Actions

1. **Juan reviews this plan** — especially §6 open questions. Recommended calls: pin first, fix/replace cron-job.org, defer 13.x.
2. On approval, Hermes executes Phases 0–2 (branch → pin → wrap → tests → PRs → manual verification).
3. Juan does Phase 3 (cron-job.org inspection, ~5 min) or approves Phase 3-alt (VM scheduler).
4. Verify the next scheduled run lands green and the email arrives.
5. Optional phases (4, 5) after production is stable.

---

*Diagnosed and written by Hermes, 2026-09-02. No repo changes made during diagnosis.*