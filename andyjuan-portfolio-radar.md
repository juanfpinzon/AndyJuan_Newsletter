# AndyJuan Personal Portfolio Radar

## Problem Statement
How might we deliver a daily morning email to Juan and Andrea that ranks market news
by their actual portfolio exposure (looking through ETFs to top-10 constituents),
reports yesterday's P&L, and adds clearly-labeled AI commentary — in a dark
Binance/IBKR-inspired Gmail-rendered brief that respects a 90-second read budget.

## Recommended Direction
A forked-pipeline (DP_news_scout) HTML email system with two cadences:
- **Mon–Fri 07:30 CET** — daily light: P&L scoreboard, concentrated-exposure widget,
  theme-grouped position cards with per-theme AI flashes, middle-filtered news radar
  with "Affects" badges, bottom AI Synthesis with suggestions, macro footer.
- **Sat 08:00 CET** — deep brief: theme drift, ETF composition changes, FX & rates
  context, week-ahead earnings/macro calendar, longer AI Synthesis.

Substrate: a daily-computed **look-through exposure map** flattening direct holdings +
ETF top-10 holdings into `entity → composite weight + paths`. Drives ranking, the
Concentrated Exposures widget, and the "Affects" badges on news items.

Both readers (Juan + Andrea) receive identical content — single 07:30 CET send.

### Data sources (phased)
- v0.1 — manual `portfolio.yaml`
- v0.2 — SnapTrade API for IBKR positions + daily P&L
- v0.2 — Binance read-only API key (Read Info only, IP-whitelisted) for crypto DCA
- Always — ETF issuer pages for top-10 (iShares, VanEck, SSgA, Global X, Lyxor)
- Always — **NewsData.io** for entity news (free tier dev, ~$20/mo prod)
- Always — RSS for macro (ECB, Fed, FT macro, Reuters macro) — keeps macro off the API meter

