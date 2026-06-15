"""
Anthropic Claude adapter.

Claude uses the Messages API: the system prompt is a top-level `system` field
(not a message), and `max_tokens` is required.

POST https://api.anthropic.com/v1/messages
x-api-key: <KEY>
anthropic-version: 2023-06-01
{
  "model": "claude-3-5-sonnet-latest",
  "system": "<persona / wrapper>",
  "max_tokens": 512,
  "temperature": 0.7,
  "messages": [{"role": "user", "content": "..."}]
}

Response: content[0].text + usage.{input,output}_tokens
"""

from __future__ import annotations

from providers.base import BaseAIAdapter, CompletionResult, ProviderError


class AnthropicAdapter(BaseAIAdapter):
    default_base_url = "https://api.anthropic.com/v1"
    api_version = "2023-06-01"

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> CompletionResult:
        # Anthropic only accepts user/assistant roles in `messages`.
        wire_messages = [
            {"role": "assistant" if m["role"] == "assistant" else "user",
             "content": m["content"]}
            for m in messages
        ]

        payload = {
            "model": model,
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": wire_messages,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
        }

        data = await self._post_json(
            f"{self.base_url}/messages", headers=headers, payload=payload
        )

        try:
            text = "".join(
                block.get("text", "")
                for block in data["content"]
                if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Malformed Anthropic response: {data}") from exc

        usage = data.get("usage", {}) or {}
        return CompletionResult(
            text=text.strip(),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            raw=data,
        )
