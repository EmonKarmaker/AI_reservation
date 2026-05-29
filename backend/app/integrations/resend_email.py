"""Resend email integration.

Module is named ``resend_email.py`` (not ``resend.py``) to avoid a name
collision with the ``resend`` PyPI package — importing ``app.integrations.resend``
would shadow the SDK and break our own imports.

SDK shape: the resend package uses a module-level pattern, not a class:

    import resend
    resend.api_key = "re_..."
    result = resend.Emails.send({"from": ..., "to": [...], ...})

We wrap it so callers don't depend on those module globals.

Why a thin wrapper:
- The Resend Python SDK is synchronous. Calling it from an async node would
  block the event loop. We use ``asyncio.to_thread`` to run the send on a
  worker thread so the chatbot stays responsive.
- A single ``send_email`` entrypoint keeps the SDK contained: if Resend ever
  changes API shape or we swap providers, only this file changes.
- The wrapper raises ``EmailError`` on failure. Callers catch it and decide
  whether to retry, log, or surface to the user. The chatbot's pattern is
  always best-effort: log + continue.

Configuration (from app.config.settings):
- ``RESEND_API_KEY``: must be set; if empty, ``send_email`` raises EmailError
  on first call. Lets the dev path stay quiet (no boot-time crash) but
  surfaces clearly when escalation actually fires.
- ``RESEND_FROM_EMAIL``: the From address. Defaults to ``onboarding@resend.dev``
  (Resend's verified sandbox sender — works for any developer without
  domain verification, but only delivers to the address you signed up with).
- ``RESEND_REPLY_TO``: optional Reply-To. Empty string means no Reply-To
  header (the recipient replies to the From address).
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings


logger = logging.getLogger(__name__)


class EmailError(RuntimeError):
    """Raised when a Resend send fails for any reason."""


# Module-level latch: we set ``resend.api_key`` once per process, then leave
# it alone. ``_ensure_configured`` is idempotent.
_api_key_set: bool = False


def _ensure_configured() -> None:
    """Set the SDK's module-level api_key on first use. Idempotent."""
    global _api_key_set
    if _api_key_set:
        return

    if not settings.RESEND_API_KEY:
        raise EmailError(
            "RESEND_API_KEY is not set. Add it to backend/.env before sending email."
        )

    import resend

    resend.api_key = settings.RESEND_API_KEY
    _api_key_set = True


def _send_sync(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> str:
    """Synchronous send. Returns the Resend message ID on success.

    Called from ``send_email`` via ``asyncio.to_thread``. Raises EmailError
    on any failure.
    """
    _ensure_configured()

    # Imported here (after ensure_configured ran) so the api_key is set.
    import resend

    params: dict = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        params["reply_to"] = [reply_to]

    try:
        # SDK shape: resend.Emails.send(params) -> {"id": "re_...", ...}
        result = resend.Emails.send(params)
    except Exception as exc:  # noqa: BLE001 — wrap any SDK/network error
        raise EmailError(f"Resend send failed: {exc}") from exc

    # The SDK returns either a dict or an Email object depending on version.
    # Normalise both: prefer dict-style .get, fall back to attribute access.
    message_id: str | None = None
    if isinstance(result, dict):
        message_id = result.get("id")
    else:
        message_id = getattr(result, "id", None)

    if not message_id:
        raise EmailError(f"Resend returned unexpected response: {result!r}")

    return str(message_id)


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> str:
    """Send an email via Resend. Returns the message ID on success.

    Args:
        to: Recipient email. Must be a single address. For multi-recipient
            sends, call this multiple times (Resend bills per address
            anyway, so there's no benefit to bundling).
        subject: Email subject line.
        html: HTML body. No templating engine — caller assembles the string.
        reply_to: Optional Reply-To address. Defaults to settings.RESEND_REPLY_TO
                  if not provided; both empty means no header.

    Raises:
        EmailError: on any underlying failure (auth, network, validation).
                    Callers using the best-effort pattern should catch this.
    """
    effective_reply_to = reply_to if reply_to is not None else (
        settings.RESEND_REPLY_TO or None
    )

    return await asyncio.to_thread(
        _send_sync,
        to=to,
        subject=subject,
        html=html,
        reply_to=effective_reply_to,
    )
