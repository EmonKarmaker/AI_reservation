"""Groq LLM client and thin chat-completion wrapper.

Two model tiers, both configured via settings:

- ``GROQ_MODEL_FAST``  (default: llama-3.1-8b-instant) — for intent
  classification, slot extraction, and other latency-sensitive low-stakes
  calls. ~1 s response time on simple prompts.

- ``GROQ_MODEL_SMART`` (default: llama-3.3-70b-versatile) — for question
  answering, drafting messages, anything that needs reasoning over the
  business's services + FAQs. ~2-4 s response time.

The client is a module-level singleton, created lazily on first use, so
importing this module is cheap and tests that don't hit the LLM don't need
a real API key.

Public surface:
- ``chat_completion(messages, model, ...)`` — returns the raw text content
  of the assistant's reply. Synchronous in the sense that it awaits the
  network call but returns a single completed string (no streaming).
- ``LLMError`` — raised on any underlying API/network failure.

Why no streaming yet: the chatbot endpoint will block on the LLM and return
the full response; streaming UX is a polish-pass concern. We can swap to the
streaming variant later without changing callers if we keep this façade.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from groq import AsyncGroq


logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when a Groq call fails for any reason (network, auth, ratelimit)."""


_client: "AsyncGroq | None" = None


def _get_client() -> "AsyncGroq":
    """Return the singleton AsyncGroq client.

    Constructed on first use so that importing this module doesn't require
    GROQ_API_KEY to be set (handy for tests that don't touch the LLM).
    """
    global _client
    if _client is not None:
        return _client

    if not settings.GROQ_API_KEY:
        raise LLMError(
            "GROQ_API_KEY is not set. Add it to backend/.env before using the LLM."
        )

    # Lazy import — keeps the groq SDK out of cold-import paths.
    from groq import AsyncGroq

    _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

ChatMessage = dict[str, str]  # {"role": "system|user|assistant", "content": "..."}


async def chat_completion(
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Send a chat completion request to Groq and return the assistant's text.

    Args:
        messages: OpenAI-style list of role/content dicts. Roles: system,
                  user, assistant. The list must be non-empty.
        model:    Groq model id. Defaults to ``settings.GROQ_MODEL_SMART``.
                  Pass ``settings.GROQ_MODEL_FAST`` for latency-sensitive
                  classification calls.
        temperature: 0.0 = deterministic, higher = more creative. 0.3 is a
                  good default for grounded conversational responses where
                  we don't want hallucinated facts but do want natural
                  phrasing.
        max_tokens: Cap on response length. 1024 is plenty for chat replies;
                  raise for long-form generation.

    Returns:
        The text content of the assistant's reply.

    Raises:
        LLMError: on any underlying API/network/auth failure. Callers
                  decide whether to retry, surface the error to the user,
                  or fall back to a canned response.
    """
    if not messages:
        raise LLMError("messages must be non-empty")

    client = _get_client()
    target_model = model or settings.GROQ_MODEL_SMART

    try:
        response = await client.chat.completions.create(
            model=target_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 — wrap any SDK/network error
        logger.warning("Groq chat_completion failed: %s", exc)
        raise LLMError(str(exc)) from exc

    if not response.choices:
        raise LLMError("Groq returned no choices")

    content = response.choices[0].message.content
    if not content:
        raise LLMError("Groq returned an empty message")

    return content
