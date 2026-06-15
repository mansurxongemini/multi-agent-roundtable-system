"""
Adapter-pattern foundation.

Every provider (Groq, Gemini, OpenAI, Anthropic, custom OpenAI-compatible
endpoints…) is wrapped by a subclass of `BaseAIAdapter`. The orchestration
engine depends ONLY on this interface, so adding a new vendor is a matter of
writing one small class and registering it in `providers.router`.

The interface is intentionally tiny:

    adapter.generate(messages, system_prompt, model, temperature, max_tokens)
        -> CompletionResult(text, prompt_tokens, completion_tokens, raw)

`messages` is a provider-neutral list of {"role": "user"|"assistant"|"system",
"content": str}. Each adapter translates it into the vendor's wire format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class CompletionResult:
    """Normalized response returned by every adapter."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a non-retryable way."""


class RateLimitError(ProviderError):
    """Raised on HTTP 429 so the engine can back off and retry."""


class BaseAIAdapter:
    """Common contract + shared HTTP plumbing for all providers."""

    #: Overridden by subclasses; used when Provider.base_url is blank.
    default_base_url: str = ""
    #: Per-request timeout (seconds).
    timeout: float = 60.0

    def __init__(self, api_key: str, base_url: str = ""):
        self.api_key = api_key
        self.base_url = (base_url or self.default_base_url).rstrip("/")

    # ── Public API (the only thing the engine calls) ─────────────────────
    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> CompletionResult:
        raise NotImplementedError

    # ── Shared helpers ───────────────────────────────────────────────────
    async def _post_json(
        self, url: str, *, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST JSON and translate transport errors into ProviderError types."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 429:
                raise RateLimitError(f"Rate limited by provider: {resp.text[:200]}")
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Provider returned {resp.status_code}: {resp.text[:300]}"
                )
            return resp.json()
