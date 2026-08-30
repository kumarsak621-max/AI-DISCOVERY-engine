"""Pydantic schemas for structured LLM analysis output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

WishlistBehavior = Literal[
    "explicit_wishlist",
    "save_for_later",
    "cart_as_bookmark",
    "browsing_only",
    "comparison_shortlist",
    "price_watch",
    "occasion_planning",
    "unclear",
]

PurchaseIntent = Literal["high", "medium", "low", "unknown"]

PurchaseStatus = Literal[
    "purchased",
    "considering",
    "postponed",
    "abandoned",
    "rejected",
    "waiting",
    "alternative_purchased",
    "unknown",
]

Blocker = Literal[
    "price_uncertainty",
    "waiting_for_price_drop",
    "size_uncertainty",
    "fit_uncertainty",
    "quality_uncertainty",
    "fabric_uncertainty",
    "appearance_uncertainty",
    "review_uncertainty",
    "trust_uncertainty",
    "return_uncertainty",
    "delivery_uncertainty",
    "occasion_uncertainty",
    "styling_uncertainty",
    "comparison_uncertainty",
    "availability_uncertainty",
    "social_validation",
    "indecision",
    "low_urgency",
    "budget_constraint",
    "discovered_better_alternative",
    "no_blocker",
    "unknown",
]

ExternalSource = Literal[
    "Reddit",
    "Instagram",
    "YouTube",
    "Google",
    "friends",
    "influencers",
    "other shopping apps",
    "brand website",
    "physical store",
    "none",
    "unknown",
]


ALLOWED_THEMES = (
    "Product Quality",
    "Size / Fit",
    "Pricing",
    "Delivery",
    "Returns / Refund",
    "Customer Support",
    "Product Discovery",
    "Fashion / Styling",
    "Wishlist",
    "Purchase Decision",
    "App Experience",
    "Payment",
    "Availability",
    "Trust",
    "Reviews",
    "Comparison",
    "Other",
    "Unclear",
)

_THEME_ALIASES = {
    "product quality": "Product Quality",
    "quality": "Product Quality",
    "size / fit": "Size / Fit",
    "size/fit": "Size / Fit",
    "size": "Size / Fit",
    "fit": "Size / Fit",
    "fit uncertainty": "Size / Fit",
    "size uncertainty": "Size / Fit",
    "pricing": "Pricing",
    "price": "Pricing",
    "delivery": "Delivery",
    "returns / refund": "Returns / Refund",
    "returns": "Returns / Refund",
    "refund": "Returns / Refund",
    "customer support": "Customer Support",
    "support": "Customer Support",
    "product discovery": "Product Discovery",
    "discovery": "Product Discovery",
    "fashion / styling": "Fashion / Styling",
    "fashion": "Fashion / Styling",
    "styling": "Fashion / Styling",
    "wishlist": "Wishlist",
    "purchase decision": "Purchase Decision",
    "app experience": "App Experience",
    "app": "App Experience",
    "payment": "Payment",
    "availability": "Availability",
    "trust": "Trust",
    "reviews": "Reviews",
    "comparison": "Comparison",
    "other": "Other",
    "unclear": "Unclear",
    "unknown": "Unclear",
}

LEVEL_VALUES = ("High", "Medium", "Low", "Unknown")
SENTIMENT_VALUES = ("Positive", "Negative", "Neutral", "Mixed")


def normalize_theme(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unclear"
    if text in ALLOWED_THEMES:
        return text
    return _THEME_ALIASES.get(text.lower(), text)


def normalize_level(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"
    titled = text[:1].upper() + text[1:].lower() if text else "Unknown"
    if titled in LEVEL_VALUES:
        return titled
    lowered = text.lower()
    mapping = {"high": "High", "medium": "Medium", "low": "Low", "unknown": "Unknown", "unclear": "Unknown"}
    return mapping.get(lowered, "Unknown")


def normalize_sentiment(value: object) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "positive": "positive",
        "negative": "negative",
        "neutral": "neutral",
        "mixed": "mixed",
    }
    return mapping.get(text, "neutral")


class ConversationAnalysis(BaseModel):
    relevant: bool
    relevance_reason: str = ""
    wishlist_behavior: WishlistBehavior = "unclear"
    purchase_intent: PurchaseIntent = "unknown"
    purchase_status: PurchaseStatus = "unknown"
    blockers: list[str] = Field(default_factory=list)
    primary_problem: str = ""
    theme: str = "Unclear"
    secondary_problems: list[str] = Field(default_factory=list)
    uncertainty_type: str = ""
    uncertainty_text: str = ""
    uncertainty: str = "Unknown"
    wishlist_intent: str = "Unknown"
    pain_point: str = ""
    pain_point_evidence: str = ""
    information_sought: list[str] = Field(default_factory=list)
    leaves_myntra: bool = False
    external_information_source: str = "unknown"
    workaround: str = ""
    motivation: str = ""
    alternative_considered: str = ""
    user_segment: str = "unknown"
    segment_evidence: str = "no direct evidence"
    fashion_category: str = "unknown"
    occasion: str = "unknown"
    sentiment: str = "neutral"
    evidence_quote: str = "no direct evidence"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    funnel_stage: str = "unknown"
    needs_human_validation: bool = True

    @field_validator("theme", mode="before")
    @classmethod
    def _theme(cls, value: object) -> str:
        return normalize_theme(value)

    @field_validator("uncertainty", "wishlist_intent", mode="before")
    @classmethod
    def _level(cls, value: object) -> str:
        return normalize_level(value)

    @field_validator("sentiment", mode="before")
    @classmethod
    def _sentiment(cls, value: object) -> str:
        return normalize_sentiment(value)

    @field_validator("user_segment", mode="before")
    @classmethod
    def _segment(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text or text.lower() in {"unknown", "unclear", "none", "n/a"}:
            return "unknown"
        return text

    @field_validator("blockers", "secondary_problems", "information_sought", mode="before")
    @classmethod
    def _coerce_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            if not value.strip() or value.strip().lower() in {"none", "n/a", "unknown"}:
                return []
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("evidence_quote", "segment_evidence", mode="before")
    @classmethod
    def _empty_quote(cls, value: object) -> str:
        if value is None or str(value).strip() == "":
            return "no direct evidence"
        return str(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, value: object) -> float:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        if number > 1.0 and number <= 100.0:
            number = number / 100.0
        return max(0.0, min(1.0, number))


class ThemeClusterDraft(BaseModel):
    theme_name: str
    description: str
    member_problem_keys: list[str] = Field(default_factory=list)
