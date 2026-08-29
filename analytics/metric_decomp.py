"""Wishlist → purchase metric decomposition from stored discovery evidence.

Stages are a research framework. Counts are public-conversation evidence, not Myntra funnel analytics.
"""

from __future__ import annotations

import pandas as pd

STAGES = [
    {
        "stage": "Product discovered",
        "behavior": "User finds a product via search, browse, ads, or social.",
        "drop_off": "Never sees a relevant item, or leaves after a poor search experience.",
        "product_metric": "Search/browse sessions that view a PDP",
        "keywords": ("discover", "search", "browse", "app"),
        "fields": (),
    },
    {
        "stage": "Product liked",
        "behavior": "User expresses interest (likes, saves, positive comments).",
        "drop_off": "Interest is aesthetic only; no intent to buy.",
        "product_metric": "PDP engagement / like rate",
        "keywords": ("love this", "liked", "beautiful", "want this"),
        "fields": (),
    },
    {
        "stage": "Product wishlisted",
        "behavior": "User adds to wishlist, saved items, or cart-as-bookmark.",
        "drop_off": "Bookmarking without purchase intent (price watch, later occasion).",
        "product_metric": "Wishlist add rate",
        "keywords": ("wishlist", "wish list", "saved", "bookmark"),
        "fields": ("explicit_wishlist", "save_for_later", "cart_as_bookmark", "price_watch"),
    },
    {
        "stage": "Wishlist revisited",
        "behavior": "User returns to saved items later.",
        "drop_off": "Saved items are forgotten; no reminder or occasion trigger.",
        "product_metric": "Wishlist return visits within 30 days",
        "keywords": ("came back", "later", "waiting", "sale"),
        "fields": ("price_watch", "occasion_planning"),
    },
    {
        "stage": "Purchase consideration",
        "behavior": "User compares, reads reviews, checks size/fit.",
        "drop_off": "Comparison paralysis or missing decision information.",
        "product_metric": "Wishlist → PDP reopen / compare events",
        "keywords": ("compare", "which one", "reviews", "size chart"),
        "fields": ("comparison_shortlist",),
    },
    {
        "stage": "Uncertainty resolved",
        "behavior": "User feels confident enough to buy (fit, size, quality, price).",
        "drop_off": "Unresolved fit/size/price/review/styling uncertainty.",
        "product_metric": "Share of wishlisted SKUs with size/fit tools used",
        "keywords": ("not sure", "uncertain", "fit", "size", "doubt"),
        "fields": (),
    },
    {
        "stage": "Add to cart",
        "behavior": "User moves from wishlist/save into cart.",
        "drop_off": "Stays wishlisted; does not cart.",
        "product_metric": "Wishlist → cart conversion",
        "keywords": ("cart", "checkout later", "added to bag"),
        "fields": ("cart_as_bookmark",),
    },
    {
        "stage": "Checkout",
        "behavior": "User starts payment / address flow.",
        "drop_off": "Delivery, payment, or return-policy friction.",
        "product_metric": "Cart → checkout start",
        "keywords": ("checkout", "payment", "cod", "delivery"),
        "fields": (),
    },
    {
        "stage": "Purchase",
        "behavior": "Order placed.",
        "drop_off": "Order not completed within 30 days of wishlist add.",
        "product_metric": "% of users who purchase ≥1 wishlisted item within 30 days",
        "keywords": ("bought", "ordered", "purchased"),
        "fields": (),
    },
]


def _blob(row: pd.Series) -> str:
    parts = [
        str(row.get("original_text") or ""),
        str(row.get("text") or ""),
        str(row.get("primary_problem") or ""),
        str(row.get("uncertainty_type") or ""),
        str(row.get("purchase_blocker") or ""),
        str(row.get("wishlist_behavior") or ""),
        str(row.get("purchase_status") or ""),
    ]
    return " ".join(parts).lower()


def decompose_metric(records: pd.DataFrame) -> pd.DataFrame:
    """Count stored records whose text/labels mention each funnel stage. Never invents counts."""
    rows = []
    n = 0 if records.empty else int(len(records))
    for spec in STAGES:
        if records.empty:
            count = 0
            sources = "—"
            top_problem = "Insufficient evidence in the collected dataset."
        else:
            mask = pd.Series(False, index=records.index)
            blob = records.apply(_blob, axis=1)
            for kw in spec["keywords"]:
                mask = mask | blob.str.contains(kw, regex=False)
            if spec["fields"] and "wishlist_behavior" in records.columns:
                mask = mask | records["wishlist_behavior"].isin(list(spec["fields"]))
            if spec["stage"] == "Purchase" and "purchase_status" in records.columns:
                mask = mask | records["purchase_status"].fillna("").astype(str).str.lower().eq("purchased")
            if spec["stage"] == "Uncertainty resolved" and "uncertainty_type" in records.columns:
                # Evidence of remaining uncertainty, not resolved certainty.
                mask = mask | records["uncertainty_type"].fillna("").astype(str).str.len().gt(2)
            subset = records[mask]
            count = int(len(subset))
            if count == 0:
                sources = "—"
                top_problem = "Insufficient evidence in the collected dataset."
            else:
                src = subset["source"].value_counts().to_dict() if "source" in subset.columns else {}
                sources = ", ".join(f"{k}:{v}" for k, v in src.items()) or "—"
                if "primary_problem" in subset.columns:
                    series = subset["primary_problem"].dropna().astype(str)
                    series = series[series.str.lower().isin(["", "unknown", "none", "nan"]) == False]  # noqa: E712
                    top_problem = str(series.value_counts().index[0]) if not series.empty else "—"
                else:
                    top_problem = "—"
        share = round(100.0 * count / n, 1) if n else 0.0
        rows.append(
            {
                "Stage": spec["stage"],
                "User behavior": spec["behavior"],
                "Potential drop-off": spec["drop_off"],
                "Measurable product metric": spec["product_metric"],
                "Evidence records": count,
                "% of window records": share,
                "Sources": sources,
                "Strongest related problem in evidence": top_problem,
                "Potential opportunity": (
                    "Investigate this stage with primary research if evidence is non-zero; "
                    "do not treat review frequency as conversion causality."
                    if count
                    else "Insufficient evidence in the collected dataset."
                ),
            }
        )
    return pd.DataFrame(rows)
