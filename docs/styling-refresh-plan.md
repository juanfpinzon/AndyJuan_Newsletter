# Daily Portfolio Radar — Style Refresh Plan (v0.1)

**Audience:** Codex (coding partner). Follow this top-to-bottom; every change is scoped, paste-ready, and addresses a specific defect visible in `code-feedback/Gmail29-04-26.pdf`.

**Touch only this file:** `templates/daily_email.html.j2`. (`templates/saturday_deep.html.j2` extends it; no separate edits required.)

**Goal:** Modern, dense-but-breathable financial brief. Keep the existing palette. Fix the visual hierarchy. Kill the broken Macro Footer.

---

## 0. Ground rules (read before editing)

1. **This is an email, not a webpage.** Gmail strips `<head><style>` in some forwarding paths; we rely on `premailer` to inline CSS. Stick to inline-friendly properties:
   - **Allowed:** padding, margin, color, background, border, border-radius, font-*, line-height, table layout, `display:inline-block` on spans.
   - **Avoid:** `display:flex`, `display:grid`, CSS variables, `gap` on tables, `position:absolute`, `@supports`, `clip-path`, web fonts loaded by `<link>` (Gmail strips them).
2. **Layout = tables.** Always wrap multi-column rows in `<table role="presentation" cellspacing="0" cellpadding="0" width="100%">`. Use `<td width="...">` for column widths. Never rely on percent widths that don't add up to 100.
3. **Keep the palette.** Do not introduce new hues. The full token list is in §1. If you need a new shade, derive it by adjusting the alpha of an existing color over `#0b0f19`.
4. **Keep behaviour intact.** Do not change Jinja variable names (`total_pnl.daily_pnl_eur`, `position_rows`, `concentrated_exposures`, `theme_groups`, `macro_items`, etc.). Renderer code in `src/renderer/render.py` stays untouched. If a new visual element needs new data, **stop and ask** — do not silently invent fields.
5. **Verification after every section** (see §11). Run `python scripts/run_manual.py --preview` and visually compare to the PDF. The preview must still open in the browser without errors.

---

## 1. Design tokens (the only colors you may use)

These already exist in the file. Memorize them; do not invent new ones.

| Token | Hex | Use |
|---|---|---|
| `bg-page` | `#0b0f19` | Outermost shell |
| `bg-shell-grad-top` | `#111827` | Top of shell gradient |
| `bg-panel` | `#131a2a` | Section panel surface |
| `bg-panel-2` | `#0f1524` | Inner card surface (one tier deeper) |
| `bg-panel-3` | `#101726` → `#0d1320` | Theme-group wrap gradient |
| `border-soft` | `#202b40` | Default 1px border |
| `border-mid` | `#222c42` | Panel border |
| `border-strong` | `#32405d` | Chip border (interactive look) |
| `border-divider` | `#1d2740` | Theme-wrap border |
| `text-primary` | `#ffffff` | Numbers, headings, ticker |
| `text-body` | `#e6edf7` | Default body |
| `text-secondary` | `#d5deed` | Card body copy |
| `text-muted` | `#8b9bb8` | Eyebrow / secondary metadata |
| `text-muted-2` | `#aebbd2` | Theme description |
| `text-muted-3` | `#b7c2d9` | Subtitle / inline label |
| `accent-gold` | `#f3ba2f` | Brand accent (used sparingly) |
| `pos-green` | `#0ecb81` | Positive P&L |
| `neg-red` | `#f6465d` | Negative P&L |
| `accent-soft-bg` | `rgba(243, 186, 47, 0.08)` | AI Take backdrop |

**New rule:** percentages and EUR amounts that carry a sign **must** be wrapped in a span tinted by sign. Currently all numbers render in white — Codex must fix this in §3 and §5.

---

## 2. Typography refresh (5 minutes)

**Why:** Arial-only stack looks 2008. We add a modern system stack and tabular numerics so the `€2,741.78` columns line up.

**Where:** `templates/daily_email.html.j2`, `<style>` block.

**Replace** the current `body` rule (around line 11):

```css
body {
  margin: 0;
  padding: 0;
  background: #0b0f19;
  color: #e6edf7;
  font-family: Arial, Helvetica, sans-serif;
}
```

**With:**

```css
body {
  margin: 0;
  padding: 0;
  background: #0b0f19;
  color: #e6edf7;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
```

Then add `class="num"` to every element that prints a number (metric values, table cells with EUR/%, mini-card values, exposure weights). See §3 and §5 for exact locations.

**Verify:** preview in browser; numbers in the P&L table align in vertical columns even with mixed widths.

---

## 3. Hero (top section) — small polish

**Why:** It's not broken, but the gold "Daily" chip floats lonely below the subtitle. Tighten spacing, give the eyebrow more breathing room, and add a subtle horizontal rule to separate hero from the body.

**Where:** lines ~194–199 in the template.

**Replace:**

```html
<section class="panel section" data-section="hero">
  <div class="eyebrow">Portfolio Radar · {{ generated_for_date }}</div>
  <h1 class="title">{{ title }}</h1>
  <p class="subtitle">{{ subtitle }}</p>
  <div class="mode-chip">{{ mode_label }}</div>
</section>
```

