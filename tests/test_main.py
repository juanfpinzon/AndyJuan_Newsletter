from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.sender.agentmail import SendResult

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_main_routes_daily_mode(monkeypatch) -> None:
    import src.main as main

    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        main,
        "run_daily",
        lambda **kwargs: calls.append(("daily", kwargs)) or _fake_result(),
    )
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: calls.append(("deep", kwargs)) or _fake_result(),
    )

    exit_code = main.main(["--mode", "daily"])

    assert exit_code == 0
    assert calls == [("daily", {"send": True})]


def test_main_routes_deep_mode(monkeypatch) -> None:
    import src.main as main

    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        main,
        "run_daily",
        lambda **kwargs: calls.append(("daily", kwargs)) or _fake_result(),
    )
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: calls.append(("deep", kwargs)) or _fake_result(),
    )

    exit_code = main.main(["--mode", "deep"])

    assert exit_code == 0
    assert calls == [("deep", {"send": True})]


def test_main_routes_dry_run_with_send_false(monkeypatch) -> None:
    import src.main as main

    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        main,
        "run_daily",
        lambda **kwargs: calls.append(("daily", kwargs)) or _fake_result(),
    )
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: calls.append(("deep", kwargs)) or _fake_result(),
    )

    exit_code = main.main(["--mode", "deep", "--dry-run"])

    assert exit_code == 0
    assert calls == [("deep", {"send": False})]


def test_main_routes_juan_only_mode(monkeypatch) -> None:
    import src.main as main

    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        main,
        "run_daily",
        lambda **kwargs: calls.append(("daily", kwargs)) or _fake_result(),
    )
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: calls.append(("deep", kwargs)) or _fake_result(),
    )

    exit_code = main.main(["--mode", "daily", "--juan-only"])

    assert exit_code == 0
    assert calls == [("daily", {"send": True, "juan_only": True})]


def test_main_subprocess_daily_dry_run_smoke(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.json"
    env = os.environ.copy()
    env["ANDYJUAN_PIPELINE_STUB_CAPTURE"] = str(capture_path)

    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--mode", "daily", "--dry-run"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert json.loads(capture_path.read_text(encoding="utf-8")) == {
        "mode": "daily",
        "send": False,
    }


def _fake_result():
    return type(
        "Result",
        (),
        {"send_result": SendResult(message_id="msg_123")},
    )()
