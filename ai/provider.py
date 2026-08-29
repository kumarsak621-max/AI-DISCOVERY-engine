"""AI provider abstraction. Collectors and the database never import Gemini or OpenRouter directly."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

from ai.openrouter import OpenRouterClient, OpenRouterError, _redact, extract_json_object
from config import DEFAULT_GEMINI_MODEL, DEFAULT_MODEL, MAX_RETRIES, REQUEST_TIMEOUT_SECONDS, RETRY_BACKOFF_SECONDS

logger = logging.getLogger(__name__)

GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class AIProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        provider: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.provider = provider


class GeminiClient:
    """Google Gemini via the public Generative Language REST API (no key in logs)."""

    provider_name = "Gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.temperature = temperature
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def missing_key_message(self) -> str:
        return "Gemini API key is not configured."

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise AIProviderError(self.missing_key_message(), status_code=401, provider="Gemini")
        url = GEMINI_GENERATE_URL.format(model=self.model)
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        if extra_payload:
            body.update(extra_payload)
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    url,
                    params={"key": self.api_key},
                    json=body,
                    timeout=self.timeout,
                )
                if response.status_code in {401, 403}:
                    raise AIProviderError(
                        "Gemini API key was rejected.",
                        status_code=response.status_code,
                        provider="Gemini",
                    )
                if response.status_code == 429:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    last_error = AIProviderError("Gemini rate limited", status_code=429, retryable=True, provider="Gemini")
                    continue
                if response.status_code >= 500:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    last_error = AIProviderError(
                        f"Gemini server error {response.status_code}",
                        status_code=response.status_code,
                        retryable=True,
                        provider="Gemini",
                    )
                    continue
                if response.status_code >= 400:
                    raise AIProviderError(
                        f"Gemini error {response.status_code}",
                        status_code=response.status_code,
                        provider="Gemini",
                    )
                payload = response.json()
                parts = (
                    payload.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])
                )
                text = ""
                if parts:
                    text = str(parts[0].get("text") or "")
                return extract_json_object(text)
            except AIProviderError:
                raise
            except (requests.RequestException, ValueError, json.JSONDecodeError, KeyError, IndexError) as exc:
                last_error = AIProviderError(_redact(str(exc)), retryable=True, provider="Gemini")
                logger.warning("Gemini call failed on attempt %s: %s", attempt, _redact(str(exc)))
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise last_error or AIProviderError("Gemini request failed", provider="Gemini")


def missing_key_message(provider: str) -> str:
    if str(provider).lower() == "gemini":
        return "Gemini API key is not configured."
    return "OpenRouter API key is not configured."


def get_llm_client(
    provider: str,
    *,
    openrouter_key: str = "",
    gemini_key: str = "",
    model: str = "",
    temperature: float = 0.1,
):
    """Return a client with complete_json / is_configured. Never silently switches providers."""
    name = (provider or "openrouter").strip().lower()
    if name == "gemini":
        client = GeminiClient(api_key=gemini_key, model=model or DEFAULT_GEMINI_MODEL, temperature=temperature)
        return client
    return OpenRouterClient(
        api_key=openrouter_key,
        model=model or DEFAULT_MODEL,
        temperature=temperature,
    )


def provider_display_name(provider: str) -> str:
    return "Gemini" if str(provider).lower() == "gemini" else "OpenRouter"