**With:**

```html
<section class="panel section" data-section="hero" style="padding:32px 28px;">
  <div class="eyebrow" style="color:#f3ba2f;">Portfolio Radar · {{ generated_for_date }}</div>
  <h1 class="title" style="margin:14px 0 6px;letter-spacing:-0.01em;">{{ title }}</h1>
  <p class="subtitle">{{ subtitle }}</p>
  <div style="margin-top:18px;display:inline-block;padding:6px 14px;background:rgba(243,186,47,0.12);border:1px solid rgba(243,186,47,0.35);border-radius:999px;color:#f3ba2f;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
    {{ mode_label }}
  </div>
</section>
```

What changed:
- Eyebrow now uses `accent-gold` so the brand color leads the page.
- Title gets a tiny negative letter-spacing — feels editorial, not corporate.
- Mode chip gains tinted gold background (vs. pure dark) for stronger anchor.

---

## 4. Section header pattern (do this once, applies to all)

**Why:** Every section currently starts with the same gray eyebrow. Real products use a small "label + thin divider" pattern to signal a fresh region without yelling.

**Add** a new helper macro near the top of the file (right under the `ai_disclaimer_chip` macro at line 1):

```jinja
{% macro section_header(label, accent='#8b9bb8') -%}
<table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="margin-bottom:16px;">
  <tr>
    <td style="white-space:nowrap;padding-right:12px;color:{{ accent }};font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;">{{ label }}</td>
    <td style="width:100%;border-top:1px solid #1d2740;height:1px;"></td>
  </tr>
</table>
{%- endmacro %}
```

Then **replace every** `<div class="eyebrow">…</div>` that opens a `<section>` with `{{ section_header("PnL Scoreboard") }}`, etc.

Sections to swap (exact label text — keep current capitalization):
- `PnL Scoreboard` (line ~202)
- `Concentrated Exposures` (line ~260)
- `Theme Groups` (line ~282)
- `AI Synthesis` (line ~337)
- `Macro Footer` (line ~351) — **but** keep the new label `Macro & Markets` (see §8)
- `Week Ahead` (in saturday_deep template — leave alone, it inherits the macro)

Do **not** replace the inner eyebrows on metric cards (`Current Value`, `Total PnL`, etc.); those keep the small gray label.

---

## 5. PnL Scoreboard — color-code signs, polish table

### 5a. Metric tiles (the four big numbers)

**Why:** All four values render white. The viewer can't tell at a glance whether `Daily PnL` is up or down.

**Where:** lines ~204–232.

**Replace the four `<td>` blocks** with this pattern. Codex: use the helper below for each tile, passing the right label/value/sign.

```jinja
{% macro metric_tile(label, value, sub=None, sign='neutral') -%}
{# sign in {'pos','neg','neutral'} -> color the value #}
{% set color = '#0ecb81' if sign == 'pos' else ('#f6465d' if sign == 'neg' else '#ffffff') %}
<div class="metric" style="padding:20px 22px;">
  <div class="eyebrow">{{ label }}</div>
  <p class="metric-value num" style="color:{{ color }};">{{ value }}</p>
  {% if sub %}<div class="muted num" style="margin-top:6px;">{{ sub }}</div>{% endif %}
</div>
{%- endmacro %}
```

Place this macro at the top of the file with the other macros.

Then replace lines ~203–233 with:

```jinja
<table class="score-grid" role="presentation" cellspacing="0" cellpadding="0" width="100%" style="border-collapse:separate;border-spacing:12px;margin:0 -12px;">
  <tr>
    <td style="width:50%;">
      {{ metric_tile('Current Value', total_pnl.current_value_total_eur) }}
    </td>
    <td style="width:50%;">
      {{ metric_tile('Total PnL', total_pnl.total_pnl_eur, sub=total_pnl.total_pnl_pct, sign=total_pnl.total_pnl_sign) }}
    </td>
  </tr>
  <tr>
    <td style="width:50%;">
      {{ metric_tile('Daily PnL', total_pnl.daily_pnl_eur, sign=total_pnl.daily_pnl_sign) }}
    </td>
    <td style="width:50%;">
      {{ metric_tile('Tracked Positions', position_rows|length|string) }}
    </td>
  </tr>
</table>
```

> ⚠️ **Data dependency:** `total_pnl.total_pnl_sign` and `total_pnl.daily_pnl_sign` do not exist yet. Codex: **stop and ask the user** before adding `_sign` fields to the renderer. If the user says no, replace the `sign=…` arg with a Jinja inline check that parses the value (`'neg' if value.startswith('-') or value.startswith('€-') else 'pos'`). Either is fine; do not invent fields silently.

Switch `border-collapse:separate;border-spacing:12px;margin:0 -12px;` gives the four tiles real gutters without `display:flex`.

### 5b. Position table — tighten and color-code

**Why:** Currently every cell is white text on dark. P&L percentages should hint at performance.

**Where:** lines ~235–256.

Add new helpers near the top of `<style>`:

```css
.cell-mono {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
.row-zebra:nth-child(even) td {
  background: rgba(255,255,255,0.015);
}
```

