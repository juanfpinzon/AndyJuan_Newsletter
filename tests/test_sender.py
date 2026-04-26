from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sender.agentmail import EmailSendError, SendResult, send_email


class _StubMessagesClient:
    def __init__(
        self, *, response: object | None = None, error: Exception | None = None
    ):
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def send(self, inbox_id: str, **kwargs: object) -> object:
        self.calls.append({"inbox_id": inbox_id, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response


class _StubInboxesClient:
    def __init__(self, messages_client: _StubMessagesClient) -> None:
        self.messages = messages_client


class _StubAgentMailClient:
    def __init__(self, messages_client: _StubMessagesClient) -> None:
        self.inboxes = _StubInboxesClient(messages_client)


class _StubSendResponse:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


def test_send_email_sends_html_and_text_and_logs_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_file = tmp_path / "andyjuan.jsonl"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AGENTMAIL_INBOX_ID", "inbox_123")

    messages_client = _StubMessagesClient(response=_StubSendResponse("msg_123"))
    client = _StubAgentMailClient(messages_client)

    result = send_email(
        to=["juan@example.com", "andrea@example.com"],
        subject="Daily Portfolio Radar",
        html="<p>Hello</p>",
        text="Hello",
        from_addr="radar@example.com",
        client=client,
    )

    assert result == SendResult(message_id="msg_123")
    assert messages_client.calls == [
        {
            "inbox_id": "inbox_123",
            "to": ["juan@example.com", "andrea@example.com"],
            "subject": "Daily Portfolio Radar",
            "html": "<p>Hello</p>",
            "text": "Hello",
            "headers": {"From": "radar@example.com"},
        }
    ]

    payload = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["event"] == "email_sent"
    assert payload["message_id"] == "msg_123"
    assert payload["recipients"] == ["juan@example.com", "andrea@example.com"]


def test_send_email_wraps_agentmail_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTMAIL_INBOX_ID", "inbox_123")
    messages_client = _StubMessagesClient(error=RuntimeError("AgentMail unavailable"))
    client = _StubAgentMailClient(messages_client)

    with pytest.raises(EmailSendError, match="AgentMail unavailable"):
        send_email(
            to="juan@example.com",
            subject="Daily Portfolio Radar",
            html="<p>Hello</p>",
            text="Hello",
            from_addr="radar@example.com",
            client=client,
        )
