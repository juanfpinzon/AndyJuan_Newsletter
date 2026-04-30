from __future__ import annotations

from src.sender.agentmail import SendResult


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


def _fake_result():
    return type(
        "Result",
        (),
        {"send_result": SendResult(message_id="msg_123")},
    )()
