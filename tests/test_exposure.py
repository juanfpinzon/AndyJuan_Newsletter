import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.exposure.models import ExposureEntry
from src.exposure.resolver import compute_exposure
from src.lookthrough.models import Holding
from src.portfolio.models import Position


def make_position(
    ticker: str,
    *,
    asset_type: str,
    cost_basis_eur: str,
    issuer: str | None = None,
    shares: str = "1",
) -> Position:
    return Position(
        ticker=ticker,
        isin=None,
        asset_type=asset_type,  # type: ignore[arg-type]
        issuer=issuer,
        shares=Decimal(shares),
        cost_basis_eur=Decimal(cost_basis_eur),
        currency="EUR",
    )


def test_compute_exposure_combines_direct_and_lookthrough_paths() -> None:
    positions = [
        make_position("NVDA", asset_type="stock", cost_basis_eur="10"),
        make_position("QDVE", asset_type="etf", cost_basis_eur="10", issuer="iShares"),
        make_position("GOOGL", asset_type="stock", cost_basis_eur="80"),
    ]
    lookthrough = {
        "QDVE": [
            Holding("NVDA", None, Decimal("30")),
            Holding("AAPL", None, Decimal("70")),
        ]
    }

    exposure = compute_exposure(positions, lookthrough)

    assert exposure["NVDA"] == ExposureEntry(
        entity="NVDA",
        composite_weight=Decimal("0.13"),
        paths=(
            {"source": "direct", "weight": Decimal("0.10")},
            {"source": "etf:QDVE", "weight": Decimal("0.03")},
        ),
    )
    assert exposure["AAPL"].composite_weight == Decimal("0.07")
    assert list(exposure) == ["GOOGL", "NVDA", "AAPL"]


def test_compute_exposure_coalesces_duplicate_physical_metal_rows() -> None:
    positions = [
        make_position("EGLN", asset_type="etf", cost_basis_eur="40", issuer="iShares"),
        make_position("NVDA", asset_type="stock", cost_basis_eur="60"),
    ]
    lookthrough = {
        "EGLN": [Holding("GOLD", None, Decimal("10")) for _ in range(10)],
    }

    exposure = compute_exposure(positions, lookthrough)

    assert exposure["GOLD"].composite_weight == Decimal("0.4")
    assert exposure["GOLD"].paths == (
        {"source": "etf:EGLN", "weight": Decimal("0.4")},
    )


def test_compute_exposure_weights_positions_by_total_cost_basis() -> None:
    positions = [
        make_position(
            "WIDE",
            asset_type="etf",
            cost_basis_eur="100",
            issuer="iShares",
            shares="2",
        ),
        make_position(
            "CASH",
            asset_type="stock",
            cost_basis_eur="50",
            shares="1",
        ),
    ]
    lookthrough = {
        "WIDE": [
            Holding("AAPL", None, Decimal("100")),
        ]
    }

    exposure = compute_exposure(positions, lookthrough)

    assert exposure["AAPL"] == ExposureEntry(
        entity="AAPL",
        composite_weight=Decimal("0.8"),
        paths=(
            {"source": "etf:WIDE", "weight": Decimal("0.8")},
        ),
    )
    assert exposure["CASH"].composite_weight == Decimal("0.2")


def test_compute_exposure_is_reproducible() -> None:
    positions = [
        make_position("NVDA", asset_type="stock", cost_basis_eur="50"),
        make_position(
            "SPYY",
            asset_type="etf",
            cost_basis_eur="50",
            issuer="State Street",
        ),
    ]
    lookthrough = {
        "SPYY": [
            Holding("NVDA", None, Decimal("4.82")),
            Holding("AAPL", None, Decimal("4.08")),
        ]
    }

    first = compute_exposure(positions, lookthrough)
    second = compute_exposure(positions, lookthrough)

    assert first == second


def test_compute_exposure_skips_unresolvable_etf_and_logs_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a single unresolvable ETF must not crash exposure.

    The ETF is excluded from both numerator and denominator, so the
    remaining exposure percentages are computed over the resolvable
    portfolio. This is the fail-soft end-to-end contract the watchdog
    required (resolver + exposure, not resolver in isolation).
    """
    log_path = tmp_path / "exposure.jsonl"
    monkeypatch.setenv("LOG_FILE", str(log_path))
    monkeypatch.setenv("APP_ENV", "prod")

    positions = [
        make_position("QDVE", asset_type="etf", cost_basis_eur="40", issuer="iShares"),
        make_position("NVDA", asset_type="stock", cost_basis_eur="60"),
    ]

    # QDVE has no look-through entry — must be skipped, not raised
    exposure = compute_exposure(positions, {})

    # NVDA is the only resolvable position → 100% weight
    assert exposure["NVDA"].composite_weight == Decimal("1")
    assert "QDVE" not in exposure

    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(log_lines[-1])
    assert payload["event"] == "lookthrough_exhausted"
    assert payload["ticker"] == "QDVE"
