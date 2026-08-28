"""Per-conversation LLM analysis with quote grounding and failure isolation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ai.openrouter import OpenRouterClient, OpenRouterError
from ai.prompts import SYSTEM_PROMPT, build_user_prompt
from ai.schemas import ConversationAnalysis
from config import HIGH_INTENT_STATUSES, HUMAN_VALIDATION_CONFIDENCE_THRESHOLD
from database.models import Analysis, Conversation, FailedAnalysis

logger = logging.getLogger(__name__)


def quote_is_grounded(quote: str, original_text: str) -> bool:
    if not quote or quote.strip().lower() == "no direct evidence":
        return True
    haystack = original_text.lower()
    needle = quote.strip().lower()
    if needle in haystack:
        return True
    # Allow minor whitespace differences
    compact_h = " ".join(haystack.split())
    compact_n = " ".join(needle.split())
    return compact_n in compact_h


def apply_quality_gates(analysis: ConversationAnalysis, original_text: str) -> ConversationAnalysis:
    if not quote_is_grounded(analysis.evidence_quote, original_text):
        analysis.evidence_quote = "no direct evidence"
        analysis.confidence = min(analysis.confidence, 0.4)
        analysis.needs_human_validation = True
    if analysis.confidence < HUMAN_VALIDATION_CONFIDENCE_THRESHOLD:
        analysis.needs_human_validation = True
    if analysis.evidence_quote.strip().lower() == "no direct evidence":
        analysis.needs_human_validation = True
    if (
        analysis.purchase_intent == "high"
        and analysis.purchase_status in HIGH_INTENT_STATUSES
        and analysis.confidence < 0.8
    ):
        analysis.needs_human_validation = True
    return analysis


def analysis_from_dict(payload: dict) -> ConversationAnalysis:
    return ConversationAnalysis.model_validate(payload)


def persist_analysis(session: Session, conversation: Conversation, parsed: ConversationAnalysis) -> Analysis:
    blockers = list(parsed.blockers) if parsed.blockers else ["unknown"]
    primary_blocker = blockers[0] if blockers else "unknown"
    row = conversation.analysis
    if row is None:
        row = Analysis(conversation_id=conversation.id)
        session.add(row)
    row.relevant_to_wishlist = parsed.relevant
    row.relevance_reason = parsed.relevance_reason
    row.wishlist_behavior = parsed.wishlist_behavior
    row.purchase_intent = parsed.purchase_intent
    row.purchase_status = parsed.purchase_status
    row.primary_problem = parsed.primary_problem
    row.secondary_problems = json.dumps(parsed.secondary_problems)
    row.uncertainty = parsed.uncertainty_text
    row.uncertainty_type = parsed.uncertainty_type
    row.uncertainty_text = parsed.uncertainty_text
    row.purchase_blocker = primary_blocker
    row.purchase_blockers = json.dumps(blockers)
    row.motivation = parsed.motivation
    row.workaround = parsed.workaround
    row.information_sought = json.dumps(parsed.information_sought)
    row.leaves_myntra = parsed.leaves_myntra
    row.external_information_source = parsed.external_information_source
    row.alternative_considered = parsed.alternative_considered
    row.user_segment = parsed.user_segment
    row.segment_evidence = parsed.segment_evidence
    row.fashion_category = parsed.fashion_category
    row.occasion = parsed.occasion
    row.sentiment = parsed.sentiment
    row.evidence_quote = parsed.evidence_quote
    row.evidence_type = "verbatim" if parsed.evidence_quote != "no direct evidence" else "none"
    row.confidence = parsed.confidence
    row.needs_human_validation = parsed.needs_human_validation
    row.funnel_stage = parsed.funnel_stage
    row.analyzed_at = datetime.now(timezone.utc)
    conversation.analysis_status = "complete"
    conversation.analysis_error = ""
    return row


class ConversationAnalyzer:
    def __init__(self, client: OpenRouterClient) -> None:
        self.client = client

    def analyze_one(self, conversation: Conversation) -> ConversationAnalysis:
        user_prompt = build_user_prompt(
            source=conversation.source,
            source_url=conversation.source_url,
            title=conversation.title,
            text=conversation.original_text or conversation.text,
            language=conversation.language,
            query_used=conversation.query_used,
        )
        payload = self.client.complete_json(SYSTEM_PROMPT, user_prompt)
        parsed = analysis_from_dict(payload)
        return apply_quality_gates(parsed, conversation.original_text or conversation.text)

    def analyze_batch(
        self,
        session: Session,
        conversations: list[Conversation],
        progress_callback=None,
    ) -> tuple[int, int]:
        ok = 0
        failed = 0
        total = len(conversations)
        for index, conversation in enumerate(conversations, start=1):
            try:
                parsed = self.analyze_one(conversation)
                persist_analysis(session, conversation, parsed)
                session.commit()
                ok += 1
            except OpenRouterError as exc:
                failed += 1
                conversation.analysis_status = "failed"
                conversation.analysis_error = str(exc)[:500]
                session.add(
                    FailedAnalysis(
                        conversation_id=conversation.id,
                        error=str(exc)[:1000],
                        retry_count=1,
                    )
                )
                session.commit()
                logger.warning("Analysis failed for conversation %s: %s", conversation.id, exc)
                if exc.status_code == 401:
                    logger.error("Stopping batch: invalid API key")
                    break
            except Exception as exc:  # noqa: BLE001 - isolate per-record failures
                failed += 1
                conversation.analysis_status = "failed"
                conversation.analysis_error = str(exc)[:500]
                session.add(
                    FailedAnalysis(
                        conversation_id=conversation.id,
                        error=str(exc)[:1000],
                        retry_count=1,
                    )
                )
                session.commit()
                logger.warning("Unexpected analysis failure for %s: %s", conversation.id, exc)
            if progress_callback:
                progress_callback(index, total, ok, failed)
        return ok, failed
