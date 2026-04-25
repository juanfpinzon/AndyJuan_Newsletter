from dataclasses import dataclass
from pathlib import Path

from src.storage.db import init_db
from src.utils.llm import call_openrouter


@dataclass
class FakeMessage:
    content: str


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float


@dataclass
class FakeResponse:
    model: str
    choices: list[FakeChoice]
    usage: FakeUsage


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeChat:
    def __init__(self, outcomes):
        self.completions = FakeCompletions(outcomes)


class FakeClient:
    def __init__(self, outcomes):
        self.chat = FakeChat(outcomes)


def build_response(model: str, content: str, *, cost: float) -> FakeResponse:
    return FakeResponse(
        model=model,
        choices=[FakeChoice(message=FakeMessage(content=content))],
        usage=FakeUsage(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
            cost=cost,
        ),
    )


def test_call_openrouter_returns_response_and_persists_usage(tmp_path: Path) -> None:
    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    client = FakeClient(
        [build_response("anthropic/claude-haiku-4.5", "hello world", cost=0.0012)]
    )

    response = call_openrouter(
        "Summarize this",
        model="anthropic/claude-haiku-4.5",
        max_tokens=128,
        client=client,
        db_path=db_path,
    )

    assert response.content == "hello world"
    assert response.tokens_in == 11
    assert response.tokens_out == 7
    assert response.cost_usd == 0.0012

    db = init_db(db_path)
    rows = list(db["llm_calls"].rows)
    assert len(rows) == 1
    assert rows[0]["model"] == "anthropic/claude-haiku-4.5"
    assert rows[0]["success"] == 1


def test_call_openrouter_falls_back_on_primary_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "andyjuan.db"
    init_db(db_path)
    client = FakeClient(
        [
            RuntimeError("primary failed"),
            build_response(
                "anthropic/claude-haiku-4.5", "fallback answer", cost=0.0008
            ),
        ]
    )

    response = call_openrouter(
        "Summarize this",
        model="anthropic/claude-sonnet-4-6",
        max_tokens=128,
        fallback_model="anthropic/claude-haiku-4.5",
        client=client,
        db_path=db_path,
    )

    assert response.model == "anthropic/claude-haiku-4.5"
    assert response.content == "fallback answer"

    db = init_db(db_path)
    rows = list(db["llm_calls"].rows)
    assert len(rows) == 2
    assert rows[0]["success"] == 0
    assert rows[1]["success"] == 1
