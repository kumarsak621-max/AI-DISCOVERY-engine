"""Grounded Ask AI chatbot. Quotes always come from retrieved stored records."""

from __future__ import annotations

from typing import Any

import pandas as pd

from ai.openrouter import OpenRouterError
from ai.provider import AIProviderError, get_llm_client, missing_key_message, provider_display_name
from analytics.quantify import retrieved_quantification
from analytics.retrieval import retrieve_records

CHAT_SYSTEM = """You are a product-discovery analyst for Myntra wishlist conversion.

You may ONLY use the numbered EVIDENCE RECORDS provided.
Do not use general knowledge about fashion or e-commerce.
Do not invent quotes, URLs, dates, or statistics.
If the records are insufficient, say so and set confidence to low.
Distinguish OBSERVED EVIDENCE (stored user text) from AI INTERPRETATION (hypothesis only).
Do not claim causality. Use wording such as "observed evidence", "potential barrier", or "evidence suggests".
Percentages, if any, are of these retrieved records — never of all Myntra users.

Return JSON:
{
  "direct_answer": "string",
  "key_finding": "string",
  "observed_pattern": "string",
  "business_implication": "string — labeled as hypothesis, not causality",
  "confidence": "high|medium|low",
  "caveats": "string",
  "evidence_numbers": [1, 2]
}

evidence_numbers must be ids from the provided list. Do not quote text that is not in those records.
Do not invent record counts or percentages. Quantification is computed separately from the retrieved rows.
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
                "subreddit": str(row.get("subreddit") or ""),
                "url": str(row.get("source_url") or ""),
                "date": str(row.get("published_at") or ""),
                "platform": str(row.get("source") or ""),
                "intent": str(row.get("purchase_intent") or ""),
                "wishlist_intent": str(row.get("wishlist_intent") or ""),
                "problem": str(row.get("theme") or row.get("primary_problem") or ""),
                "pain_point": str(row.get("pain_point") or ""),
                "text": original,
                "video": str(row.get("video_title") or ""),
                "rating": row.get("rating"),
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
    provider: str = "openrouter",
    gemini_key: str = "",
) -> dict[str, Any]:
    retrieved = retrieve_records(records, question, limit=8)
    evidence = records_to_evidence(retrieved)
    quant = retrieved_quantification(retrieved)
    used_name = provider_display_name(provider)
    if records.empty:
        return {
            "direct_answer": "No real reviews were collected for this period.",
            "key_insight": "The chatbot has no stored public conversations to retrieve.",
            "key_finding": "The chatbot has no stored public conversations to retrieve.",
            "quantification": {"n": 0, "sources": {}, "themes": {}, "intents": {}},
            "source_breakdown": {},
            "observed_pattern": "—",
            "business_implication": "—",
            "confidence": "low",
            "caveats": "Collect public conversations first. This answer is not based on Myntra user analytics.",
            "evidence": [],
            "n_records": 0,
            "sources": [],
            "period": period_label,
            "used_openrouter": False,
            "ai_provider": used_name,
        }
    if retrieved.empty:
        return {
            "direct_answer": "Insufficient evidence in the collected dataset.",
            "key_insight": "No stored records matched this question closely enough to quote.",
            "key_finding": "Insufficient evidence in the collected dataset.",
            "quantification": {"n": 0, "sources": {}, "themes": {}, "intents": {}},
            "source_breakdown": {},
            "observed_pattern": "—",
            "business_implication": "—",
            "confidence": "low",
            "caveats": "The dataset may not contain reviews about this topic in the selected period.",
            "evidence": [],
            "n_records": 0,
            "sources": [],
            "period": period_label,
            "used_openrouter": False,
            "ai_provider": used_name,
        }

    numbered = []
    for item in evidence:
        numbered.append(
            f"RECORD {item['n']}\n"
            f"source={item['source']} subreddit={item.get('subreddit') or '—'} date={item['date']} url={item['url']}\n"
            f"intent={item['intent']} wishlist_intent={item.get('wishlist_intent') or 'Unknown'} "
            f"problem={item['problem']} pain_point={item.get('pain_point') or ''}\n"
            f"text={_clip(item['text'])}\n"
        )
    user_prompt = (
        f"QUESTION: {question}\n"
        f"{period_label}\n"
        f"Retrieved real records: {len(evidence)}\n\n"
        + "\n".join(numbered)
        + "\nAnswer using only these records."
    )

    client = get_llm_client(
        provider,
        openrouter_key=api_key,
        gemini_key=gemini_key,
        model=model,
        temperature=0.1,
    )
    used_name = provider_display_name(provider)
    if not client.is_configured:
        return {
            "direct_answer": missing_key_message(provider),
            "key_insight": "The selected AI provider is not configured. Evidence below is still retrieved stored records.",
            "key_finding": "The selected AI provider is not configured. Evidence below is still retrieved stored records.",
            "quantification": quant,
            "source_breakdown": quant.get("sources") or {},
            "observed_pattern": "—",
            "business_implication": "—",
            "confidence": "low",
            "caveats": missing_key_message(provider),
            "evidence": evidence,
            "n_records": len(evidence),
            "sources": sorted({e["source"] for e in evidence if e["source"]}),
            "period": period_label,
            "used_openrouter": False,
            "ai_provider": used_name,
        }
    try:
        parsed = client.complete_json(CHAT_SYSTEM, user_prompt)
    except (OpenRouterError, AIProviderError) as exc:
        return {
            "direct_answer": f"{used_name} is unavailable: {exc}",
            "key_insight": "The model did not run. Evidence below is still the retrieved stored records.",
            "key_finding": "The model did not run. Evidence below is still the retrieved stored records.",
            "quantification": quant,
            "source_breakdown": quant.get("sources") or {},
            "observed_pattern": "—",
            "business_implication": "—",
            "confidence": "low",
            "caveats": str(exc),
            "evidence": evidence,
            "n_records": len(evidence),
            "sources": sorted({e["source"] for e in evidence if e["source"]}),
            "period": period_label,
            "used_openrouter": False,
            "ai_provider": used_name,
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

    finding = str(parsed.get("key_finding") or parsed.get("key_insight") or "")
    return {
        "direct_answer": str(parsed.get("direct_answer") or "Insufficient evidence in the collected dataset."),
        "key_insight": finding,
        "key_finding": finding,
        "quantification": quant,
        "source_breakdown": quant.get("sources") or {},
        "observed_pattern": str(parsed.get("observed_pattern") or ""),
        "business_implication": str(
            parsed.get("business_implication")
            or "This may indicate a hypothesis to validate — not a proven cause of non-purchase."
        ),
        "confidence": str(parsed.get("confidence") or "low").lower(),
        "caveats": str(parsed.get("caveats") or "Public conversations are directional, not Myntra conversion rates."),
        "evidence": keep,
        "n_records": int(quant.get("n") or len(evidence)),
        "sources": sorted({e["source"] for e in evidence if e["source"]}),
        "period": period_label,
        "used_openrouter": used_name == "OpenRouter",
        "ai_provider": used_name,
        "ai_model": getattr(client, "model", model),
    }
