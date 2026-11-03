"""Groq text generation with pooled HTTPS and provider-neutral reply metadata."""

from dataclasses import dataclass

import httpx


GROQ_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"}


class GenerationProviderError(RuntimeError):
    def __init__(self, code: int | None = None, kind: str = "unavailable"):
        super().__init__("Generation service is unavailable.")
        self.code = code
        self.kind = kind


@dataclass
class GenerationUsage:
    prompt_token_count: int | None = None
    candidates_token_count: int | None = None
    thoughts_token_count: int | None = None
    total_token_count: int | None = None


@dataclass
class GenerationReply:
    text: str
    blocked: bool = False
    usage_metadata: GenerationUsage | None = None


class GroqClient:
    def __init__(self, api_key: str, *, transport=None):
        if not api_key.strip():
            raise ValueError("GROQ_API_KEY is required.")
        self._http = httpx.Client(
            base_url="https://api.groq.com/openai/v1/",
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=httpx.Timeout(4.0, connect=1.0, pool=0.5),
            follow_redirects=False,
            transport=transport,
        )

    def close(self):
        self._http.close()

    def generate(self, *, model: str, contents: str, config) -> GenerationReply:
        if model not in GROQ_MODELS:
            raise ValueError("Unsupported Groq generation model.")
        try:
            response = self._http.post("chat/completions", json={
                "model": model,
                "messages": [{"role": "system", "content": config.system_instruction},
                             {"role": "user", "content": contents}],
                "temperature": config.temperature,
                "reasoning_effort": "none" if model.startswith("qwen/") else "low",
                "include_reasoning": False,
                "max_completion_tokens": 1024,
            })
        except httpx.HTTPError:
            raise GenerationProviderError(kind="transport") from None
        if response.status_code != 200:
            # Provider error bodies can echo submitted content. Keep only the status.
            raise GenerationProviderError(response.status_code) from None
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            if choice["finish_reason"] == "content_filter" or message.get("refusal"):
                return GenerationReply("", blocked=True)
            if choice["finish_reason"] != "stop":
                raise GenerationProviderError(kind="incomplete")
            answer = message.get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise GenerationProviderError(kind="empty")
            usage = data.get("usage") or {}

            def count(key):
                value = usage.get(key)
                return value if type(value) is int and value >= 0 else None

            return GenerationReply(answer.strip(), usage_metadata=GenerationUsage(
                prompt_token_count=count("prompt_tokens"), candidates_token_count=count("completion_tokens"),
                total_token_count=count("total_tokens"),
            ))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise GenerationProviderError(kind="malformed") from None
