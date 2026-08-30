"""SQLAlchemy models — SQLite now, PostgreSQL-compatible types."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_conversations_content_hash"),
        Index("ix_conversations_source_item", "source", "source_item_id"),
        Index("ix_conversations_published_at", "published_at"),
        Index("ix_conversations_source_url", "source_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_item_id: Mapped[str] = mapped_column(String(256), default="", index=True)
    source_url: Mapped[str] = mapped_column(String(1024), default="")
    author_id_hash: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(32), default="unknown")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    query_used: Mapped[str] = mapped_column(String(256), default="")
    engagement_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    is_syndicated: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    analysis_status: Mapped[str] = mapped_column(String(32), default="pending")
    analysis_error: Mapped[str] = mapped_column(Text, default="")

    analysis: Mapped["Analysis | None"] = relationship(
        back_populates="conversation", uselist=False, cascade="all, delete-orphan"
    )


class Analysis(Base):
    __tablename__ = "analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, index=True
    )
    relevant_to_wishlist: Mapped[bool] = mapped_column(Boolean, default=False)
    relevance_reason: Mapped[str] = mapped_column(Text, default="")
    wishlist_behavior: Mapped[str] = mapped_column(String(64), default="unclear")
    purchase_intent: Mapped[str] = mapped_column(String(32), default="unknown")
    purchase_status: Mapped[str] = mapped_column(String(64), default="unknown")
    primary_problem: Mapped[str] = mapped_column(String(256), default="")
    secondary_problems: Mapped[str] = mapped_column(Text, default="[]")
    uncertainty_type: Mapped[str] = mapped_column(String(64), default="")
    uncertainty_text: Mapped[str] = mapped_column(Text, default="")
    purchase_blockers: Mapped[str] = mapped_column(Text, default="[]")
    purchase_blocker: Mapped[str] = mapped_column(String(64), default="unknown")
    motivation: Mapped[str] = mapped_column(Text, default="")
    workaround: Mapped[str] = mapped_column(Text, default="")
    information_sought: Mapped[str] = mapped_column(Text, default="[]")
    external_information_source: Mapped[str] = mapped_column(String(64), default="unknown")
    leaves_myntra: Mapped[bool] = mapped_column(Boolean, default=False)
    alternative_considered: Mapped[str] = mapped_column(Text, default="")
    user_segment: Mapped[str] = mapped_column(String(128), default="unknown")
    segment_evidence: Mapped[str] = mapped_column(Text, default="")
    fashion_category: Mapped[str] = mapped_column(String(64), default="unknown")
    occasion: Mapped[str] = mapped_column(String(64), default="unknown")
    sentiment: Mapped[str] = mapped_column(String(32), default="neutral")
    theme: Mapped[str] = mapped_column(String(128), default="")
    wishlist_intent: Mapped[str] = mapped_column(String(32), default="unknown")
    uncertainty_level: Mapped[str] = mapped_column(String(32), default="unknown")
    pain_point: Mapped[str] = mapped_column(Text, default="")
    pain_point_evidence: Mapped[str] = mapped_column(Text, default="")
    analysis_provider: Mapped[str] = mapped_column(String(64), default="")
    analysis_model: Mapped[str] = mapped_column(String(128), default="")
    evidence_quote: Mapped[str] = mapped_column(Text, default="no direct evidence")
    evidence_type: Mapped[str] = mapped_column(String(64), default="verbatim")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_human_validation: Mapped[bool] = mapped_column(Boolean, default=True)
    funnel_stage: Mapped[str] = mapped_column(String(64), default="unknown")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="analysis")


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theme_name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[int] = mapped_column(Integer, default=0)
    percentage_of_relevant_conversations: Mapped[float] = mapped_column(Float, default=0.0)
    unique_users: Mapped[int] = mapped_column(Integer, default=0)
    high_intent_mentions: Mapped[int] = mapped_column(Integer, default=0)
    blocker_mentions: Mapped[int] = mapped_column(Integer, default=0)
    purchase_mentions: Mapped[int] = mapped_column(Integer, default=0)
    average_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    representative_evidence: Mapped[str] = mapped_column(Text, default="[]")
    segment_distribution: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_name: Mapped[str] = mapped_column(String(256), index=True)
    user_segment: Mapped[str] = mapped_column(String(128), default="")
    problem_statement: Mapped[str] = mapped_column(Text, default="")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    frequency_score: Mapped[float] = mapped_column(Float, default=0.0)
    severity_score: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    workaround_score: Mapped[float] = mapped_column(Float, default=0.0)
    segment_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_evidence: Mapped[str] = mapped_column(Text, default="[]")
    contradictory_evidence: Mapped[str] = mapped_column(Text, default="[]")
    evidence_gaps: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_new: Mapped[int] = mapped_column(Integer, default=0)
    records_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    requested_records: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="running")
    error_message: Mapped[str] = mapped_column(Text, default="")


class SourceState(Base):
    """Per-source health and incremental collection cursor (spec: source_health)."""

    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_successful_collection_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_records_found: Mapped[int] = mapped_column(Integer, default=0)
    last_records_new: Mapped[int] = mapped_column(Integer, default=0)
    last_records_failed: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FailedAnalysis(Base):
    __tablename__ = "failed_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_days: Mapped[int] = mapped_column(Integer, default=30)
    conversations_collected: Mapped[int] = mapped_column(Integer, default=0)
    conversations_new: Mapped[int] = mapped_column(Integer, default=0)
    conversations_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    conversations_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    source_results_json: Mapped[str] = mapped_column(Text, default="[]")
    relevant_count: Mapped[int] = mapped_column(Integer, default=0)
    full_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    brief_markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="running")
    error: Mapped[str] = mapped_column(Text, default="")
    last_ai_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_provider: Mapped[str] = mapped_column(String(64), default="")
    ai_model: Mapped[str] = mapped_column(String(128), default="")

    @property
    def source_results(self) -> list:
        try:
            parsed = json.loads(self.source_results_json or "[]")
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @source_results.setter
    def source_results(self, value: list | None) -> None:
        self.source_results_json = json.dumps(value or [])


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
