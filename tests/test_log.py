import json
from pathlib import Path

import pytest

from src.utils.log import get_logger


def test_get_logger_writes_jsonl_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = tmp_path / "andyjuan.jsonl"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("APP_ENV", "production")

    logger = get_logger("tests")
    logger.info("test_event", foo="bar")

    payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])

    assert payload["event"] == "test_event"
    assert payload["foo"] == "bar"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_get_logger_uses_updated_log_file_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_log = tmp_path / "first.jsonl"
    second_log = tmp_path / "second.jsonl"
    monkeypatch.setenv("APP_ENV", "production")

    monkeypatch.setenv("LOG_FILE", str(first_log))
    get_logger("first").info("first_event")

    monkeypatch.setenv("LOG_FILE", str(second_log))
    get_logger("second").info("second_event")

    assert first_log.exists()
    assert second_log.exists()
