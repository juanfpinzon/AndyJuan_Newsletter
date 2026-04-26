"""Thin AgentMail sender wrapper."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agentmail import AgentMail

from src.utils.log import get_logger


@dataclass(frozen=True)
class SendResult:
    message_id: str


class EmailSendError(RuntimeError):
    """Raised when AgentMail cannot send the message."""


def send_email(
    to: str | list[str],
    subject: str,
    html: str,
    text: str,
    from_addr: str,
    *,
    client: Any | None = None,
    inbox_id: str | None = None,
) -> SendResult:
    """Send a multipart email via AgentMail."""

    resolved_inbox_id = inbox_id or os.getenv("AGENTMAIL_INBOX_ID")
    if not resolved_inbox_id:
        raise EmailSendError("AGENTMAIL_INBOX_ID is not set")

    recipients = [to] if isinstance(to, str) else list(to)
    try:
        response = (client or get_agentmail_client()).inboxes.messages.send(
            resolved_inbox_id,
            to=recipients,
            subject=subject,
            html=html,
            text=text,
            headers={"From": from_addr},
        )
    except Exception as exc:  # noqa: BLE001
        raise EmailSendError(str(exc)) from exc

    result = SendResult(message_id=str(getattr(response, "message_id", "")).strip())
    get_logger("sender").info(
        "email_sent",
        message_id=result.message_id,
        recipients=recipients,
    )
    return result


def get_agentmail_client() -> AgentMail:
    """Construct an AgentMail client from the environment."""

    api_key = os.getenv("AGENTMAIL_API_KEY")
    if not api_key:
        raise EmailSendError("AGENTMAIL_API_KEY is not set")
    return AgentMail(api_key=api_key)
