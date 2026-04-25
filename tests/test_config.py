from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest

from src.config import ConfigError, load_settings


def write_settings(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "llm_scoring_model: primary-model",
                "llm_synthesis_model: synthesis-model",
                "llm_fact_check_model: fact-check-model",
                "llm_fallback_model: fallback-model",
                "database_path: data/test.db",
                "log_file: data/logs/test.jsonl",
                "news_item_limit: 15",
                "exposure_threshold_percent: 5.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_settings_returns_frozen_dataclass(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)

    settings = load_settings(settings_path)

    assert is_dataclass(settings)
    assert settings.llm_scoring_model == "primary-model"

    with pytest.raises(FrozenInstanceError):
        settings.llm_scoring_model = "mutated-model"


def test_load_settings_uses_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    monkeypatch.setenv("LLM_SCORING_MODEL", "override-model")

    settings = load_settings(settings_path)

    assert settings.llm_scoring_model == "override-model"


def test_load_settings_coerces_environment_numeric_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.yaml"
    write_settings(settings_path)
    monkeypatch.setenv("NEWS_ITEM_LIMIT", "99")
    monkeypatch.setenv("EXPOSURE_THRESHOLD_PERCENT", "6.5")

    settings = load_settings(settings_path)

    assert isinstance(settings.news_item_limit, int)
    assert settings.news_item_limit == 99
    assert isinstance(settings.exposure_threshold_percent, float)
    assert settings.exposure_threshold_percent == 6.5


def test_load_settings_raises_for_missing_required_keys(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("log_file: data/logs/test.jsonl\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="llm_scoring_model"):
        load_settings(settings_path)


def test_load_settings_defaults_to_repository_config() -> None:
    settings = load_settings()

    assert settings.database_path == "data/andyjuan.db"
