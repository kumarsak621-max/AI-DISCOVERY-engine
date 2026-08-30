"""Keyword retrieval over collected records. No embeddings, no extra infrastructure."""

from __future__ import annotations

import re

import pandas as pd

STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "is",
    "are",
    "was",
    "were",
    "what",
    "why",
    "how",
    "do",
    "does",
    "users",
    "user",
    "they",
    "their",
    "this",
    "that",
    "with",
    "from",
    "about",
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if t not in STOP}


def retrieve_records(records: pd.DataFrame, question: str, limit: int = 8) -> pd.DataFrame:
    """Return the most relevant real rows for a question. Never invents rows."""
    if records.empty:
        return records
    qtok = _tokens(question)
    if not qtok:
        dated = records.copy()
        dated["_pub"] = pd.to_datetime(dated.get("published_at"), utc=True, errors="coerce")
        return dated.sort_values("_pub", ascending=False, na_position="last").head(limit).drop(columns=["_pub"], errors="ignore")

    scores: list[float] = []
    for _, row in records.iterrows():
        blob = " ".join(
            str(row.get(c) or "")
            for c in (
                "title",
                "text",
                "original_text",
                "primary_problem",
                "theme",
                "pain_point",
                "uncertainty_type",
                "uncertainty_text",
                "uncertainty_level",
                "purchase_blocker",
                "motivation",
                "workaround",
                "evidence_quote",
                "user_segment",
                "fashion_category",
                "wishlist_intent",
            )
        )
        rtok = _tokens(blob)
        overlap = len(qtok & rtok)
        boost = 0
        problem = str(row.get("primary_problem") or "").lower()
        if any(t in problem for t in qtok):
            boost += 2
        qlow = question.lower()
        if "fit" in qlow or "size" in qlow:
            if any(w in blob.lower() for w in ("fit", "size", "sizing", "size chart")):
                boost += 3
        if "wishlist" in qlow or "save" in qlow:
            if any(w in blob.lower() for w in ("wishlist", "saved", "bookmark")):
                boost += 2
        if "postpone" in qlow or "wait" in qlow or "sale" in qlow:
            if any(w in blob.lower() for w in ("wait", "sale", "later", "postpone", "price")):
                boost += 2
        scores.append(float(overlap + boost))
    ranked = records.copy()
    ranked["_score"] = scores
    hit = ranked[ranked["_score"] > 0].sort_values("_score", ascending=False)
    if hit.empty:
        ranked["_pub"] = pd.to_datetime(ranked.get("published_at"), utc=True, errors="coerce")
        return ranked.sort_values("_pub", ascending=False, na_position="last").head(limit).drop(
            columns=["_score", "_pub"], errors="ignore"
        )
    return hit.head(limit).drop(columns=["_score"], errors="ignore")