(Premailer will inline most of this; `:nth-child` survives in Gmail web but not all clients — it's a progressive enhancement, harmless if dropped.)

Replace the table body loop with:

```jinja
<tbody>
  {% for row in position_rows %}
  <tr class="row-zebra">
    <td style="color:#ffffff;font-weight:700;">{{ row.ticker }}</td>
    <td class="muted">{{ row.theme }}</td>
    <td class="cell-mono">{{ row.current_value_eur }}</td>
    <td class="cell-mono" style="color:{% if row.total_pnl_pct.startswith('-') %}#f6465d{% elif row.total_pnl_pct.startswith('+') and row.total_pnl_pct != '+0.0%' %}#0ecb81{% else %}#8b9bb8{% endif %};">{{ row.total_pnl_pct }}</td>
    <td class="cell-mono" style="color:{% if row.daily_change_pct.startswith('-') %}#f6465d{% elif row.daily_change_pct.startswith('+') and row.daily_change_pct != '+0.0%' %}#0ecb81{% else %}#8b9bb8{% endif %};">{{ row.daily_change_pct }}</td>
  </tr>
  {% endfor %}
</tbody>
```

Note: the renderer (`_format_percent`) always emits `+` or `-`, so string-prefix check is safe.

---

## 6. Concentrated Exposures — give it a visual

**Why:** A 2-row table for the most important data on the page is wasteful. Add a horizontal "weight bar" so the reader sees concentration without reading.

**Where:** lines ~259–279.

**Replace** the entire section's `<table>` with:

```jinja
<section class="panel section" data-section="concentrated-exposures">
  {{ section_header("Concentrated Exposures") }}
  <table role="presentation" cellspacing="0" cellpadding="0" width="100%">
    {% for row in concentrated_exposures %}
    {# row.composite_weight_percent looks like '+18.43%' — strip sign and % to get a number for the bar width.
       Cap visual width at 30% portfolio weight (above that, just max out the bar). #}
    {% set raw = row.composite_weight_percent.lstrip('+').rstrip('%') %}
    {% set pct = raw|float %}
    {% set bar_width = ([pct, 30.0]|min / 30.0 * 100)|round(1) %}
    <tr>
      <td style="padding:14px 0;border-bottom:1px solid #202b40;">
        <table role="presentation" cellspacing="0" cellpadding="0" width="100%">
          <tr>
            <td style="width:80px;color:#ffffff;font-weight:700;font-size:14px;">{{ row.entity }}</td>
            <td style="padding:0 14px;">
              <div style="height:8px;background:#0f1524;border:1px solid #202b40;border-radius:999px;overflow:hidden;">
                <div style="width:{{ bar_width }}%;height:8px;background:linear-gradient(90deg, #f3ba2f 0%, #f6c04a 100%);border-radius:999px;"></div>
              </div>
            </td>
            <td class="num" style="width:80px;text-align:right;color:#ffffff;font-weight:700;font-size:14px;">{{ row.composite_weight_percent }}</td>
            <td class="muted num" style="width:80px;text-align:right;font-size:12px;">{{ row.path_count }} path{% if row.path_count != 1 %}s{% endif %}</td>
          </tr>
        </table>
      </td>
    </tr>
    {% endfor %}
  </table>
</section>
```

Behaviour notes:
- **30% cap** is a reasonable visual ceiling for portfolio composite weights. If a future entity exceeds 30%, the bar pegs and the number still reads exact. Don't add overflow indicators — the percent on the right is the source of truth.
- The bar uses a gentle gradient from `accent-gold` to a 7%-lighter shade — pure flat looked dead in tests.
- Headings (`Entity / Composite Weight / Paths`) are removed — the layout is now self-describing. (Senior-engineer review: don't print a header row of three columns when each row already shows what each cell is.)

---

## 7. Theme Groups — restructure cards and articles

This section has three sub-fixes.

### 7a. Theme card grid — fix the squeeze

**Why:** With 4 tickers in a single `<tr>` (Precious Metals row in the PDF), each card collapses to ~140px and the labels wrap (`Total / -8.4% / Daily / -1.5%` stacked).

**Rule:** **Max 3 cards per row.** If there are more, wrap to the next row. Keep card width at 33% on desktop, 100% on mobile.

**Where:** lines ~292–305.

**Replace** the `<table class="card-grid">…</table>` with this batched-row pattern:

```jinja
<table class="card-grid" role="presentation" cellspacing="0" cellpadding="0" width="100%" style="margin-top:16px;border-collapse:separate;border-spacing:10px;margin-left:-10px;margin-right:-10px;">
  {% set card_rows = group.cards|batch(3) %}
  {% for chunk in card_rows %}
  <tr>
    {% for card in chunk %}
    <td style="width:33.33%;vertical-align:top;">
      <div class="mini-card" style="padding:16px 18px;">
        <div class="eyebrow" style="color:#f3ba2f;">{{ card.ticker }}</div>
        <div class="num" style="margin-top:10px;color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.01em;">{{ card.current_value_eur }}</div>
        <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="margin-top:10px;">
          <tr>
            <td class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Total</td>
            <td class="num" style="text-align:right;font-size:13px;font-weight:600;color:{% if card.total_pnl_pct.startswith('-') %}#f6465d{% elif card.total_pnl_pct == '+0.0%' %}#8b9bb8{% else %}#0ecb81{% endif %};">{{ card.total_pnl_pct }}</td>
          </tr>
          <tr>
            <td class="muted" style="font-size:11px;text-transform:uppercase;letter-spacing:0.06em;padding-top:4px;">Daily</td>
            <td class="num" style="text-align:right;font-size:13px;font-weight:600;padding-top:4px;color:{% if card.daily_change_pct.startswith('-') %}#f6465d{% elif card.daily_change_pct == '+0.0%' %}#8b9bb8{% else %}#0ecb81{% endif %};">{{ card.daily_change_pct }}</td>
          </tr>
        </table>
      </div>
    </td>
    {% endfor %}
    {# pad short rows so the last row's cards don't stretch to fill #}
    {% for _ in range(3 - chunk|length) %}
    <td style="width:33.33%;"></td>
    {% endfor %}
  </tr>
  {% endfor %}
</table>
```

What changed:
- Uses Jinja's `|batch(3)` filter to wrap to a new `<tr>` after 3 cards.
- Pads the last row with empty `<td>` so 4 → 3+1, the lone card stays at 33% (not stretched).
- "Total" / "Daily" labels and values sit on the same line via inner table; this kills the 4-line stacked text.
- Sign coloring is now applied.
- Ticker label switches to gold for stronger identity.

### 7b. Theme group heading

**Why:** Currently `<h2>` has no visual relationship to the cards below. Add a thin gold accent bar.

**Where:** lines ~285–290.

**Replace:**

```html
<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
  <div>
    <h2 style="margin:0;color:#ffffff;font-size:22px;">{{ group.name }}</h2>
    <p style="margin:8px 0 0;color:#aebbd2;font-size:14px;line-height:1.6;">{{ group.description }}</p>
  </div>
</div>
```

**With** (no flex — pure block flow):

```html
<div style="border-left:3px solid #f3ba2f;padding-left:14px;margin-bottom:6px;">
  <h2 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;letter-spacing:-0.01em;">{{ group.name }}</h2>
  <p style="margin:6px 0 0;color:#aebbd2;font-size:13px;line-height:1.55;">{{ group.description }}</p>
</div>
```

### 7c. Article cards — tighten the metadata

**Why:** Each article spends 3 lines on metadata: `SOURCE · TIME` / `Primary entity: NVDA …` / `Affects US Megacaps`. That repeats N times per theme — visual debt.

**Where:** lines ~314–330.

**Replace** the article loop with:

```jinja
{% for article in group.articles %}
<div class="article-card news-item" style="padding:14px 18px;">
  <div class="eyebrow">{{ article.source }} · {{ article.published_at_label }}</div>
  <h3 style="margin:6px 0 10px;font-size:16px;line-height:1.45;font-weight:600;">
    <a href="{{ article.href }}" style="color:#ffffff;text-decoration:none;border-bottom:1px solid transparent;">{{ article.title }}</a>
  </h3>
  <div style="font-size:12px;line-height:1.5;color:#8b9bb8;">
    <span style="display:inline-block;padding:3px 8px;background:rgba(243,186,47,0.10);border:1px solid rgba(243,186,47,0.35);border-radius:6px;color:#f3ba2f;font-weight:700;font-size:11px;letter-spacing:0.04em;margin-right:8px;">{{ article.primary_entity }}</span>
    <span class="num" style="color:#d5deed;">{{ article.composite_weight_percent }}</span>
    <span style="color:#52617f;"> · </span>
    {% if article.affects_themes %}
      {% for theme in article.affects_themes %}
      <span style="color:#aebbd2;">{{ theme }}{% if not loop.last %}, {% endif %}</span>
      {% endfor %}
    {% endif %}
  </div>
</div>
{% endfor %}
```

What changed:
- Title font drops to 16px (was 18px) — less shouty.
- "Primary entity:" label is **gone**; the ticker now lives in a small gold-tinted chip — instantly readable.
- "Affects" labels collapse into a comma-separated list on the same line.
- Total metadata height drops from 3 lines to 1 line.

---

## 8. Macro Footer — full rewrite (the worst offender)

**Why this looks broken in the PDF:** the current code is

```jinja
<table class="macro-grid" …>
  <tr>
    {% for item in macro_items %}
    <td style="width:50%;…">
    …
```

When 8 items each get `width:50%` in a single `<tr>`, the browser distributes width proportionally — each cell gets ~12% of the container, and the headlines wrap to one or two words per line. That's the column-collapse you see in the PDF.

**Fix:** chunk items into rows of 4 with `|batch`, like §7a. Also drop the eyebrow rename and rebrand it.

**Where:** lines ~350–375.

**Replace the entire `<section data-section="macro-footer">` block with:**

```jinja
<section class="panel section" data-section="macro-footer" style="padding:24px 22px 18px;">
  {{ section_header("Macro & Markets", accent='#f3ba2f') }}
  {% if macro_items %}
  <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="border-collapse:separate;border-spacing:10px;margin:0 -10px;">
    {% set macro_rows = macro_items|batch(2) %}
    {% for chunk in macro_rows %}
    <tr>
      {% for item in chunk %}
      <td style="width:50%;vertical-align:top;">
        <div style="padding:16px 18px;background:#0f1524;border:1px solid #202b40;border-radius:14px;">
          <div class="eyebrow" style="font-size:10px;color:#8b9bb8;">{{ item.source }} · {{ item.published_at_label }}</div>
          <a href="{{ item.href }}" style="display:block;margin-top:8px;color:#ffffff;text-decoration:none;font-size:14px;font-weight:600;line-height:1.45;">{{ item.title }}</a>
        </div>
      </td>
      {% endfor %}
      {% for _ in range(2 - chunk|length) %}
      <td style="width:50%;"></td>
      {% endfor %}
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="footer-note" style="margin:12px 0 0;">No fresh macro items cleared the last 24h window.</p>
  {% endif %}
  <p class="footer-note" style="margin:18px 0 0;padding-top:14px;border-top:1px solid #1d2740;">
    Generated for {{ generated_for_date }}. Review source links before acting on any market-moving information.
  </p>
</section>
```

What changed:
- **2 columns × N rows** instead of N × 1 row. Each card now has ~440px on desktop and never collapses.
- Eyebrow source label drops to 10px, more `text-muted`. Headlines breathe.
- Padding/typography matches the article cards above for consistency.
- Footer disclaimer gets a 1px top divider — visually closes the email.
- Section title becomes **"Macro & Markets"** (more descriptive than "Macro Footer", which is a code-name not a UI label).

> 💡 **Why batch-by-2 instead of batch-by-3 or 4?** With 8 items typical, 4×2 looks balanced and each card has enough width for a 2-line headline (~70 chars). A 3-column layout pushes cards to ~290px and wraps headlines to 4 lines.

---

## 9. Mobile responsive — additions

**Where:** the `@media only screen and (max-width: 640px)` block (line ~170).

**Add inside the existing media query:**

```css
@media only screen and (max-width: 640px) {
  .container { padding: 16px 10px 28px; }
  .section { padding: 18px 16px; }
  .title { font-size: 26px; }
  .metric-value { font-size: 24px; }
  .table th, .table td { padding-left: 0; padding-right: 0; }

  /* New: collapse 3-card and 2-card grids to single column on phones */
  .card-grid td,
  .macro-grid td,
  .score-grid td {
    display: block !important;
    width: 100% !important;
    padding: 6px 0 !important;
  }
  .score-grid {
    border-spacing: 0 !important;
    margin: 0 !important;
  }
  /* Concentrated exposures: keep ticker + bar inline, drop "paths" col */
  .conc-paths { display: none !important; }
}
```

If you add the `conc-paths` hide rule, also add `class="conc-paths"` to the path-count `<td>` in §6.

> ⚠️ Gmail mobile webview ignores `!important` inconsistently. Test on a real Gmail iOS app before declaring done.

---

## 10. Accessibility quick-pass

These are cheap wins; do them all.

1. **`alt` on images:** none present today; if you add any, every `<img>` must have `alt=""` (decorative) or descriptive text.
2. **Link contrast:** the gold `#f3ba2f` on `#0b0f19` is ~9:1 — passes AA. Headlines use white on `#0f1524` (~17:1) — also fine. Don't drop below `#aebbd2` for any user-readable text.
3. **`<table role="presentation">`** is already on every layout table — keep it; it tells screen readers "this is layout, not data."
4. **Real data tables** (the position table in §5b and the `Week Ahead` table in saturday template) **must not** have `role="presentation"`. They already don't — leave alone.
5. **Email subject preview text:** add a hidden preheader span as the very first child of `<body>`:
   ```html
   <div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;color:#0b0f19;opacity:0;">
     {{ subtitle }} · Daily PnL {{ total_pnl.daily_pnl_eur }} · {{ position_rows|length }} positions tracked.
   </div>
   ```
   Place it immediately after `<body>` (line ~191). Gmail/Apple Mail show this preview text in the inbox list.

---

## 11. Saturday Deep Brief — additional treatment

**Why this section exists:** sections 1–10 apply to **both** daily and Saturday templates (Saturday inherits via `{% extends "daily_email.html.j2" %}`). But the Saturday brief must *feel* like a longer-form read — calmer accent, wider rhythm, extra editorial structure, redesigned Week Ahead. This section spells out the Saturday-only deltas.

**Files touched in this section:**
- `templates/daily_email.html.j2` — add empty `{% block %}` hooks so Saturday can inject content without duplicating the whole template.
- `templates/saturday_deep.html.j2` — fill those hooks; redesign Week Ahead.

**Behaviour rule:** the daily email must look exactly the same after these block hooks are added (empty blocks render nothing). Codex: verify with `python scripts/test_email.py` after step 11a — the daily preview must be byte-identical to before step 11a.

---

### 11a. Add block hooks in `daily_email.html.j2`

Codex: add four `{% block %}` placeholders so Saturday can extend without re-templating.

**Hook 1 — Hero mode chip.** Replace the inline mode-chip `<div>` from §3 with a block:

```jinja
{% block hero_chip %}
<div style="margin-top:18px;display:inline-block;padding:6px 14px;background:rgba(243,186,47,0.12);border:1px solid rgba(243,186,47,0.35);border-radius:999px;color:#f3ba2f;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
  {{ mode_label }}
</div>
{% endblock %}
```

**Hook 2 — Lede block** (rendered between hero and PnL Scoreboard, empty by default). Add right after the hero `</section>` (around line ~199):

```jinja
{% block deep_lede %}{% endblock %}
```

**Hook 3 — Synthesis intro** (rendered at the top of the AI Synthesis section, empty by default). Add inside the AI Synthesis `<section>`, **after** the section_header line:

```jinja
{% block synthesis_intro %}{% endblock %}
```

**Hook 4 — Reading rhythm class on synthesis copy.** Wrap the existing `<div class="copy">` in §3 / current line ~339 so Saturday can swap it:

```jinja
<div class="copy {% block synthesis_class %}{% endblock %}" style="margin-top:16px;">
```

---

### 11b. Hero — Saturday gets a distinct chip + secondary tagline

**Why:** the daily uses gold `Daily`. Saturday should not also be gold — it cheapens the brand accent. Use the slate-blue tones already in the palette (`#32405d` / `#b7c2d9`) for a calmer, "long-read" chip.

**Where:** `saturday_deep.html.j2`, override `{% block hero_chip %}`.

```jinja
{% block hero_chip %}
<table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:18px;">
  <tr>
    <td style="padding-right:8px;">
      <div style="display:inline-block;padding:6px 14px;background:#1a2335;border:1px solid #32405d;border-radius:999px;color:#b7c2d9;font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
        {{ mode_label }}
      </div>
    </td>
    <td style="padding-right:8px;">
      <div style="display:inline-block;padding:6px 14px;background:rgba(243,186,47,0.06);border:1px solid rgba(243,186,47,0.20);border-radius:999px;color:#f3ba2f;font-size:11px;font-weight:600;letter-spacing:0.04em;">
        Weekly · {{ word_count }} words · ≈ {{ reading_time_min }} min read
      </div>
    </td>
  </tr>
</table>
{% endblock %}
```

> ⚠️ **Data dependency:** `word_count` and `reading_time_min` are not in context today. `RenderedEmail.word_count` is computed *after* render so the template can't read it. Codex: **stop and ask the user** before adding these to context. Fallback if user says no — drop the second pill entirely; keep only the slate `Saturday Deep` chip. Don't fake a number.

The visual contrast is the point: Daily = single gold chip; Saturday = muted slate chip + optional gold "weekly" sub-chip. Reader knows which is in their inbox at a glance.

---

### 11c. Lede paragraph (Saturday-only opening)

**Why:** the daily reads like a dashboard. The Saturday brief is editorial. A 2–3 sentence lede sets the week's frame before the reader hits numbers.

**Where:** `saturday_deep.html.j2`, override `{% block deep_lede %}`.

```jinja
{% block deep_lede %}
{% if deep_lede %}
<section class="panel section" data-section="deep-lede" style="padding:24px 28px;background:linear-gradient(180deg,#131a2a 0%,#0f1524 100%);">
  <div style="border-left:3px solid #f3ba2f;padding-left:16px;">
    <p style="margin:0;color:#e6edf7;font-size:16px;line-height:1.7;font-weight:400;letter-spacing:0.005em;">{{ deep_lede }}</p>
  </div>
</section>
{% endif %}
{% endblock %}
```

> ⚠️ **Data dependency:** `deep_lede` is a new context field — a 2–3 sentence string, generated by the existing Saturday synthesis prompt or hand-edited. Codex: **stop and ask the user** before:
> 1. Adding `deep_lede` to the context (likely originates in `src/analyzer/synthesis.py` for deep mode), and
> 2. Wiring it through `src/pipeline/deep.py` and the renderer.
>
> If the user says "skip for now," leave the `{% if deep_lede %}` guard — the section silently no-ops when the field is absent. **Do not** invent placeholder copy.

The accent bar (gold left-border) reuses the same pattern as theme-group headings in §7b, so visual language stays consistent.

---

### 11d. Synthesis section — longform typography

**Why:** Saturday's `deep_synthesis_paragraphs` is intentionally longer than daily's `synthesis_paragraphs`. Same 14px line-height feels cramped at 4× the length.

**Where:** `saturday_deep.html.j2`, override the new `synthesis_class` and `synthesis_intro` blocks.

```jinja
{% block synthesis_class %}copy-longform{% endblock %}

{% block synthesis_intro %}
<p style="margin:14px 0 0;color:#8b9bb8;font-size:11px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;">
  This week, in five paragraphs.
</p>
{% endblock %}
```

Then in `daily_email.html.j2`'s `<style>` block, **add**:

```css
.copy-longform p {
  font-size: 15px !important;
  line-height: 1.8 !important;
  color: #e6edf7 !important;
  margin-bottom: 18px !important;
}
.copy-longform p:first-of-type {
  font-size: 16px !important;
  color: #ffffff !important;
}
```

> 🟡 The `!important` is needed because premailer inlines the base `.copy p` rule with higher specificity. Email is a hostile environment; live with it.

The first-paragraph bump (16px white) creates a soft "lead paragraph" feel without resorting to drop-caps (which break in Outlook).

---

### 11e. Week Ahead — full redesign

**Why:** the current Saturday-only `Week Ahead` is a plain `.table` with three columns (`Date / Event / Kind`). It looks identical to the position table four sections above. The Saturday brief deserves a distinct visual treatment for its only Saturday-only data.

**Where:** `saturday_deep.html.j2`, replace the entire `{% block week_ahead %}` body.

```jinja
{% block week_ahead %}
<section class="panel section" data-section="week-ahead" style="padding:28px 24px;">
  {{ section_header("Week Ahead", accent='#f3ba2f') }}
  {% if week_ahead_items %}
  <table role="presentation" cellspacing="0" cellpadding="0" width="100%">
    {% for item in week_ahead_items %}
    <tr>
      <td style="padding:0;">
        <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="margin-bottom:10px;">
          <tr>
            <td style="width:104px;vertical-align:top;padding:14px 0;">
              <div style="display:inline-block;padding:6px 12px;background:rgba(243,186,47,0.10);border:1px solid rgba(243,186,47,0.30);border-radius:8px;color:#f3ba2f;font-size:11px;font-weight:700;letter-spacing:0.06em;text-align:center;min-width:64px;">
                {{ item.date_label }}
              </div>
            </td>
            <td style="vertical-align:top;padding:14px 0 14px 16px;border-bottom:1px solid #1d2740;">
              <div style="color:#ffffff;font-size:15px;font-weight:600;line-height:1.45;letter-spacing:-0.005em;">{{ item.label }}</div>
              <div style="margin-top:6px;">
                <span style="display:inline-block;padding:3px 8px;background:#0f1524;border:1px solid #202b40;border-radius:6px;color:#aebbd2;font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">{{ item.kind }}</span>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p class="footer-note" style="margin:12px 0 0;">No week-ahead items were supplied for this Saturday run.</p>
  {% endif %}
</section>
{% endblock %}
```

What changed:
- Plain table → calendar-style row layout with a date pill on the left.
- `kind` (e.g., `earnings`, `macro`, `release`) becomes a small uppercase tag — visually clear category without color-coding (color-coding would require a kind→color map, which is a new data contract; skip for v0.1).
- Date pill uses gold tint (`accent-gold` at 10% bg) for hierarchy — date is the scanning anchor, not the event title.
- Bottom border on the right cell (not the left) creates a clean rhythm down the list, with the date pill floating out of the line.

---

### 11f. Section order in Saturday brief (final layout)

After all overrides, the Saturday email reads as:

1. **Hero** — slate `Saturday Deep` chip + (optional) `Weekly · X min read` chip
2. **Deep Lede** — single editorial paragraph with gold accent bar *(only if `deep_lede` field exists)*
3. **PnL Scoreboard** — same as daily
4. **Concentrated Exposures** — same as daily
5. **Theme Groups** — same as daily
6. **AI Synthesis (longform)** — wider line-height, "This week, in five paragraphs." kicker, lead paragraph emphasized
7. **Week Ahead** — date-pill calendar list (Saturday-only)
8. **Macro & Markets** — same as daily

Daily reads as: hero → PnL → exposures → themes → synthesis → macro. Saturday reads as: hero → **lede** → PnL → exposures → themes → **longform synthesis** → **week ahead** → macro. Two extra editorial sections, calmer accent, longer rhythm — that's the distinction.

---

## 12. Verification (do not skip)

After every numbered section is done:

```bash
# 1. Render with mock data
python scripts/test_email.py
open /tmp/preview.html  # or whatever path test_email.py prints

# 2. Render with real data, dry-run (no send)
python scripts/run_manual.py --preview

# 3. Tests still pass
pytest tests/test_renderer.py -v
ruff check .
```

**Acceptance checklist (must all be true before opening PR):**

*Daily template (`daily_email.html.j2`):*
- [ ] Hero title uses tighter letter-spacing; gold mode chip has tinted background.
- [ ] All P&L numbers (metric tiles + position table + theme cards) render in green/red/gray based on sign.
- [ ] Tabular numerics (`.num` class applied) keep numeric columns aligned.
- [ ] Concentrated Exposures shows horizontal weight bars; no header row.
- [ ] No theme group has more than 3 cards in a single row; 4-card themes wrap to 3+1.
- [ ] Theme cards' `Total` and `Daily` labels are inline with their values (single line each, not stacked).
- [ ] Article metadata is one line (chip + weight + themes), not three.
- [ ] **Macro footer renders as 2-column rows.** No card has a single word per line. Section is renamed to "Macro & Markets".
- [ ] Footer disclaimer has a 1px top border.
- [ ] Hidden preheader text shows in Gmail inbox preview.

*Saturday deep template (`saturday_deep.html.j2`):*
- [ ] All four block hooks (`hero_chip`, `deep_lede`, `synthesis_intro`, `synthesis_class`) added to daily template render empty by default; a daily `--preview` is **byte-identical** to before §11a.
- [ ] Saturday hero uses **slate** `Saturday Deep` chip, not gold (visually distinct from daily at a glance).
- [ ] Saturday `Deep Lede` block renders if `deep_lede` is provided; silently no-ops when absent.
- [ ] AI Synthesis on Saturday uses `.copy-longform` styles (15px / 1.8 line-height; first paragraph 16px white).
- [ ] Week Ahead renders as a calendar-style list with gold date pills, **not** the plain 3-column table from before.
- [ ] Saturday final section order matches §11f: hero → (lede) → PnL → exposures → themes → longform synthesis → week ahead → macro.
- [ ] `pytest tests/test_renderer.py -v` covers both `mode="daily"` and `mode="deep"` and passes.

*Cross-cutting:*
- [ ] Email word count still ≤ 1,000 for daily; Saturday is allowed to exceed (deep brief, by spec).
- [ ] `ruff check .` clean.
- [ ] Open the rendered HTML in **Gmail (web), Gmail (iOS), Apple Mail (macOS)** for both daily and Saturday previews; screenshot each. Compare daily against `code-feedback/Gmail29-04-26.pdf` — every defect listed below must be resolved.

**Defects from the PDF that this plan resolves:**

| # | Defect (from PDF) | Section that fixes it |
|---|---|---|
| 1 | Macro Footer cards collapse to one word per line | §8 |
| 2 | All P&L numbers render white regardless of sign | §5a, §5b, §7a |
| 3 | Precious Metals theme: 4 cards squeezed in a single row, "Total" and "Daily" labels stack on 4 lines | §7a |
| 4 | Article metadata uses 3 lines per article | §7c |
| 5 | Concentrated Exposures: dense table with no visual cue to which entity is biggest | §6 |
| 6 | Hero feels static; eyebrow uses dim gray instead of leading with brand color | §3 |
| 7 | Sectional eyebrows look identical and disconnected | §4 |
| 8 | Number columns don't align (proportional digits) | §2 |
| 9 | No subject preheader (inbox preview text wasted) | §10.5 |
| 10 | Footer disclaimer floats with no separation from cards | §8 |

---

## 13. Out of scope (do **not** do these)

These are tempting but not part of this pass:

- ❌ Don't restructure `src/renderer/render.py` or any Python module. (Exception: adding `total_pnl.total_pnl_sign` if the user approves §5a's data dependency.)
- ❌ Don't introduce SVG sparklines, charts, or images. v0.2 territory.
- ❌ Don't add web fonts via `<link>`. Gmail strips them; the system stack is final.
- ❌ Don't add light/auto theme support. v0.1 is dark-only by spec.
- ❌ Don't change the section order or rename Jinja blocks. The renderer asserts on `data-section` attributes. (Exception: §11 adds **new** `{% block %}` hooks and a new `data-section="deep-lede"`/`data-section="week-ahead"` — those are additions, not renames.)
- ❌ Don't add `cellpadding` / `cellspacing` to inline-CSS-only versions. Keep both, since some clients honor only the attribute.
- ❌ Don't replace the existing AI disclaimer chip styling. It's intentional and tested.

---

## 14. Order of operations (suggested)

Codex: do this in 5 small commits, not one big one. Each commit must pass `pytest` and `ruff check`. Run **both** `python scripts/run_manual.py --preview` and `python scripts/run_manual.py --mode=deep --preview` after every commit.

1. **Commit 1 — foundation (§1, §2, §4, §10.5):** add tokens reference comment if useful, swap font stack, add `.num` class, add `section_header` macro, add preheader span. Replace eyebrows with the macro across all sections. Diff is mostly mechanical. Run both previews, screenshot.
2. **Commit 2 — top half (§3, §5, §6):** hero polish, metric tiles with sign coloring, position table sign coloring, concentrated exposures bars. Run both previews, screenshot.
3. **Commit 3 — theme groups (§7):** card grid batch-by-3, theme heading accent bar, article metadata one-liner. Run both previews, screenshot.
4. **Commit 4 — macro footer + responsive (§8, §9, §10):** rewrite footer, add mobile rules, accessibility pass. Run both previews, screenshot.
5. **Commit 5 — Saturday deep brief (§11):** add the four `{% block %}` hooks to daily template (must be no-ops for daily preview), then implement Saturday-specific overrides — slate hero chip, lede block guard, longform synthesis class, Week Ahead calendar redesign. Verify daily preview is byte-identical to commit 4. Verify Saturday preview matches the §11f section order. Stop and ask the user about the `deep_lede` / `reading_time_min` / `word_count` data dependencies before adding context fields. Run both previews, screenshot.

Open the PR with all five commits and **both daily and Saturday screenshots** inline (compare daily against `code-feedback/Gmail29-04-26.pdf`; Saturday is the new layout — annotate which blocks are Saturday-only).

---

**Done condition:** the email looks like something a senior FT or Bloomberg engineer would ship. Specifically: numbers are color-coded, exposures are scannable in 2 seconds, no card collapses to vertical text, and the macro footer is a tidy 2-column shelf — not an Excel-error-message.
