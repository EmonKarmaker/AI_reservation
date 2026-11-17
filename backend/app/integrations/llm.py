"""Groq LLM client and thin chat-completion wrapper.

Two model tiers, both configured via settings:

- ``GROQ_MODEL_FAST``  (default: openai/gpt-oss-20b) — for slot matching
  and other latency-sensitive low-stakes calls.

- ``GROQ_MODEL_SMART`` (default: openai/gpt-oss-120b) — for intent
  classification, date parsing, question answering, anything that needs
  reasoning over the business's services + FAQs.

The original Llama defaults (llama-3.1-8b-instant / llama-3.3-70b-versatile)
were shut down by Groq on 2026-08-16.

Reasoning models: gpt-oss (and Qwen3) "think" before answering, and those
thinking tokens count against ``max_tokens``. Callers in this codebase ask
for tiny outputs (``max_tokens=10`` for a one-word label), which would leave
no room for the answer and come back empty. ``chat_completion`` therefore
asks reasoning models for low reasoning effort, hides the reasoning text,
and raises the token budget to at least ``REASONING_MIN_TOKENS``. Callers
keep passing the size of the answer they want; nothing else changes.

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
import re
from typing import TYPE_CHECKING, Any

from app.config import settings

if TYPE_CHECKING:
    from groq import AsyncGroq


logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when a Groq call fails for any reason (network, auth, ratelimit)."""


_client: "AsyncGroq | None" = None


# Model-id prefixes that produce hidden reasoning tokens before the answer.
_REASONING_MODEL_PREFIXES: tuple[str, ...] = ("openai/gpt-oss", "qwen/qwen3")

# Minimum completion budget for reasoning models. Low effort usually spends
# well under this on our short classification prompts; the rest is headroom.
REASONING_MIN_TOKENS = 1024

# Some reasoning models inline their thinking in <think>...</think>.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def is_reasoning_model(model: str) -> bool:
    """True if ``model`` emits reasoning tokens that eat into ``max_tokens``."""
    return model.lower().startswith(_REASONING_MODEL_PREFIXES)


def build_completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Assemble the keyword arguments for ``chat.completions.create``.

    Pure function so the reasoning-model handling can be unit-tested
    without a network call.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if is_reasoning_model(model):
        kwargs["max_tokens"] = max(max_tokens, REASONING_MIN_TOKENS)
        kwargs["reasoning_effort"] = "low"
        kwargs["include_reasoning"] = False
    return kwargs


def clean_completion_text(content: str) -> str:
    """Strip inline ``<think>`` blocks some reasoning models emit."""
    return _THINK_BLOCK_RE.sub("", content).strip()


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

    kwargs = build_completion_kwargs(
        model=target_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    try:
        response = await client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 — wrap any SDK/network error
        logger.warning("Groq chat_completion failed (model=%s): %s", target_model, exc)
        raise LLMError(str(exc)) from exc

    if not response.choices:
        raise LLMError("Groq returned no choices")

    content = clean_completion_text(response.choices[0].message.content or "")
    if not content:
        raise LLMError("Groq returned an empty message")

    return content
