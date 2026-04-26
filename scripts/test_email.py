"""Render a canned email preview to /tmp/preview.html and open it locally."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from src.renderer import render_email

PREVIEW_PATH = Path("/tmp/preview.html")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("daily", "deep"),
        default="daily",
        help="Template mode to preview.",
    )
    args = parser.parse_args()

    rendered = render_email(_sample_context(args.mode), mode=args.mode)
    PREVIEW_PATH.write_text(rendered.html, encoding="utf-8")
    webbrowser.open(PREVIEW_PATH.as_uri())
    print(f"Wrote preview to {PREVIEW_PATH} ({rendered.word_count} words)")
    return 0


def _sample_context(mode: str) -> dict[str, object]:
    return {
        "title": "Saturday Deep Portfolio Brief"
        if mode == "deep"
        else "Daily Portfolio Radar",
        "subtitle": "Position-aware brief for Juan and Andrea",
        "mode_label": "Saturday Deep" if mode == "deep" else "Daily",
        "generated_for_date": "April 26, 2026",
        "total_pnl": {
            "current_value_total_eur": "€2,760.68",
            "total_pnl_eur": "+€67.52",
            "total_pnl_pct": "+2.51%",
            "daily_pnl_eur": "+€0.14",
        },
        "position_rows": [
            {
                "ticker": "NVDA",
                "current_value_eur": "€412.12",
                "total_pnl_pct": "+14.2%",
                "daily_change_pct": "+1.1%",
                "theme": "AI/Semis",
            },
            {
                "ticker": "GOOGL",
                "current_value_eur": "€389.40",
                "total_pnl_pct": "+6.4%",
                "daily_change_pct": "+0.3%",
                "theme": "US Megacaps",
            },
            {
                "ticker": "EGLN",
                "current_value_eur": "€320.18",
                "total_pnl_pct": "+4.7%",
                "daily_change_pct": "-0.2%",
                "theme": "Precious Metals",
            },
        ],
        "concentrated_exposures": [
            {
                "entity": "NVDA",
                "composite_weight_percent": "13.00%",
                "path_count": 2,
            },
            {
                "entity": "GOOGL",
                "composite_weight_percent": "9.10%",
                "path_count": 1,
            },
            {
                "entity": "AAPL",
                "composite_weight_percent": "5.25%",
                "path_count": 2,
            },
        ],
        "theme_groups": [
            {
                "name": "AI/Semis",
                "description": (
                    "Semiconductor leaders and AI infrastructure beneficiaries."
                ),
                "cards": [
                    {
                        "ticker": "NVDA",
                        "current_value_eur": "€412.12",
                        "total_pnl_pct": "+14.2%",
                        "daily_change_pct": "+1.1%",
                    }
                ],
                "articles": [
                    {
                        "title": "Nvidia suppliers signal firm AI demand",
                        "source": "Reuters",
                        "href": "https://example.com/nvda-demand",
                        "published_at_label": "07:15 UTC",
                        "primary_entity": "NVDA",
                        "composite_weight_percent": "13.00%",
                        "affects_themes": ["US Megacaps"],
                    },
                    {
                        "title": "Chip equipment orders stay elevated",
                        "source": "Bloomberg",
                        "href": "https://example.com/chip-orders",
                        "published_at_label": "06:42 UTC",
                        "primary_entity": "NVDA",
                        "composite_weight_percent": "13.00%",
                        "affects_themes": [],
                    },
                ],
                "flash_text": (
                    "AI hardware demand still looks broad rather than "
                    "concentrated in a single winner."
                ),
            },
            {
                "name": "US Megacaps",
                "description": (
                    "Large-cap U.S. platform and index-heavy equity exposure."
                ),
                "cards": [
                    {
                        "ticker": "GOOGL",
                        "current_value_eur": "€389.40",
                        "total_pnl_pct": "+6.4%",
                        "daily_change_pct": "+0.3%",
                    }
                ],
                "articles": [
                    {
                        "title": "Alphabet leans into cloud efficiency",
                        "source": "FT",
                        "href": "https://example.com/googl-cloud",
                        "published_at_label": "06:40 UTC",
                        "primary_entity": "GOOGL",
                        "composite_weight_percent": "9.10%",
                        "affects_themes": ["AI/Semis"],
                    }
                ],
                "flash_text": (
                    "Megacap cash generation continues to cushion valuation pressure."
                ),
            },
            {
                "name": "Precious Metals",
                "description": "Physical metals and miners tied to gold and silver.",
                "cards": [
                    {
                        "ticker": "EGLN",
                        "current_value_eur": "€320.18",
                        "total_pnl_pct": "+4.7%",
                        "daily_change_pct": "-0.2%",
                    }
                ],
                "articles": [
                    {
                        "title": "Gold steadies as traders digest rates outlook",
                        "source": "CNBC",
                        "href": "https://example.com/gold-rates",
                        "published_at_label": "05:55 UTC",
                        "primary_entity": "EGLN",
                        "composite_weight_percent": "4.95%",
                        "affects_themes": ["Macro/FX"],
                    }
                ],
                "flash_text": (
                    "Metals remain more sensitive to rate expectations than to "
                    "cyclical growth chatter."
                ),
            },
        ],
        "synthesis_paragraphs": [
            (
                "AI and platform exposure remain the main drivers of portfolio "
                "sensitivity, with the strongest spillovers still concentrated "
                "in semis and cloud demand."
            ),
            (
                "Precious metals continue to behave as the rate-sensitive hedge "
                "in the mix, which matters when equity leadership narrows and "
                "macro pricing shifts abruptly."
            ),
            (
                "Watch whether next week brings broader participation or a "
                "sharper split between growth leadership and defensive hedges."
            ),
        ],
        "deep_synthesis_paragraphs": [
            (
                "This Saturday deep read extends the synthesis with more "
                "context on where portfolio sensitivity is clustering and why "
                "the same factors keep dominating the signal."
            ),
            (
                "AI infrastructure exposure still drives the upside case, but "
                "that conviction remains healthier if earnings breadth keeps "
                "confirming demand rather than narrowing to one or two names."
            ),
            (
                "Metals still matter as the rate-sensitive hedge in the mix, "
                "especially if macro repricing starts to pressure long-duration "
                "equity leadership."
            ),
            (
                "Into the week ahead, the practical question is whether fresh "
                "macro data broadens participation or reinforces the same "
                "concentrated leaders already carrying the book."
            ),
        ],
        "macro_items": [
            {
                "title": "ECB speakers keep rate path data-dependent",
                "source": "ECB",
                "href": "https://example.com/ecb-rates",
                "published_at_label": "05:50 UTC",
            },
            {
                "title": "Dollar index pauses after Treasury move",
                "source": "Reuters",
                "href": "https://example.com/dxy-pause",
                "published_at_label": "04:30 UTC",
            },
        ],
        "week_ahead_items": [
            {
                "date_label": "Mon",
                "label": "Eurozone CPI flash",
                "kind": "Macro",
            },
            {
                "date_label": "Wed",
                "label": "NVIDIA supplier earnings",
                "kind": "Earnings",
            },
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
