"""OpenRouter client — missing key and JSON helpers."""

import pytest

from ai.openrouter import OpenRouterClient, OpenRouterError, analyze_batch


def test_missing_api_key_is_not_configured() -> None:
    client = OpenRouterClient(api_key="")
    assert client.is_configured is False
    with pytest.raises(OpenRouterError) as exc:
        client.analyze_conversation("sys", "user")
    assert exc.value.status_code == 401
    assert exc.value.retryable is False


def test_analyze_batch_isolates_failures(monkeypatch) -> None:
    client = OpenRouterClient(api_key="test-key")
    calls = {"n": 0}

    def fake_complete(system_prompt, user_prompt, extra_payload=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OpenRouterError("boom", status_code=500, retryable=True)
        return {"relevant": True}

    monkeypatch.setattr(client, "complete_json", fake_complete)
    results = client.analyze_batch([("s", "u1"), ("s", "u2")])
    assert results[0] is None
    assert results[1] == {"relevant": True}


def test_module_analyze_batch_uses_client(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    client = OpenRouterClient(api_key="")
    assert analyze_batch([], api_key="") == []
    assert client.analyze_batch([]) == []
