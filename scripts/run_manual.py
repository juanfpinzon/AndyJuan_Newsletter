"""Manual operator entry point for daily/deep runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_PREVIEW_PATH = Path("/tmp/preview.html")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    delivery = parser.add_mutually_exclusive_group()
    delivery.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline without sending email.",
    )
    delivery.add_argument(
        "--preview",
        action="store_true",
        help="Render HTML and open a local preview.",
    )
    delivery.add_argument(
        "--test-email",
        metavar="EMAIL",
        help="Send one test email to a single address.",
    )
    parser.add_argument(
        "--juan-only",
        action="store_true",
        help="Send only to Juan for test runs.",
    )
    parser.add_argument(
        "--reuse-seen-db",
        action="store_true",
        help="Reuse cached news articles from the seen-article database.",
    )
    parser.add_argument(
        "--ignore-seen-db",
        action="store_true",
        help="Refetch news even if URLs already exist in the seen-article database.",
    )
    parser.add_argument(
        "--mode",
        choices=("daily", "deep"),
        default="daily",
        help="Pipeline mode to run.",
    )
    args = parser.parse_args(argv)

    if args.reuse_seen_db and args.ignore_seen_db:
        parser.error("--reuse-seen-db and --ignore-seen-db cannot be combined")

    runner = _resolve_runner(args.mode)
    send = not (args.dry_run or args.preview)
    runner_kwargs = {
        "send": send,
        "from_addr": os.getenv("EMAIL_FROM"),
        "reuse_seen_db": args.reuse_seen_db,
        "ignore_seen_db": args.ignore_seen_db,
    }
    if args.test_email:
        runner_kwargs["recipients_override"] = [args.test_email]
    elif args.juan_only:
        runner_kwargs["juan_only"] = True
    result = runner(**runner_kwargs)

    if args.preview:
        preview_path = Path(
            os.getenv("ANDYJUAN_PREVIEW_PATH", str(DEFAULT_PREVIEW_PATH))
        )
        preview_path.write_text(result.rendered_email.html, encoding="utf-8")
        if os.getenv("ANDYJUAN_DISABLE_BROWSER") != "1":
            webbrowser.open(preview_path.as_uri())
        print(f"Preview written to {preview_path}")
        return 0

    if args.dry_run:
        summary = (
            f"Dry run complete for {args.mode} "
            f"({result.rendered_email.word_count} words)"
        )
        print(summary)
        return 0

    message_id = result.send_result.message_id if result.send_result else "unsent"
    if args.test_email:
        print(f"Sent test email to {args.test_email} ({message_id})")
        return 0

    print(f"Sent {args.mode} email ({message_id})")
    return 0


def _resolve_runner(mode: str):
    capture_path = os.getenv("ANDYJUAN_PIPELINE_STUB_CAPTURE")
    if capture_path:
        return _build_stub_runner(capture_path, mode)
    from src.pipeline import run_daily, run_deep

    return run_deep if mode == "deep" else run_daily


def _build_stub_runner(capture_path: str, mode: str):
    def _runner(**kwargs):
        payload = {"mode": mode, **kwargs}
        Path(capture_path).write_text(
            json.dumps(payload, sort_keys=True, default=_json_default),
            encoding="utf-8",
        )
        return SimpleNamespace(
            rendered_email=SimpleNamespace(
                html="<html><body>Stub Portfolio Radar</body></html>",
                text="Stub Portfolio Radar",
                word_count=3,
            ),
            send_result=SimpleNamespace(message_id="msg_stub"),
        )

    return _runner


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
