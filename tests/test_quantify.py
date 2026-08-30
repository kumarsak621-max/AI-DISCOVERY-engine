"""Theme quantification from real records only — no invented percentages."""

from datetime import datetime, timezone

import pandas as pd

from analytics.quantify import retrieved_quantification, source_comparison, source_counts, theme_quantification


def _frame() -> pd.DataFrame:
    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    return pd.DataFrame(
        [
            {
                "source": "google_play",
                "primary_problem": "fit uncertainty",
                "relevant_to_wishlist": True,
                "sentiment": "negative",
                "purchase_intent": "high",
                "user_segment": "size-anxious",
                "uncertainty_type": "fit",
                "wishlist_behavior": "explicit_wishlist",
                "rating": 2,
                "published_at": now,
            },
            {
                "source": "google_play",
                "primary_problem": "fit uncertainty",
                "relevant_to_wishlist": True,
                "sentiment": "negative",
                "purchase_intent": "medium",
                "user_segment": "size-anxious",
                "uncertainty_type": "fit",
                "wishlist_behavior": "save_for_later",
                "rating": 3,
                "published_at": now,
            },
            {
                "source": "youtube",
                "primary_problem": "price timing",
                "relevant_to_wishlist": True,
                "sentiment": "mixed",
                "purchase_intent": "high",
                "user_segment": "deal-seeker",
                "uncertainty_type": "price",
                "wishlist_behavior": "price_watch",
                "rating": None,
                "published_at": now,
            },
        ]
    )


def test_source_counts_from_rows() -> None:
    counts = source_counts(_frame())
    assert counts["Total"] == 3
    assert counts["Google Play Store"] == 2
    assert counts["YouTube"] == 1
    assert counts["Manual Upload"] == 0


def test_theme_share_is_of_relevant_records() -> None:
    table = theme_quantification(_frame())
    fit = table[table["Theme"] == "fit uncertainty"].iloc[0]
    assert int(fit["Records"]) == 2
    assert float(fit["Share of relevant records %"]) == 66.7
    assert int(fit["Google Play Store"]) == 2
    assert int(fit["YouTube"]) == 0


def test_empty_quantification_is_empty_not_fake() -> None:
    assert theme_quantification(pd.DataFrame()).empty
    counts = source_counts(pd.DataFrame())
    assert counts["Total"] == 0
    assert counts["Google Play Store"] == 0


def test_source_comparison_keeps_zero_sources() -> None:
    table = source_comparison(_frame())
    play = table[table["Source"] == "Google Play Store"].iloc[0]
    assert int(play["Records"]) == 2
    assert play["Top theme"] == "fit uncertainty"
    manual = table[table["Source"] == "Manual Upload"].iloc[0]
    assert int(manual["Records"]) == 0


def test_retrieved_quantification_matches_rows() -> None:
    quant = retrieved_quantification(_frame())
    assert quant["n"] == 3
    assert quant["sources"]["google_play"] == 2
    assert quant["themes"]["fit uncertainty"] == 2