### LLM strategy
- **Ranker / news classifier**: Haiku (cheap, fast, single-call per article batch)
- **Per-theme AI flashes**: Sonnet — 1–2 sentences per theme, accent-colored
- **Bottom AI Synthesis + Suggestions**: Sonnet — paragraphs synthesizing across themes
  + actionable suggestions ("Watch X earnings on Wed", "EUR/USD move tilts USD-tracking
  ETFs +1.2%"). Re-evaluate Opus for Saturday only after 4 weeks if Sonnet feels dry.
- **Hard rule**: AI Take blocks may NOT introduce novel facts. Prompt scope = the
  rendered email content + structured exposure map. Synthesis only, no fresh research.

### AI Take visual treatment
- **Accent color** distinct from body text (e.g., muted amber/gold from Binance palette)
- Each AI Take block opens with a chip: `🤖 AI-generated · not investment advice`
- Per-theme flash sits inside the theme group, indented under the news items
- Bottom AI Synthesis is a clearly delimited section (top-bordered card) above the macro footer

### Email design
- Dark Binance/IBKR-inspired CSS: deep navy/charcoal base, green for gains, red for
  losses, muted gold for AI accents and highlights.
- Position cards: ticker, today %, P&L €, expandable footer for ETF top-10 movers.
- Theme groups: Defense · AI/Semis · Precious Metals · EU Banks · US Megacaps · Macro/FX.
- Gmail-tested only.

### Filter thresholds (defaults — tune in week 1)
- News inclusion: top 15 items OR composite-exposure ≥ 5%, whichever is more.
- Per-theme item cap: 5 items max per theme group.
- Concentrated Exposures widget: entities with composite weight ≥ 5%.

## Key Assumptions to Validate
- [ ] **SnapTrade API** gives clean positions + daily P&L for IBKR with stable tokens.
      *Test:* 30-min spike. Hit `/accounts` and `/holdings`. Note token expiry behavior.
- [ ] **Binance read-only API key** flow works end-to-end with IP whitelist.
      *Test:* 1-hour spike. Generate key, fetch `/api/v3/account` and `/sapi/v1/asset/wallet/balance`.
- [ ] **All 8 ETF issuers** publish daily/weekly top-10 holdings free and parseably.
      *Test:* 2-hour spike. One issuer at a time. Note format (CSV/PDF/JSON) per issuer.
- [ ] **NewsData.io** delivers usable entity coverage — 5–15 min lag acceptable, but
      entity tagging may be weaker than ticker-purpose-built APIs.
      *Test:* 2-hour spike. Pull 24h of news against our 70-entity universe. Measure
      what fraction of articles need our own fuzzy-match vs are correctly auto-tagged.
- [ ] **Filter defaults** (top-15 OR ≥5% composite) keep emails ≤ 90s read.
      *Test:* dry-run on 2 weeks of historical news. Measure rendered length. Tune.
- [ ] **Sonnet** for AI Take is rich enough; cheaper Haiku for ranker stays accurate.
      *Test:* 4-week live trial. If AI Take feels dry on Saturday, promote Saturday-only to Opus.
- [ ] **Single 07:30 CET send** satisfies Juan (9:15) and Andrea (8:00).
      *Test:* analytics on open time + ask Andrea after week 2.

## MVP Scope (v0.1 — target 2-week build)
**IN:**
- Manual `portfolio.yaml` (ticker · shares · cost_basis · currency)
- Top-10 ETF look-through, cached weekly from issuer pages
- Look-through exposure map computation
- NewsData.io free tier integration with our own fuzzy-match entity tagging
- Haiku-powered news ranker; Sonnet-powered AI Take (per-theme flashes + bottom synthesis)
- Daily 07:30 CET HTML email to Juan + Andrea
- Section order: P&L scoreboard → Concentrated Exposures → Theme groups (cards + news
  + per-theme AI flash) → AI Synthesis + Suggestions → Macro footer
- AI Take blocks: accent-colored, "🤖 AI-generated · not investment advice" chip
- Dark Binance/IBKR-inspired CSS, Gmail-rendered
- Source citation on every news item

**OUT of v0.1 (phased):**
- SnapTrade live integration → v0.2
- Binance read-only integration → v0.2
- Sparklines (start with text deltas; add inline SVG/CSS bars in v0.2)
- Saturday deep edition → v0.3
- Cost optimization for prod (caching, dedup across entities, RSS-first for macro) → v1.0

## Not Doing (and Why)
- ❌ **Web dashboard / static archive** — email-only, confirmed.
- ❌ **Outlook compatibility** — both readers use Gmail.
- ❌ **Trade actions / rebalancing recommendations** — out of scope; AI Suggestions
       stay informational ("Watch X", "Note Y") with disclaimers.
- ❌ **Real-time intraday alerts** — daily digest is the contract.
- ❌ **Tax/lot-level reporting** — Snowball owns this.
- ❌ **Mobile push / Slack / Telegram** — email channel only.
- ❌ **Crypto market news beyond holdings** — too noisy, low signal.
- ❌ **Snowball outbound integration** — no public API; using SnapTrade + Binance + manual.
- ❌ **Watchlist (companies you don't hold)** — deferred to v2 / probably never.
- ❌ **Two-time-of-day sends** — single 07:30 CET, accept staleness for Juan.
- ❌ **Polygon / Finnhub for v0.1** — start with NewsData.io; only escalate if entity
       coverage proves materially weaker after the spike.

## Open Questions
- [ ] Exact NewsData.io plan for prod — free + heavy caching may suffice; if not, $20/mo
      Basic. Settled during v0.1 spike.
- [ ] How prescriptively to lock down AI Take prompts to prevent novel-fact introduction
      — RAG-only over rendered content vs structured-exposure-map + content. (My lean:
      structured-input prompting with explicit "no novel facts" rule and a fact-checker
      pass that flags any claim not present in input.)

## Risk Watchlist
- **NewsData.io entity tagging weak** → our fuzzy-matcher carries the load; budget 2–3
  hours to build a tight matcher in v0.1.
- **News API cost spiral in prod** → entity-level caching (1 query per entity per day),
  RSS for macro (free), dedup articles across entities.
- **SnapTrade silent disconnect** → daily heartbeat check; email warning if positions
  stale > 24h.
- **ETF issuer page format change** → look-through breaks silently. Add scrape-format
  guard with checksum/validation.
- **AI Take hallucination** → prompt restricts to rendered-content + exposure map only;
  fact-checker pass before render; banner on every block.
- **"Maximum scope + middle aggression + 90s read" is still a triangle.** If v0.1 dry-runs
  exceed 90s, tighten thresholds (top-12 items + ≥6%) before adding complexity.
