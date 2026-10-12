"""Point d'entrée unique pour les appels au serveur LLM local."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Sequence

import requests

logger = logging.getLogger("onyx.llm")


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str
    elapsed_ms: int
    estimated_cost: float = 0.0


class LLMService:
    def __init__(self, url: str, default_model: str, timeout: tuple[float, float] = (5.0, 120.0)):
        self.url = url
        self.default_model = default_model
        self.timeout = timeout
        self.session = requests.Session()

    def complete(self, messages: Sequence[dict[str, str]], *, model: str | None = None,
                 temperature: float = 0.2, max_tokens: int = 2048,
                 retries: int = 2) -> LLMResult:
        selected_model = model or self.default_model
        if max_tokens < 1 or max_tokens > 16_384:
            raise ValueError("max_tokens out of range")
        payload: dict[str, Any] = {"model": selected_model, "messages": list(messages),
                                   "temperature": temperature, "max_tokens": max_tokens}
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self.session.post(self.url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                elapsed = int((time.perf_counter() - started) * 1000)
                logger.info("llm.complete model=%s elapsed_ms=%s attempt=%s", selected_model, elapsed, attempt + 1)
                return LLMResult(str(content)[:100_000], selected_model, elapsed)
            except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
                last_error = exc
                logger.warning("llm.complete failed model=%s attempt=%s", selected_model, attempt + 1)
                if attempt < retries:
                    time.sleep(0.25 * (2 ** attempt))
        raise RuntimeError("LLM indisponible") from last_error
