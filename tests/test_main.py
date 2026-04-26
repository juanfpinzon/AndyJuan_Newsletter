from __future__ import annotations

from src.sender.agentmail import SendResult


def test_main_routes_daily_mode(monkeypatch) -> None:
    import src.main as main

    calls: list[str] = []
    monkeypatch.setattr(
        main,
        "run_daily",
        lambda **kwargs: calls.append("daily") or _fake_result(),
    )
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: calls.append("deep") or _fake_result(),
    )

    exit_code = main.main(["--mode", "daily"])

    assert exit_code == 0
    assert calls == ["daily"]


def test_main_routes_deep_mode(monkeypatch) -> None:
    import src.main as main

    calls: list[str] = []
    monkeypatch.setattr(
        main,
        "run_daily",
        lambda **kwargs: calls.append("daily") or _fake_result(),
    )
    monkeypatch.setattr(
        main,
        "run_deep",
        lambda **kwargs: calls.append("deep") or _fake_result(),
    )

    exit_code = main.main(["--mode", "deep"])

    assert exit_code == 0
    assert calls == ["deep"]


def _fake_result():
    return type(
        "Result",
        (),
        {"send_result": SendResult(message_id="msg_123")},
    )()
