"""
OpenAI-compatible adapters.

Groq, OpenAI itself, and most "custom" endpoints (Together, Perplexity, Ollama,
LM Studio, vLLM…) all speak the `POST /chat/completions` schema, so they share a
single implementation. Only the default base URL differs.

Exact request structure (Groq example)
--------------------------------------
POST https://api.groq.com/openai/v1/chat/completions
Authorization: Bearer <GROQ_API_KEY>
Content-Type: application/json
{
  "model": "llama3-70b-8192",
  "messages": [
    {"role": "system",    "content": "<persona / orchestration wrapper>"},
    {"role": "assistant", "content": "Einstein: Energy is..."},
    {"role": "user",      "content": "Sokrates: But what is energy?"}
  ],
  "temperature": 0.7,
  "max_tokens": 512
}

Response: choices[0].message.content + usage.{prompt,completion}_tokens
"""

from __future__ import annotations

from providers.base import BaseAIAdapter, CompletionResult, ProviderError


class OpenAICompatibleAdapter(BaseAIAdapter):
    """Shared base for any vendor implementing the OpenAI chat schema."""

    default_base_url = "https://api.openai.com/v1"

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> CompletionResult:
        # The system/persona message always leads the conversation.
        wire_messages = [{"role": "system", "content": system_prompt}, *messages]

        payload = {
            "model": model,
            "messages": wire_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = await self._post_json(
            f"{self.base_url}/chat/completions", headers=headers, payload=payload
        )

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"Malformed completion response: {data}") from exc

        usage = data.get("usage", {}) or {}
        return CompletionResult(
            text=text.strip(),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            raw=data,
        )


class GroqAdapter(OpenAICompatibleAdapter):
    """Groq — fast Llama / Mixtral / Gemma inference, OpenAI-compatible."""

    default_base_url = "https://api.groq.com/openai/v1"


class OpenAIAdapter(OpenAICompatibleAdapter):
    """Vanilla OpenAI (gpt-4o, gpt-4o-mini, …)."""

    default_base_url = "https://api.openai.com/v1"


class CustomAdapter(OpenAICompatibleAdapter):
    """Any self-hosted / third-party OpenAI-compatible endpoint.

    The base URL MUST be provided on the Provider record (no default).
    """

    default_base_url = ""
