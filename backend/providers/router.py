"""
AIRouter — the adapter-pattern factory.

Maps a `Provider.adapter_type` string to a concrete adapter class and builds a
ready-to-use instance (with the provider's decrypted key + base URL). New
vendors are added by writing an adapter and registering it in `_REGISTRY`.
"""

from __future__ import annotations

from providers.anthropic import AnthropicAdapter
from providers.base import BaseAIAdapter
from providers.gemini import GeminiAdapter
from providers.openai_compatible import CustomAdapter, GroqAdapter, OpenAIAdapter

# adapter_type -> adapter class
_REGISTRY: dict[str, type[BaseAIAdapter]] = {
    "groq": GroqAdapter,
    "gemini": GeminiAdapter,
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "custom": CustomAdapter,
}


def register_adapter(adapter_type: str, adapter_cls: type[BaseAIAdapter]) -> None:
    """Allow runtime/plugin registration of new providers."""
    _REGISTRY[adapter_type] = adapter_cls


def available_adapter_types() -> list[str]:
    return sorted(_REGISTRY)


def get_adapter_for_provider(provider) -> BaseAIAdapter:
    """Build an adapter instance from a core.models.Provider row.

    NOTE: accessing `provider.api_key` decrypts it in-process only.
    """
    try:
        adapter_cls = _REGISTRY[provider.adapter_type]
    except KeyError as exc:
        raise ValueError(
            f"No adapter registered for provider type '{provider.adapter_type}'. "
            f"Known: {available_adapter_types()}"
        ) from exc

    return adapter_cls(api_key=provider.api_key, base_url=provider.base_url)
