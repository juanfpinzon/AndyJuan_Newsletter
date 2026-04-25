from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from src.portfolio.loader import PortfolioLoadError, load_portfolio
from src.portfolio.models import Position

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_load_portfolio_returns_positions_with_decimal_fields() -> None:
    positions = load_portfolio(FIXTURES_DIR / "portfolio.yaml")

    assert positions == [
        Position(
            ticker="NVDA",
            isin="US67066G1040",
            asset_type="stock",
            issuer="NVIDIA Corporation",
            shares=Decimal("2.5000"),
            cost_basis_eur=Decimal("156.265041"),
            currency="USD",
        ),
        Position(
            ticker="QDVE",
            isin="IE00B3WJKG14",
            asset_type="etf",
            issuer="iShares",
            shares=Decimal("1.2500"),
            cost_basis_eur=Decimal("35.183007"),
            currency="EUR",
        ),
    ]

    assert isinstance(positions[0].shares, Decimal)
    assert isinstance(positions[0].cost_basis_eur, Decimal)

    with pytest.raises(FrozenInstanceError):
        positions[0].ticker = "AMD"


def test_load_portfolio_raises_for_missing_required_field(tmp_path: Path) -> None:
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        "\n".join(
            [
                "version: 1",
                "positions:",
                "  - ticker: NVDA",
                "    isin: US67066G1040",
                "    asset_type: stock",
                "    issuer: NVIDIA Corporation",
                "    shares: '2.5'",
                "    cost_basis_eur: '156.265041'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PortfolioLoadError, match="currency"):
        load_portfolio(portfolio_path)


def test_load_portfolio_raises_for_invalid_decimal(tmp_path: Path) -> None:
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        "\n".join(
            [
                "version: 1",
                "positions:",
                "  - ticker: NVDA",
                "    isin: US67066G1040",
                "    asset_type: stock",
                "    issuer: NVIDIA Corporation",
                "    shares: not-a-decimal",
                "    cost_basis_eur: '156.265041'",
                "    currency: USD",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PortfolioLoadError, match="shares"):
        load_portfolio(portfolio_path)


def test_repository_phase_one_config_files_load_cleanly() -> None:
    config_files = [
        REPOSITORY_ROOT / "config" / "settings.yaml",
        REPOSITORY_ROOT / "config" / "recipients.yaml",
        REPOSITORY_ROOT / "config" / "themes.yaml",
        REPOSITORY_ROOT / "config" / "macro_feeds.yaml",
        REPOSITORY_ROOT / "config" / "portfolio.yaml",
        REPOSITORY_ROOT / "config" / "etf_holdings.yaml",
    ]

    for path in config_files:
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None


def test_repository_portfolio_matches_seed_screenshot_totals() -> None:
    positions = load_portfolio(REPOSITORY_ROOT / "config" / "portfolio.yaml")

    assert len(positions) == 10

    total_cost_basis = sum(
        position.shares * position.cost_basis_eur for position in positions
    )
    assert abs(total_cost_basis - Decimal("2693.16")) <= Decimal("0.01")

    for position in positions:
        if position.asset_type == "etf":
            assert position.issuer


def test_repository_theme_assignments_cover_seed_positions() -> None:
    portfolio = load_portfolio(REPOSITORY_ROOT / "config" / "portfolio.yaml")
    themes = yaml.safe_load(
        (REPOSITORY_ROOT / "config" / "themes.yaml").read_text(encoding="utf-8")
    )

    assert {
        "Defense",
        "AI/Semis",
        "Precious Metals",
        "EU Banks",
        "US Megacaps",
        "Macro/FX",
    }.issubset(set(themes["themes"]))

    entities = themes["entities"]
    for position in portfolio:
        assert entities[position.ticker]["primary_theme"]


def test_repository_etf_holdings_file_covers_each_fund_position() -> None:
    portfolio = load_portfolio(REPOSITORY_ROOT / "config" / "portfolio.yaml")
    etf_holdings = yaml.safe_load(
        (REPOSITORY_ROOT / "config" / "etf_holdings.yaml").read_text(
            encoding="utf-8"
        )
    )

    etf_tickers = {
        position.ticker for position in portfolio if position.asset_type == "etf"
    }
    assert set(etf_holdings) == etf_tickers

    for ticker, data in etf_holdings.items():
        top_ten = data["top_10"]
        assert len(top_ten) == 10, ticker
        assert all(entry["ticker"] for entry in top_ten), ticker
        minimum_weight = Decimal("20") if ticker == "SPYY" else Decimal("30")
        assert sum(Decimal(str(entry["weight"])) for entry in top_ten) > minimum_weight
