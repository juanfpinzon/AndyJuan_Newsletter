import importlib.util
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "import_snowball.py"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_importer_module():
    spec = importlib.util.spec_from_file_location("import_snowball", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_portfolio(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "positions:",
                "  - ticker: NVDA",
                "    isin: US67066G1040",
                "    asset_type: stock",
                "    issuer: NVIDIA Corporation",
                "    shares: '2.4932'",
                "    cost_basis_eur: '156.265041'",
                "    currency: USD",
                "    theme: AI/Semis",
                "  - ticker: BNKE",
                "    isin: LU1829219390",
                "    asset_type: etf",
                "    issuer: Amundi",
                "    shares: '1.1023'",
                "    cost_basis_eur: '301.551302'",
                "    currency: EUR",
                "    theme: EU Banks",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_import_snowball_dry_run_shows_diff_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_importer_module()
    portfolio_path = tmp_path / "portfolio.yaml"
    write_portfolio(portfolio_path)
    original_text = portfolio_path.read_text(encoding="utf-8")
    module.DEFAULT_PORTFOLIO_PATH = portfolio_path

    exit_code = module.main([str(FIXTURES_DIR / "snowball-export.csv"), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert portfolio_path.read_text(encoding="utf-8") == original_text
    assert "TSLA" in captured.out
    assert "GOOGL" in captured.out
    assert "BNKE" in captured.err


def test_import_snowball_updates_existing_positions_and_preserves_enrichment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_importer_module()
    portfolio_path = tmp_path / "portfolio.yaml"
    write_portfolio(portfolio_path)
    module.DEFAULT_PORTFOLIO_PATH = portfolio_path

    exit_code = module.main([str(FIXTURES_DIR / "snowball-export.csv")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "new ticker scaffolded: TSLA" in captured.err
    assert "missing from Snowball export: BNKE" in captured.err

    portfolio = yaml.safe_load(portfolio_path.read_text(encoding="utf-8"))
    positions_by_ticker = {
        entry["ticker"]: entry for entry in portfolio["positions"]
    }

    assert positions_by_ticker["NVDA"]["issuer"] == "NVIDIA Corporation"
    assert positions_by_ticker["NVDA"]["theme"] == "AI/Semis"
    assert positions_by_ticker["NVDA"]["shares"] == "2.7500"
    assert positions_by_ticker["NVDA"]["cost_basis_eur"] == "180.000000"

    assert positions_by_ticker["GOOGL"]["asset_type"] == "stock"
    assert positions_by_ticker["GOOGL"]["issuer"] is None
    assert positions_by_ticker["GOOGL"]["isin"] is None
    assert positions_by_ticker["GOOGL"]["currency"] == "USD"

    assert positions_by_ticker["TSLA"]["asset_type"] == "stock"
    assert positions_by_ticker["TSLA"]["issuer"] is None
    assert positions_by_ticker["TSLA"]["isin"] is None

    assert positions_by_ticker["BNKE"]["theme"] == "EU Banks"


def test_load_snowball_rows_raises_for_missing_required_headers(
    tmp_path: Path,
) -> None:
    module = load_importer_module()
    csv_path = tmp_path / "broken.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Ticker,Shares,Currency",
                "NVDA,2.7500,USD",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(module.SnowballSchemaError, match="Average cost"):
        module.load_snowball_rows(csv_path)


def test_import_snowball_raises_for_currency_mismatch(tmp_path: Path) -> None:
    module = load_importer_module()
    portfolio_path = tmp_path / "portfolio.yaml"
    write_portfolio(portfolio_path)

    csv_path = tmp_path / "currency-mismatch.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Ticker,Shares,Average cost,Currency",
                "BNKE,1.1023,301.551302,USD",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(module.SnowballImportError, match="currency mismatch"):
        module.import_snowball(csv_path, dry_run=False, portfolio_path=portfolio_path)


def test_load_snowball_rows_aggregates_transaction_exports() -> None:
    module = load_importer_module()

    rows = module.load_snowball_rows(FIXTURES_DIR / "snowball-transactions.csv")

    assert rows["BNKE"] == {
        "shares": "0.3729",
        "cost_basis_eur": "281.514360",
        "currency": "EUR",
    }
    assert rows["GOOGL"] == {
        "shares": "0.1138",
        "cost_basis_eur": "261.950791",
        "currency": "USD",
    }
    assert "ACWE" not in rows


def test_import_snowball_transaction_export_preserves_existing_cost_basis(
    tmp_path: Path,
) -> None:
    module = load_importer_module()
    portfolio_path = tmp_path / "portfolio.yaml"
    write_portfolio(portfolio_path)

    exit_diff, warnings = module.import_snowball(
        FIXTURES_DIR / "snowball-transactions.csv",
        dry_run=False,
        portfolio_path=portfolio_path,
    )

    assert "GOOGL" in exit_diff
    assert warnings == [
        "missing from Snowball export: NVDA",
        "new ticker scaffolded: GOOGL",
    ]

    portfolio = yaml.safe_load(portfolio_path.read_text(encoding="utf-8"))
    positions_by_ticker = {
        entry["ticker"]: entry for entry in portfolio["positions"]
    }

    assert positions_by_ticker["BNKE"]["shares"] == "0.3729"
    assert positions_by_ticker["BNKE"]["cost_basis_eur"] == "301.551302"
    assert positions_by_ticker["GOOGL"]["cost_basis_eur"] == "261.950791"
    assert "ACWE" not in positions_by_ticker
