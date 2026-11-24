"""Model backends. Each exposes `name` and `complete(system, user) -> str`."""
from __future__ import annotations

import os
import time
from typing import Callable


class Backend:
    name = "backend"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def complete_batch(self, requests: list[tuple[str, str]]) -> list[str]:
        return [self.complete(system, user) for system, user in requests]


class MockBackend(Backend):
    """Deterministic stand-in for tests: `fn(system, user) -> str`."""

    def __init__(self, fn: Callable[[str, str], str], name: str = "mock"):
        self.fn, self.name = fn, name

    def complete(self, system: str, user: str) -> str:
        return self.fn(system, user)


class OpenAICompatibleBackend(Backend):
    """Any OpenAI-compatible chat endpoint (OpenAI, Gemini, OpenRouter, Groq, vLLM, Ollama)."""

    def __init__(self, model: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY",
                 max_tokens: int = 1024, temperature: float = 0.0):
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key=os.environ.get(api_key_env, "unused"), max_retries=5)
        self.model, self.max_tokens, self.temperature, self.name = model, max_tokens, temperature, model

    def complete(self, system: str, user: str, waits=(5, 10, 20, 40, 60, 60)) -> str:
        """Retries overload, rate-limit and connection errors after each wait in `waits` (seconds)."""
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        for wait in (*waits, None):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                )
                return response.choices[0].message.content or ""
            except (InternalServerError, RateLimitError, APITimeoutError, APIConnectionError) as exc:
                # a daily quota will not reset within the retry window
                if wait is None or "PerDay" in str(exc):
                    raise
                time.sleep(wait)


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def gemini_backend(model: str = "gemini-2.5-flash", max_tokens: int = 16384) -> OpenAICompatibleBackend:
    """Gemini through its OpenAI-compatible endpoint; the key comes from GEMINI_API_KEY."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("set GEMINI_API_KEY to use a Gemini model")
    return OpenAICompatibleBackend(model, base_url=GEMINI_BASE_URL, api_key_env="GEMINI_API_KEY",
                                   max_tokens=max_tokens)
