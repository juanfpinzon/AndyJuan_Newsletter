from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from src.config import Settings, SnapTradeSettings
from src.portfolio.loader import (
    PortfolioLoadError,
    load_portfolio,
    load_portfolio_snapshot,
    load_portfolio_snapshot_bundle,
    merge_positions,
)
from src.portfolio.models import Position
from src.portfolio.snaptrade_client import SnapTradeError
from src.storage.db import cache_position_snapshot

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
            market_symbol="IITU.L",
        ),
    ]

    assert isinstance(positions[0].shares, Decimal)
    assert isinstance(positions[0].cost_basis_eur, Decimal)
    assert positions[0].market_symbol is None

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


def test_repository_recipients_config_uses_real_andrea_address() -> None:
    recipients = yaml.safe_load(
        (REPOSITORY_ROOT / "config" / "recipients.yaml").read_text(encoding="utf-8")
    )

    assert recipients["recipients"]["andrea"]["email"] == "andrea.aliciap@gmail.com"


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
        (REPOSITORY_ROOT / "config" / "etf_holdings.yaml").read_text(encoding="utf-8")
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


def test_merge_positions_overlays_live_numeric_fields_on_yaml_metadata() -> None:
    merged = merge_positions(
        canonical_positions=[
            Position(
                ticker="QDVE",
                isin="IE00B3WJKG14",
                asset_type="etf",
                issuer="iShares",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("10"),
                currency="EUR",
                market_symbol="IITU.L",
            )
        ],
        live_positions=[
            Position(
                ticker="QDVE",
                isin=None,
                asset_type="etf",
                issuer=None,
                shares=Decimal("3.25"),
                cost_basis_eur=Decimal("42.10"),
                currency="USD",
                source="snaptrade",
                last_updated=datetime(2026, 5, 15, 7, 30, tzinfo=UTC),
            )
        ],
    )

    assert merged == [
        Position(
            ticker="QDVE",
            isin="IE00B3WJKG14",
            asset_type="etf",
            issuer="iShares",
            shares=Decimal("3.25"),
            cost_basis_eur=Decimal("42.10"),
            currency="USD",
            market_symbol="IITU.L",
            source="snaptrade",
            last_updated=datetime(2026, 5, 15, 7, 30, tzinfo=UTC),
        )
    ]


def test_merge_positions_skips_unknown_live_etf_without_supported_issuer() -> None:
    warnings: list[dict[str, object]] = []

    class StubLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings.append({"event": event, **kwargs})

    merged = merge_positions(
        canonical_positions=[],
        live_positions=[
            Position(
                ticker="MYST",
                isin=None,
                asset_type="etf",
                issuer="Mystery Funds Tactical ETF",
                shares=Decimal("2"),
                cost_basis_eur=Decimal("50"),
                currency="USD",
                source="snaptrade",
                last_updated=datetime(2026, 5, 15, 7, 30, tzinfo=UTC),
            )
        ],
        logger=StubLogger(),
    )

    assert merged == []
    assert warnings == [
        {
            "event": "snaptrade_etf_skipped",
            "ticker": "MYST",
            "reason": "missing_canonical_metadata",
        }
    ]


def test_merge_positions_can_treat_live_snapshot_as_authoritative() -> None:
    merged = merge_positions(
        canonical_positions=[
            Position(
                ticker="NVDA",
                isin="US67066G1040",
                asset_type="stock",
                issuer="NVIDIA Corporation",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("10"),
                currency="USD",
            ),
            Position(
                ticker="QDVE",
                isin="IE00B3WJKG14",
                asset_type="etf",
                issuer="iShares",
                shares=Decimal("1"),
                cost_basis_eur=Decimal("10"),
                currency="EUR",
            ),
        ],
        live_positions=[
            Position(
                ticker="QDVE",
                isin=None,
                asset_type="etf",
                issuer=None,
                shares=Decimal("3.25"),
                cost_basis_eur=Decimal("42.10"),
                currency="EUR",
                source="snaptrade",
            )
        ],
        include_missing_canonical=False,
    )

    assert [position.ticker for position in merged] == ["QDVE"]


def test_load_portfolio_snapshot_uses_cached_snaptrade_positions_when_live_fetch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.portfolio.loader as loader

    settings = Settings(
        llm_scoring_model="ranker",
        llm_synthesis_model="synth",
        llm_fact_check_model="fact-check",
        llm_fallback_model="fallback",
        database_path=str(tmp_path / "andyjuan.db"),
        log_file=str(tmp_path / "andyjuan.jsonl"),
        news_item_limit=10,
        exposure_threshold_percent=5.0,
        entity_match_threshold=85.0,
        snaptrade=SnapTradeSettings(
            enabled=True,
            client_id="client",
            consumer_key="consumer",
            user_id="user",
            user_secret="secret",
            account_id="account",
        ),
    )
    db_path = tmp_path / "andyjuan.db"
    cache_position_snapshot(
        db_path,
        source="snaptrade",
        positions=[
            Position(
                ticker="NVDA",
                isin=None,
                asset_type="stock",
                issuer=None,
                shares=Decimal("4.5"),
                cost_basis_eur=Decimal("120.00"),
                currency="USD",
                source="snaptrade",
                last_updated=datetime(2026, 5, 15, 7, 45, tzinfo=UTC),
            )
        ],
    )

    class FailingSnapTradeClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def get_positions(self) -> list[Position]:
            raise SnapTradeError("snaptrade down")

    warnings: list[dict[str, object]] = []

    class StubLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings.append({"event": event, **kwargs})

    monkeypatch.setattr(loader, "SnapTradeClient", FailingSnapTradeClient)
    monkeypatch.setattr(loader, "get_logger", lambda name=None: StubLogger())

    positions = load_portfolio_snapshot(settings=settings, db_path=db_path)

    assert any(item["event"] == "snaptrade_fallback_used" for item in warnings)
    nvda = next(position for position in positions if position.ticker == "NVDA")
    assert nvda.shares == Decimal("4.5")
    assert nvda.source == "snaptrade"


def test_load_portfolio_snapshot_bundle_returns_live_client_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.portfolio.loader as loader

    settings = Settings(
        llm_scoring_model="ranker",
        llm_synthesis_model="synth",
        llm_fact_check_model="fact-check",
        llm_fallback_model="fallback",
        database_path=str(tmp_path / "andyjuan.db"),
        log_file=str(tmp_path / "andyjuan.jsonl"),
        news_item_limit=10,
        exposure_threshold_percent=5.0,
        entity_match_threshold=85.0,
        snaptrade=SnapTradeSettings(
            enabled=True,
            client_id="client",
            consumer_key="consumer",
            user_id="user",
            user_secret="secret",
            account_id="account",
        ),
    )

    class FakeSnapTradeClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def get_positions(self) -> list[Position]:
            return [
                Position(
                    ticker="NVDA",
                    isin=None,
                    asset_type="stock",
                    issuer="NVIDIA Corporation",
                    shares=Decimal("2"),
                    cost_basis_eur=Decimal("120"),
                    currency="USD",
                    source="snaptrade",
                    last_updated=datetime(2026, 5, 15, 8, 0, tzinfo=UTC),
                )
            ]

    fake_client = FakeSnapTradeClient()
    monkeypatch.setattr(
        loader,
        "SnapTradeClient",
        lambda *args, **kwargs: fake_client,
    )

    bundle = load_portfolio_snapshot_bundle(
        settings=settings,
        db_path=tmp_path / "andyjuan.db",
    )

    assert bundle.snaptrade_client is fake_client
    assert [position.ticker for position in bundle.positions] == ["NVDA"]
