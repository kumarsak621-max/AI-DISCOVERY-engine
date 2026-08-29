"""Grounded Ask AI chatbot. Quotes always come from retrieved stored records."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ai.openrouter import OpenRouterClient, OpenRouterError
from analytics.retrieval import retrieve_records

CHAT_SYSTEM = """You are a product-discovery analyst for Myntra wishlist conversion.

You may ONLY use the numbered EVIDENCE RECORDS provided.
Do not use general knowledge about fashion or e-commerce.
Do not invent quotes, URLs, dates, or statistics.
If the records are insufficient, say so and set confidence to low.
Percentages, if any, are of these retrieved records — never of all Myntra users.

Return JSON:
{
  "direct_answer": "string",
  "key_insight": "string",
  "observed_pattern": "string",
  "confidence": "high|medium|low",
  "caveats": "string",
  "evidence_numbers": [1, 2]
}

evidence_numbers must be ids from the provided list. Do not quote text that is not in those records.
"""


def _clip(text: str, n: int = 700) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= n:
        return value
    return value[: n - 1] + "…"


def records_to_evidence(retrieved: pd.DataFrame) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(retrieved.iterrows(), start=1):
        original = str(row.get("original_text") or row.get("text") or "")
        quote = str(row.get("evidence_quote") or "").strip()
        if not quote or quote.lower() == "no direct evidence" or quote.lower() not in original.lower():
            quote = _clip(original, 280)
        items.append(
            {
                "n": i,
                "quote": quote,
                "source": str(row.get("source") or ""),
                "url": str(row.get("source_url") or ""),
                "date": str(row.get("published_at") or ""),
                "platform": str(row.get("source") or ""),
                "intent": str(row.get("purchase_intent") or ""),
                "problem": str(row.get("primary_problem") or ""),
                "text": original,
            }
        )
    return items


def answer_question(
    question: str,
    records: pd.DataFrame,
    *,
    api_key: str,
    model: str,
    period_label: str,
) -> dict[str, Any]:
    retrieved = retrieve_records(records, question, limit=8)
    evidence = records_to_evidence(retrieved)
    if records.empty:
        return {
            "direct_answer": "No real reviews were collected for this period.",
            "key_insight": "The chatbot has no stored public conversations to retrieve.",
            "observed_pattern": "—",
            "confidence": "low",
            "caveats": "Collect public conversations first. This answer is not based on Myntra user analytics.",
            "evidence": [],
            "n_records": 0,
            "sources": [],
            "period": period_label,
            "used_openrouter": False,
        }
    if retrieved.empty:
        return {
            "direct_answer": "Insufficient evidence in the collected dataset.",
            "key_insight": "No stored records matched this question closely enough to quote.",
            "observed_pattern": "—",
            "confidence": "low",
            "caveats": "The dataset may not contain reviews about this topic in the selected period.",
            "evidence": [],
            "n_records": 0,
            "sources": [],
            "period": period_label,
            "used_openrouter": False,
        }

    numbered = []
    for item in evidence:
        numbered.append(
            f"RECORD {item['n']}\n"
            f"source={item['source']} date={item['date']} url={item['url']}\n"
            f"intent={item['intent']} problem={item['problem']}\n"
            f"text={_clip(item['text'])}\n"
        )
    user_prompt = (
        f"QUESTION: {question}\n"
        f"{period_label}\n"
        f"Retrieved real records: {len(evidence)}\n\n"
        + "\n".join(numbered)
        + "\nAnswer using only these records."
    )

    client = OpenRouterClient(api_key=api_key, model=model, temperature=0.1)
    try:
        parsed = client.complete_json(CHAT_SYSTEM, user_prompt)
    except OpenRouterError as exc:
        return {
            "direct_answer": f"OpenRouter is unavailable: {exc}",
            "key_insight": "The model did not run. Evidence below is still the retrieved stored records.",
            "observed_pattern": "—",
            "confidence": "low",
            "caveats": str(exc),
            "evidence": evidence,
            "n_records": len(evidence),
            "sources": sorted({e["source"] for e in evidence if e["source"]}),
            "period": period_label,
            "used_openrouter": False,
        }

    allowed = {item["n"] for item in evidence}
    raw_ids = parsed.get("evidence_numbers") or list(allowed)
    keep = []
    for n in raw_ids:
        try:
            ni = int(n)
        except (TypeError, ValueError):
            continue
        if ni in allowed:
            keep.append(next(e for e in evidence if e["n"] == ni))
    if not keep:
        keep = evidence[:4]

    return {
        "direct_answer": str(parsed.get("direct_answer") or "Insufficient evidence in the retrieved records."),
        "key_insight": str(parsed.get("key_insight") or ""),
        "observed_pattern": str(parsed.get("observed_pattern") or ""),
        "confidence": str(parsed.get("confidence") or "low").lower(),
        "caveats": str(parsed.get("caveats") or "Public conversations are directional, not Myntra conversion rates."),
        "evidence": keep,
        "n_records": len(evidence),
        "sources": sorted({e["source"] for e in evidence if e["source"]}),
        "period": period_label,
        "used_openrouter": True,
    }
