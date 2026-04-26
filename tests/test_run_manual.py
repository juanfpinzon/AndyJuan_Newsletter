from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "run_manual.py"


def test_run_manual_dry_run_passes_send_false(tmp_path: Path) -> None:
    result, payload = run_script(tmp_path, ["--dry-run"])

    assert result.returncode == 0
    assert payload["mode"] == "daily"
    assert payload["send"] is False
    assert payload["reuse_seen_db"] is False
    assert payload["ignore_seen_db"] is False


def test_run_manual_preview_writes_html(tmp_path: Path) -> None:
    preview_path = tmp_path / "preview.html"
    result, payload = run_script(
        tmp_path,
        ["--preview"],
        extra_env={"ANDYJUAN_PREVIEW_PATH": str(preview_path)},
    )

    assert result.returncode == 0
    assert payload["send"] is False
    assert preview_path.exists()
    assert "Stub Portfolio Radar" in preview_path.read_text(encoding="utf-8")


def test_run_manual_test_email_overrides_recipients(tmp_path: Path) -> None:
    result, payload = run_script(tmp_path, ["--test-email", "ops@example.com"])

    assert result.returncode == 0
    assert payload["send"] is True
    assert payload["recipients_override"] == ["ops@example.com"]


def test_run_manual_deep_mode_and_reuse_seen_db(tmp_path: Path) -> None:
    result, payload = run_script(
        tmp_path, ["--mode=deep", "--reuse-seen-db", "--preview"]
    )

    assert result.returncode == 0
    assert payload["mode"] == "deep"
    assert payload["reuse_seen_db"] is True
    assert payload["send"] is False


def test_run_manual_ignore_seen_db_passes_flag(tmp_path: Path) -> None:
    result, payload = run_script(tmp_path, ["--ignore-seen-db"])

    assert result.returncode == 0
    assert payload["ignore_seen_db"] is True
    assert payload["send"] is True


def test_run_manual_rejects_dry_run_with_test_email(tmp_path: Path) -> None:
    result, _ = run_script(tmp_path, ["--dry-run", "--test-email", "ops@example.com"])

    assert result.returncode != 0
    assert (
        "not allowed with argument" in result.stderr
        or "mutually exclusive" in result.stderr
    )


def test_run_manual_rejects_conflicting_seen_db_flags(tmp_path: Path) -> None:
    result, _ = run_script(tmp_path, ["--reuse-seen-db", "--ignore-seen-db"])

    assert result.returncode != 0
    assert "cannot be combined" in result.stderr


def run_script(
    tmp_path: Path,
    args: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    capture_path = tmp_path / "capture.json"
    env = os.environ.copy()
    env.update(
        {
            "ANDYJUAN_PIPELINE_STUB_CAPTURE": str(capture_path),
            "ANDYJUAN_DISABLE_BROWSER": "1",
        }
    )
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = (
        json.loads(capture_path.read_text(encoding="utf-8"))
        if capture_path.exists()
        else {}
    )
    return result, payload
