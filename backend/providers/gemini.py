"""
Google Gemini adapter.

Gemini's REST surface differs from OpenAI in three ways:
  1. The model id is part of the URL path, not the body.
  2. The API key is a `?key=` query parameter (or x-goog-api-key header).
  3. The persona goes into `system_instruction`, and turns use {"role": "user"
     |"model", "parts": [{"text": ...}]} — note "model" instead of "assistant".

Exact request structure
-----------------------
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=<KEY>
Content-Type: application/json
{
  "system_instruction": {"parts": [{"text": "<persona / wrapper>"}]},
  "contents": [
    {"role": "user",  "parts": [{"text": "Sokrates: What is justice?"}]},
    {"role": "model", "parts": [{"text": "Plato: Justice is harmony..."}]}
  ],
  "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512}
}

Response: candidates[0].content.parts[*].text + usageMetadata.*
"""

from __future__ import annotations

from providers.base import BaseAIAdapter, CompletionResult, ProviderError


class GeminiAdapter(BaseAIAdapter):
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    @staticmethod
    def _to_gemini_role(role: str) -> str:
        # OpenAI "assistant" => Gemini "model"; everything else => "user".
        return "model" if role == "assistant" else "user"

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> CompletionResult:
        contents = [
            {
                "role": self._to_gemini_role(m["role"]),
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        # Model id lives in the path; key as query param.
        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        data = await self._post_json(url, headers=headers, payload=payload)

        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError) as exc:
            # Gemini may return no candidate when the prompt is blocked.
            raise ProviderError(f"Malformed Gemini response: {data}") from exc

        usage = data.get("usageMetadata", {}) or {}
        return CompletionResult(
            text=text.strip(),
            prompt_tokens=usage.get("promptTokenCount", 0),
            completion_tokens=usage.get("candidatesTokenCount", 0),
            raw=data,
        )
