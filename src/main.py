"""Production CLI for scheduled daily/deep runs."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from src.pipeline import run_daily, run_deep

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("daily", "deep"),
        default="daily",
        help="Pipeline mode to run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline without sending email.",
    )
    args = parser.parse_args(argv)

    runner = run_deep if args.mode == "deep" else run_daily
    runner(send=not args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
