"""OpenRouter client with retries, JSON extraction, and redacted logging."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import requests

from config import DEFAULT_MODEL, MAX_RETRIES, OPENROUTER_API_URL, REQUEST_TIMEOUT_SECONDS, RETRY_BACKOFF_SECONDS

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


class OpenRouterError(Exception):
    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _redact(text: str) -> str:
    return re.sub(r"(sk-|or-)[A-Za-z0-9_\-]+", "[REDACTED]", text)


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM response, including fenced or trailing-text cases."""
    if not text or not text.strip():
        raise ValueError("Empty model response")
    stripped = text.strip()
    fenced = _JSON_FENCE_RE.search(stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("JSON root is not an object")
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(stripped[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        raise


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if api_key is None:
            self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        else:
            self.api_key = str(api_key)
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
        self.temperature = temperature
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    def missing_key_message(self) -> str:
        return "OpenRouter API key is not configured."

    @property
    def provider_name(self) -> str:
        return "OpenRouter"

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise OpenRouterError("OpenRouter API key is not configured.", status_code=401, retryable=False)

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if extra_payload:
            payload.update(extra_payload)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Myntra Wishlist Conversion Discovery Engine",
        }

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code == 401:
                    raise OpenRouterError("Invalid OpenRouter API key", status_code=401, retryable=False)
                if response.status_code == 429:
                    wait = RETRY_BACKOFF_SECONDS * attempt
                    logger.warning("OpenRouter rate limited; retrying in %ss", wait)
                    time.sleep(wait)
                    last_error = OpenRouterError("Rate limited", status_code=429, retryable=True)
                    continue
                if response.status_code >= 500:
                    wait = RETRY_BACKOFF_SECONDS * attempt
                    logger.warning("OpenRouter server error %s; retrying", response.status_code)
                    time.sleep(wait)
                    last_error = OpenRouterError(
                        f"Server error {response.status_code}",
                        status_code=response.status_code,
                        retryable=True,
                    )
                    continue
                if response.status_code >= 400:
                    raise OpenRouterError(
                        f"OpenRouter error {response.status_code}",
                        status_code=response.status_code,
                        retryable=False,
                    )
                body = response.json()
                content = body.get("choices", [{}])[0].get("message", {}).get("content") or ""
                return extract_json_object(content)
            except OpenRouterError:
                raise
            except requests.Timeout as exc:
                last_error = OpenRouterError("OpenRouter timeout", retryable=True)
                logger.warning("OpenRouter timeout on attempt %s: %s", attempt, exc)
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            except (requests.RequestException, ValueError, json.JSONDecodeError, KeyError, IndexError) as exc:
                last_error = OpenRouterError(_redact(str(exc)), retryable=True)
                logger.warning("OpenRouter call failed on attempt %s: %s", attempt, _redact(str(exc)))
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise last_error or OpenRouterError("OpenRouter request failed")

    def analyze_conversation(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self.complete_json(system_prompt, user_prompt)

    def analyze_batch(self, items: list[tuple[str, str]]) -> list[dict[str, Any] | None]:
        """Analyze many prompt pairs. One failure does not abort the rest."""
        results: list[dict[str, Any] | None] = []
        for system_prompt, user_prompt in items:
            try:
                results.append(self.analyze_conversation(system_prompt, user_prompt))
            except OpenRouterError as exc:
                logger.warning("analyze_batch item failed: %s", _redact(str(exc)))
                results.append(None)
        return results

    def generate_theme_analysis(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self.complete_json(system_prompt, user_prompt)

    def generate_opportunity_analysis(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self.complete_json(system_prompt, user_prompt)

    def generate_research_brief(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self.complete_json(system_prompt, user_prompt)


def analyze_conversation(system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
    return OpenRouterClient(**kwargs).analyze_conversation(system_prompt, user_prompt)


def analyze_batch(items: list[tuple[str, str]], **kwargs: Any) -> list[dict[str, Any] | None]:
    return OpenRouterClient(**kwargs).analyze_batch(items)


def generate_theme_analysis(system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
    return OpenRouterClient(**kwargs).generate_theme_analysis(system_prompt, user_prompt)


def generate_opportunity_analysis(system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
    return OpenRouterClient(**kwargs).generate_opportunity_analysis(system_prompt, user_prompt)


def generate_research_brief(system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
    return OpenRouterClient(**kwargs).generate_research_brief(system_prompt, user_prompt)
