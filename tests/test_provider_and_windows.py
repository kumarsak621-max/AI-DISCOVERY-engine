"""30-month historical window and AI provider factory."""

from datetime import datetime, timezone

import pandas as pd
from dateutil.relativedelta import relativedelta

from ai.provider import GeminiClient, get_llm_client, missing_key_message
from analytics.metric_decomp import decompose_metric
from analytics.opportunities import multiplicative_framework_score
from processing.dates import days_covering_months, in_month_window, window_bounds_months


def test_thirty_months_is_not_thirty_reviews() -> None:
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    start, end = window_bounds_months(30, now=now)
    assert end == now
    assert start == now - relativedelta(months=30)
    days = days_covering_months(30, now=now)
    assert days > 800
    assert days < 1000


def test_in_month_window_excludes_older() -> None:
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    inside = now - relativedelta(months=12)
    outside = now - relativedelta(months=36)
    assert in_month_window(inside, 30, now=now) is True
    assert in_month_window(outside, 30, now=now) is False
    assert in_month_window(None, 30, now=now) is False


def test_gemini_missing_key_message() -> None:
    client = GeminiClient(api_key="")
    assert client.is_configured is False
    assert missing_key_message("gemini") == "Gemini API key is not configured."
    assert missing_key_message("openrouter") == "OpenRouter API key is not configured."


def test_provider_factory_does_not_switch() -> None:
    gemini = get_llm_client("gemini", openrouter_key="or-key", gemini_key="", model="gemini-2.0-flash")
    assert gemini.is_configured is False
    openrouter = get_llm_client("openrouter", openrouter_key="", gemini_key="gem-key")
    assert openrouter.is_configured is False


def test_metric_decomp_empty_does_not_invent() -> None:
    table = decompose_metric(pd.DataFrame())
    assert int(table["Evidence records"].sum()) == 0
    assert (table["Potential opportunity"] == "Insufficient evidence in the collected dataset.").all()


def test_multiplicative_score_zero_without_evidence() -> None:
    assert multiplicative_framework_score(0, 10, 80, 80, 0) == 0.0
    assert multiplicative_framework_score(5, 10, 100, 100, 20) > 0
