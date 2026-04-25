import json
from pathlib import Path

from src.analyzer.fact_checker import (
    FactCheckResult,
    fact_check_ai_take,
    filter_ai_take,
)
from src.config import Settings
from src.utils.llm import LLMResponse

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "llm" / "fact_checker"


class FakeLLMCaller:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        fallback_model: str | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
                "fallback_model": fallback_model,
            }
        )
        return LLMResponse(
            content=self.content,
            model=model,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
        )


def load_input(name: str) -> dict[str, str]:
    path = FIXTURES_DIR / name / "input.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_response(name: str) -> str:
    return (FIXTURES_DIR / name / "response.txt").read_text(encoding="utf-8")


def make_settings(log_file: str) -> Settings:
    return Settings(
        llm_scoring_model="anthropic/claude-haiku-4.5",
        llm_synthesis_model="anthropic/claude-sonnet-4-6",
        llm_fact_check_model="anthropic/claude-haiku-4.5",
        llm_fallback_model="anthropic/claude-haiku-4.5",
        database_path="data/test.db",
        log_file=log_file,
        news_item_limit=15,
        exposure_threshold_percent=5.0,
        entity_match_threshold=85.0,
    )


def test_fact_check_ai_take_passes_grounded_output(tmp_path: Path) -> None:
    scenario = load_input("clean_pass")
    llm = FakeLLMCaller(load_response("clean_pass"))

    result = fact_check_ai_take(
        scenario["rendered_content"],
        scenario["ai_take_text"],
        llm_caller=llm,
        settings=make_settings(str(tmp_path / "pass.jsonl")),
    )

    assert result == FactCheckResult(ok=True, flagged_claims=())
    assert "AI/Semis remained the strongest thread" in str(llm.calls[0]["prompt"])


def test_filter_ai_take_blocks_planted_novel_fact_and_logs_it(
    tmp_path: Path, monkeypatch
) -> None:
    scenario = load_input("planted_novel_fact")
    log_file = tmp_path / "fact-check.jsonl"
    monkeypatch.setenv("LOG_FILE", str(log_file))

    filtered = filter_ai_take(
        scenario["rendered_content"],
        scenario["ai_take_text"],
        llm_caller=FakeLLMCaller(load_response("planted_novel_fact")),
        settings=make_settings(str(log_file)),
    )

    assert filtered is None
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert any("NVDA acquired AMD" in line for line in lines)
    assert any("ai_take_blocked" in line for line in lines)


def test_fact_check_ai_take_fails_closed_on_invalid_json(tmp_path: Path) -> None:
    scenario = load_input("clean_pass")

    result = fact_check_ai_take(
        scenario["rendered_content"],
        scenario["ai_take_text"],
        llm_caller=FakeLLMCaller("not-json"),
        settings=make_settings(str(tmp_path / "invalid.jsonl")),
    )

    assert result.ok is False
    assert result.flagged_claims == ("Invalid fact-checker response",)


def test_fact_check_ai_take_rejects_non_mapping_payload(tmp_path: Path) -> None:
    scenario = load_input("clean_pass")

    result = fact_check_ai_take(
        scenario["rendered_content"],
        scenario["ai_take_text"],
        llm_caller=FakeLLMCaller("[]"),
        settings=make_settings(str(tmp_path / "array.jsonl")),
    )

    assert result == FactCheckResult(
        ok=False,
        flagged_claims=("Invalid fact-checker response",),
    )


def test_fact_check_ai_take_defaults_to_unverified_when_claims_are_missing(
    tmp_path: Path,
) -> None:
    scenario = load_input("clean_pass")

    result = fact_check_ai_take(
        scenario["rendered_content"],
        scenario["ai_take_text"],
        llm_caller=FakeLLMCaller('{"ok": false, "flagged_claims": 7}'),
        settings=make_settings(str(tmp_path / "unverified.jsonl")),
    )

    assert result == FactCheckResult(
        ok=False,
        flagged_claims=("Unverified AI take",),
    )


def test_fact_check_ai_take_normalizes_string_flagged_claims(tmp_path: Path) -> None:
    scenario = load_input("clean_pass")

    result = fact_check_ai_take(
        scenario["rendered_content"],
        scenario["ai_take_text"],
        llm_caller=FakeLLMCaller(
            '{"ok": false, "flagged_claims": "NVDA acquired AMD"}'
        ),
        settings=make_settings(str(tmp_path / "string-claim.jsonl")),
    )

    assert result == FactCheckResult(
        ok=False,
        flagged_claims=("NVDA acquired AMD",),
    )


def test_filter_ai_take_returns_original_text_on_pass(tmp_path: Path) -> None:
    scenario = load_input("clean_pass")
    ai_take_text = scenario["ai_take_text"]

    filtered = filter_ai_take(
        scenario["rendered_content"],
        ai_take_text,
        llm_caller=FakeLLMCaller(load_response("clean_pass")),
        settings=make_settings(str(tmp_path / "clean.jsonl")),
    )

    assert filtered == ai_take_text
