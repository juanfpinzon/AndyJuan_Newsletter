"""Delivery components."""

from .agentmail import EmailSendError, SendResult, get_agentmail_client, send_email

__all__ = [
    "EmailSendError",
    "SendResult",
    "get_agentmail_client",
    "send_email",
]
