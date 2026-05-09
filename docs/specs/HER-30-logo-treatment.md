# Spec: HER-30 — Nano Banana Logo Treatment in Email Hero Banner

## Objective

Add a branded logo to the top-right area of the hero banner in the HTML email
template. Currently the hero section (`data-section="hero"`) displays only text
(eyebrow, h1 title, subtitle, mode chip). This change places a logo image aligned
to the right within that header.

**Recipients:** Andy + Juan (internal)  
**Success:** The sent email renders a recognizable Portfolio Radar / Nano Banana
logo in the top-right of the hero, correctly displayed in Gmail, Apple Mail, and
Outlook with no layout regressions.

---

## Tech Stack

- Python 3.11+ / Jinja2 (email templates)
- HTML email — must use `<table>` layout for cross-client compat (no flexbox/grid)
- PNG logo stored in `assets/logo.png`
- Base64 data URI embedding — avoids remote image blocking in email clients
- `premailer` (already handles CSS inlining at render time)

---

## Commands

```
Test:       pytest tests/ -v
Lint:       ruff check src/ tests/
Dev render: python scripts/test_email.py
```

---

## Project Structure Changes

```
assets/                         ← NEW directory
  logo.png                      ← NEW: Nano Banana / Portfolio Radar logo
docs/specs/
  HER-30-logo-treatment.md      ← this file
templates/
  daily_email.html.j2           ← MODIFY: hero → two-column table layout
  saturday_deep.html.j2         ← NO CHANGE (extends daily; hero inherited)
src/renderer/
  render.py                     ← MODIFY: load + inject logo_data_uri into context
tests/
  test_renderer.py              ← MODIFY: assert logo img tag present in output
```

---

## Implementation Plan

### 1 — Logo Asset

Store the logo at `assets/logo.png`:

- Max **200×80 px logical** (400×160 at 2× for retina), transparent background
- Dark-theme compatible: white/gold tones matching brand color `#f3ba2f`

> **BLOCKER — Open Question #1 below:** The exact logo file must be confirmed
> before this step can be completed.

### 2 — Base64 Loader in render.py

Load and encode the logo once at module level, inject into every template context:

```python
import base64

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"

def _logo_data_uri() -> str:
    logo_path = _ASSETS_DIR / "logo.png"
    return "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode()

_LOGO_DATA_URI = _logo_data_uri()
```

In `_normalize_context`, add:

```python
normalized["logo_data_uri"] = _LOGO_DATA_URI
```

### 3 — Hero Section Refactor (daily_email.html.j2)

Replace the current single-column hero `<section>` with a two-column
`<table role="presentation">`:

```
+----------------------------------------------+-------------------+
|  eyebrow · Portfolio Radar · date            |                   |
|  <h1> title </h1>                            |   [LOGO  IMAGE]   |
|  <p> subtitle </p>                           |                   |
|  mode chip                                   |                   |
+----------------------------------------------+-------------------+
      ~75% width                                    ~25% width
```

Right cell uses `valign="middle"` and holds:

```html
<img src="{{ logo_data_uri }}"
     alt="Portfolio Radar"
     width="160"
     style="display:block;max-width:160px;height:auto;border:0;" />
```

### 4 — Mobile: Hide Logo at ≤640px

Add to the existing `@media` block in the template `<style>`:

```css
@media only screen and (max-width: 640px) {
  .hero-logo { display: none !important; }
}
```

Apply class `hero-logo` to the right-column `<td>`.

---

## Code Style

Follow existing template conventions:

- Inline styles on all structural elements (premailer will not see class-only rules)
- `role="presentation"` on all layout tables
- `{%- -%}` Jinja2 whitespace control on macros
- No JS, no external font loads, no remote image URLs in templates

---

## Testing Strategy

**Unit test** (`tests/test_renderer.py`):

```python
def test_logo_present_in_daily_render(minimal_context):
    result = render_email(minimal_context, mode="daily")
    assert 'data:image/png;base64,' in result.html
    assert '<img' in result.html
```

**Visual test:** `python scripts/test_email.py` — renders and opens HTML locally
for manual inspection before sending.

No snapshot tests on the base64 string itself — asset changes invalidate them.

---

## Boundaries

| Category   | Rule |
|------------|------|
| Always     | Use `<table>` layout (not flex/grid) in email HTML |
| Always     | Embed logo as data URI; never use a remote URL that could 404 |
| Always     | Run `pytest tests/ -v` before committing |
| Ask first  | Changing logo dimensions or replacing the asset file |
| Ask first  | Adding additional context variables beyond `logo_data_uri` |
| Ask first  | Overriding the hero block in `saturday_deep.html.j2` differently |
| Never      | Use `display:flex` or CSS Grid in email HTML |
| Never      | Commit JS to templates |
| Never      | Reference the Linear-hosted image URL (signed URL expires) |

---

## Success Criteria

- [ ] `pytest tests/ -v` passes — zero regressions
- [ ] `ruff check` passes clean
- [ ] Rendered HTML contains `<img` with `data:image/png;base64,` inside the hero section
- [ ] Logo is visible top-right in the daily hero at ≥641px viewport
- [ ] On mobile (≤640px), logo column is hidden with no layout breakage
- [ ] `saturday_deep.html.j2` renders with the same logo (auto-inherited from base)

---

## Open Questions

1. **Logo file (BLOCKER):** What is the exact logo asset to use? Is it derived
   from the `AndyJuan-Radar.png` screenshot on the Linear issue, or a separate
   wordmark/icon file? This must be confirmed before `assets/logo.png` can be
   committed and the template wired up.

2. **Display dimensions:** Preferred max display height in the hero? Suggest
   **64px tall** (128px asset at 2× for retina). Please confirm.

3. **Saturday deep opt-out:** Should the Saturday deep email share the exact
   same logo treatment, or does it get a different variant/size?
