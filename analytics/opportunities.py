"""Opportunity scoring: research-based prioritization, not causal claims."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from ai.clustering import problem_key, theme_for_key
from config import HIGH_INTENT_STATUSES, OPPORTUNITY_WEIGHTS
from database.models import Analysis, Opportunity, Theme

logger = logging.getLogger(__name__)

SEVERE_STATUSES = {
    "postponed",
    "abandoned",
    "waiting",
    "rejected",
    "alternative_purchased",
}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def frequency_score(count: int, n_relevant: int) -> float:
    if n_relevant <= 0:
        return 0.0
    share = count / n_relevant
    return clamp(share / 0.35 * 100.0)


def severity_score(items: list[Analysis]) -> float:
    if not items:
        return 0.0
    severe = sum(1 for a in items if a.purchase_status in SEVERE_STATUSES)
    return clamp(severe / len(items) * 100.0)


def conversion_relevance_score(items: list[Analysis]) -> float:
    if not items:
        return 0.0
    high = sum(
        1
        for a in items
        if a.purchase_intent == "high" and a.purchase_status in HIGH_INTENT_STATUSES
    )
    return clamp(high / len(items) * 100.0)


def workaround_score(items: list[Analysis]) -> float:
    if not items:
        return 0.0
    with_work = 0
    for analysis in items:
        text = (analysis.workaround or "").strip().lower()
        if text and text not in {"none", "unknown", "n/a", "no workaround"}:
            with_work += 1
        elif analysis.leaves_myntra:
            with_work += 1
    return clamp(with_work / len(items) * 100.0)


def segment_score(items: list[Analysis]) -> float:
    if not items:
        return 0.0
    counts = Counter((a.user_segment or "unknown") for a in items)
    top = counts.most_common(1)[0][1]
    return clamp(top / len(items) * 100.0)


def confidence_score(items: list[Analysis]) -> float:
    if not items:
        return 0.0
    return clamp(sum(a.confidence or 0.0 for a in items) / len(items) * 100.0)


def multiplicative_framework_score(
    frequency_count: int,
    n_relevant: int,
    conversion_relevance: float,
    user_impact: float,
    evidence_count: int,
    evidence_cap: int = 20,
) -> float:
    """Frequency × purchase relevance × user impact × evidence strength, scaled 0–100.

    This is an evidence-based ranking aid, not proof of causality.
    """
    freq = (frequency_count / n_relevant) if n_relevant else 0.0
    purchase = max(0.0, min(float(conversion_relevance) / 100.0, 1.0))
    impact = max(0.0, min(float(user_impact) / 100.0, 1.0))
    strength = min(max(int(evidence_count), 0) / float(evidence_cap), 1.0)
    return round(freq * purchase * impact * strength * 100.0, 2)


def compute_opportunity_score(
    frequency: float,
    severity: float,
    conversion_relevance: float,
    workaround: float,
    segment: float,
    confidence: float,
) -> float:
    weights = OPPORTUNITY_WEIGHTS
    score = (
        weights["frequency"] * frequency
        + weights["severity"] * severity
        + weights["conversion_relevance"] * conversion_relevance
        + weights["workaround"] * workaround
        + weights["segment"] * segment
        + weights["confidence"] * confidence
    )
    return round(clamp(score), 2)


def build_opportunities(session: Session, analyses: list[Analysis]) -> list[Opportunity]:
    session.query(Opportunity).delete()
    relevant = [a for a in analyses if a.relevant_to_wishlist]
    n_relevant = len(relevant)
    groups: dict[str, list[Analysis]] = defaultdict(list)
    for analysis in relevant:
        name = theme_for_key(problem_key(analysis))[0]
        groups[name].append(analysis)

    stored: list[Opportunity] = []
    for name, items in groups.items():
        freq = frequency_score(len(items), n_relevant)
        sev = severity_score(items)
        conv = conversion_relevance_score(items)
        work = workaround_score(items)
        seg = segment_score(items)
        conf = confidence_score(items)
        score = compute_opportunity_score(freq, sev, conv, work, seg, conf)
        segments = Counter((a.user_segment or "unknown") for a in items)
        top_segment = segments.most_common(1)[0][0] if segments else "unknown"
        evidence = []
        for analysis in items:
            conv_row = analysis.conversation
            if analysis.evidence_quote and analysis.evidence_quote != "no direct evidence":
                evidence.append(
                    {
                        "quote": analysis.evidence_quote,
                        "source": conv_row.source if conv_row else "",
                        "url": conv_row.source_url if conv_row else "",
                        "intent": analysis.purchase_intent,
                        "status": analysis.purchase_status,
                        "segment": analysis.user_segment,
                        "confidence": analysis.confidence,
                    }
                )
            if len(evidence) >= 8:
                break
        _, description = theme_for_key(problem_key(items[0]))
        opportunity = Opportunity(
            opportunity_name=name,
            user_segment=top_segment,
            problem_statement=description,
            evidence_count=len(items),
            frequency_score=round(freq, 2),
            severity_score=round(sev, 2),
            conversion_relevance_score=round(conv, 2),
            workaround_score=round(work, 2),
            segment_score=round(seg, 2),
            confidence_score=round(conf, 2),
            opportunity_score=score,
            supporting_evidence=json.dumps(evidence),
            contradictory_evidence="[]",
            evidence_gaps="[]",
        )
        session.add(opportunity)
        stored.append(opportunity)

        theme_row = session.query(Theme).filter(Theme.theme_name == name).one_or_none()
        if theme_row:
            theme_row.opportunity_score = score

    session.commit()
    stored.sort(key=lambda row: row.opportunity_score, reverse=True)
    return stored
