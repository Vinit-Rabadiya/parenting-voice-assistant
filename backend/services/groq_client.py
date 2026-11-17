"""Groq text generation with pooled HTTPS and provider-neutral reply metadata."""

from dataclasses import dataclass
import json
import time

import httpx


GROQ_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"}


class GenerationProviderError(RuntimeError):
    def __init__(self, code: int | None = None, kind: str = "unavailable", *, retry_after_seconds=None):
        super().__init__("Generation service is unavailable.")
        self.code = code
        self.kind = kind
        self.retry_after_seconds = retry_after_seconds


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


@dataclass
class GenerationChunk:
    text: str = ""
    done: bool = False
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

    @staticmethod
    def _payload(model, contents, config):
        if model not in GROQ_MODELS:
            raise ValueError("Unsupported Groq generation model.")
        max_tokens = getattr(config, "max_output_tokens", None) or 1024
        # Preserve the original reasoning allowance for GPT-OSS. Its completion
        # budget also needs room for internal reasoning, unlike the Qwen mode.
        if not model.startswith("qwen/"):
            max_tokens = max(1024, max_tokens)
        return {
            "model": model,
            "messages": [{"role": "system", "content": config.system_instruction},
                         {"role": "user", "content": contents}],
            "temperature": config.temperature,
            "reasoning_effort": "none" if model.startswith("qwen/") else "low",
            "include_reasoning": False,
            "max_completion_tokens": max_tokens,
        }

    def generate_stream(self, *, model: str, contents: str, config):
        """Yield real provider deltas; reject truncation and close HTTP on cancellation."""
        payload = {**self._payload(model, contents, config), "stream": True}
        started, characters = time.monotonic(), 0
        finished, blocked, usage = False, False, None
        try:
            with self._http.stream("POST", "chat/completions", json=payload) as response:
                if response.status_code != 200:
                    raise GenerationProviderError(response.status_code, retry_after_seconds=response.headers.get("Retry-After"))
                lines = []
                for line in response.iter_lines():
                    if time.monotonic() - started > 45:
                        raise GenerationProviderError(kind="timeout")
                    if len(line) > 65536:
                        raise GenerationProviderError(kind="malformed")
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip(" "))
                        if sum(map(len, lines)) > 65536:
                            raise GenerationProviderError(kind="malformed")
                        continue
                    if line or not lines:
                        continue
                    value, lines = "\n".join(lines), []
                    if value == "[DONE]":
                        if not finished:
                            raise GenerationProviderError(kind="incomplete")
                        yield GenerationChunk(done=True, blocked=blocked, usage_metadata=usage)
                        return
                    data = json.loads(value)
                    if data.get("error"):
                        raise GenerationProviderError(kind="stream_error")
                    raw_usage = data.get("usage") or (data.get("x_groq") or {}).get("usage")
                    if raw_usage:
                        def count(key):
                            value = raw_usage.get(key)
                            return value if type(value) is int and value >= 0 else None
                        usage = GenerationUsage(prompt_token_count=count("prompt_tokens"),
                                                candidates_token_count=count("completion_tokens"),
                                                total_token_count=count("total_tokens"))
                    choices = data.get("choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    if delta.get("refusal") or choice.get("finish_reason") == "content_filter":
                        blocked, finished = True, True
                    elif choice.get("finish_reason") is not None:
                        if choice["finish_reason"] != "stop":
                            raise GenerationProviderError(kind="incomplete")
                        finished = True
                    text = delta.get("content")
                    if text is not None and not isinstance(text, str):
                        raise GenerationProviderError(kind="malformed")
                    if text and not blocked:
                        characters += len(text)
                        if characters > 16000:
                            raise GenerationProviderError(kind="incomplete")
                        yield GenerationChunk(text=text)
                raise GenerationProviderError(kind="incomplete")
        except httpx.HTTPError:
            raise GenerationProviderError(kind="transport") from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise GenerationProviderError(kind="malformed") from None

    def generate(self, *, model: str, contents: str, config) -> GenerationReply:
        payload = self._payload(model, contents, config)
        try:
            response = self._http.post("chat/completions", json=payload)
        except httpx.HTTPError:
            raise GenerationProviderError(kind="transport") from None
        if response.status_code != 200:
            # Provider error bodies can echo submitted content. Keep only the status.
            raise GenerationProviderError(response.status_code, retry_after_seconds=response.headers.get("Retry-After")) from None
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
