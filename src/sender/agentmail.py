"""Thin AgentMail sender wrapper."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentmail import AgentMail
from agentmail.attachments.types.send_attachment import SendAttachment
from bs4 import BeautifulSoup

from src.utils.log import get_logger

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
_LOGO_PATH = _ASSETS_DIR / "logo.png"
_LOGO_CID = "portfolio-radar-logo"


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
    html_payload, attachments = _prepare_inline_attachments(html)
    send_kwargs: dict[str, Any] = {
        "to": recipients,
        "subject": subject,
        "html": html_payload,
        "text": text,
        "headers": {"From": from_addr},
    }
    if attachments:
        send_kwargs["attachments"] = attachments
    try:
        response = (client or get_agentmail_client()).inboxes.messages.send(
            resolved_inbox_id,
            **send_kwargs,
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


def _prepare_inline_attachments(html: str) -> tuple[str, list[SendAttachment]]:
    soup = BeautifulSoup(html, "html.parser")
    logo = soup.select_one("img[alt='Portfolio Radar']")
    if logo is None:
        return html, []

    src = str(logo.get("src", "")).strip()
    if not src.startswith("data:image/png;base64,"):
        return html, []

    html_with_cid = html.replace(src, f"cid:{_LOGO_CID}", 1)
    return html_with_cid, [_logo_attachment()]


def _logo_attachment() -> SendAttachment:
    encoded_logo = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    return SendAttachment(
        filename="logo.png",
        content_type="image/png",
        content_disposition="inline",
        content_id=_LOGO_CID,
        content=encoded_logo,
    )
