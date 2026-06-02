"""Production CLI for scheduled daily/deep runs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from src.pipeline import run_daily, run_deep


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
    parser.add_argument(
        "--juan-only",
        action="store_true",
        help="Send to Juan only for test runs.",
    )
    args = parser.parse_args(argv)

    runner = _resolve_runner(args.mode)
    runner_kwargs = {"send": not args.dry_run}
    if args.juan_only:
        runner_kwargs["juan_only"] = True
    runner(**runner_kwargs)
    return 0


def _resolve_runner(mode: str):
    capture_path = os.getenv("ANDYJUAN_PIPELINE_STUB_CAPTURE")
    if capture_path:
        return _build_stub_runner(capture_path, mode)
    return run_deep if mode == "deep" else run_daily


def _build_stub_runner(capture_path: str, mode: str):
    def _runner(**kwargs):
        payload = {"mode": mode, **kwargs}
        Path(capture_path).write_text(
            json.dumps(payload, sort_keys=True, default=_json_default),
            encoding="utf-8",
        )
        return SimpleNamespace(send_result=SimpleNamespace(message_id="msg_stub"))

    return _runner


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return str(value)


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    raise SystemExit(main())
