"""Part 1 research-question answer engine."""

from __future__ import annotations

import pandas as pd

from analytics.part1_answers import (
    PCT_LABEL,
    alternative_count_stated,
    build_part1_answers,
    classify_motivation,
    part1_markdown,
)


def _row(**kwargs) -> dict:
    base = {
        "relevant_to_wishlist": True,
        "wishlist_behavior": "explicit_wishlist",
        "purchase_intent": "high",
        "purchase_status": "postponed",
        "high_intent_friction": True,
        "blockers": ["fit_uncertainty"],
        "purchase_blocker": "fit_uncertainty",
        "uncertainty_type": "fit",
        "uncertainty_text": "not sure if it will fit",
        "motivation": "want to buy",
        "workaround": "search youtube",
        "information_sought": ["size/fit information"],
        "leaves_myntra": True,
        "external_information_source": "YouTube",
        "alternative_considered": "",
        "user_segment": "fit-sensitive shopper",
        "evidence_quote": "not sure if it will fit",
        "confidence": 0.8,
        "published_at": "2026-08-10T00:00:00+00:00",
        "source": "reddit",
        "source_url": "https://reddit.com/r/test/abc",
        "original_text": "I wishlisted this dress but not sure if it will fit",
        "text": "I wishlisted this dress but not sure if it will fit",
        "primary_problem": "fit uncertainty",
        "occasion": "",
    }
    base.update(kwargs)
    return base


def test_empty_corpus_answers_every_question() -> None:
    payload = build_part1_answers(pd.DataFrame(), pd.DataFrame())
    assert payload["n_relevant"] == 0
    assert payload["n_analyzed"] == 0
    for i in range(1, 11):
        q = payload["questions"][f"q{i}"]
        assert q["evidence_count"] == 0
        assert q["pct_of_relevant"] == 0.0
        assert q["pct_label"] == PCT_LABEL
        assert "not percentages of Myntra users" in payload["disclaimer"].lower() or "not percentages of Myntra" in payload["disclaimer"]
    md = part1_markdown(payload)
    assert "Q1 — Wishlist motivations" in md
    assert "Q10 — Unmet needs" in md
    assert "Questions public data cannot answer" in md
    assert "DISCOVERY → OPPORTUNITY HYPOTHESIS" in md


def test_percentages_use_relevant_denominator_not_all_rows() -> None:
    rows = [
        _row(),
        _row(
            relevant_to_wishlist=False,
            wishlist_behavior="browsing_only",
            purchase_intent="low",
            high_intent_friction=False,
            evidence_quote="no direct evidence",
            original_text="unrelated complaint",
            text="unrelated complaint",
        ),
    ]
    payload = build_part1_answers(pd.DataFrame(rows), pd.DataFrame())
    assert payload["n_analyzed"] == 2
    assert payload["n_relevant"] == 1
    q1 = payload["questions"]["q1"]
    assert q1["pct_of_relevant"] == 100.0
    assert q1["pct_label"] == "Percentage of analyzed public conversations"
    assert "Myntra users" in q1["direct_answer"]
    motivations = q1["tables"]["motivations"]
    genuine = next(r for r in motivations if r["motivation"] == "genuine purchase intent")
    assert genuine["frequency"] == 1
    assert genuine["pct_of_relevant"] == 100.0


def test_q2_separates_wanted_from_never_intended() -> None:
    rows = [
        _row(),
        _row(
            purchase_intent="low",
            wishlist_behavior="browsing_only",
            purchase_status="unknown",
            high_intent_friction=False,
            blockers=[],
            purchase_blocker="no_blocker",
            original_text="just browsing outfits for inspiration not sure if it will fit",
            text="just browsing outfits for inspiration not sure if it will fit",
        ),
    ]
    payload = build_part1_answers(pd.DataFrame(rows), pd.DataFrame())
    split = payload["questions"]["q2"]["tables"]["wanted_vs_never"]
    assert split["wanted_but_did_not_purchase"] == 1
    assert split["never_intended"] == 1
    assert split["wanted_pct_of_relevant"] == 50.0


def test_q5_does_not_invent_alternative_counts() -> None:
    assert alternative_count_stated("I compared a few dresses on Myntra") is None
    assert alternative_count_stated("I shortlisted 3 dresses and cannot decide") == 3
    rows = [
        _row(
            wishlist_behavior="comparison_shortlist",
            purchase_blocker="comparison_uncertainty",
            blockers=["comparison_uncertainty"],
            original_text="I compared a few dresses and cannot decide",
            text="I compared a few dresses and cannot decide",
            evidence_quote="I compared a few dresses and cannot decide",
        )
    ]
    payload = build_part1_answers(pd.DataFrame(rows), pd.DataFrame())
    stated = payload["questions"]["q5"]["tables"]["stated_alternative_counts"]
    assert stated["n_conversations_stating_a_count"] == 0
    assert stated["median_stated_alternatives"] is None
    assert "No invented" in stated["note"] or "not invented" in stated["note"].lower() or "No number is invented" in stated["note"]


def test_q6_lists_all_required_sources_even_when_zero() -> None:
    payload = build_part1_answers(pd.DataFrame([_row()]), pd.DataFrame())
    sources = {r["source"] for r in payload["questions"]["q6"]["tables"]["by_source"]}
    assert sources == {
        "Google",
        "YouTube",
        "Instagram",
        "Reddit",
        "influencers",
        "friends/family",
        "other marketplaces",
        "brand websites",
        "physical stores",
    }
    youtube = next(r for r in payload["questions"]["q6"]["tables"]["by_source"] if r["source"] == "YouTube")
    google = next(r for r in payload["questions"]["q6"]["tables"]["by_source"] if r["source"] == "Google")
    assert youtube["evidence_count"] == 1
    assert google["evidence_count"] == 0


def test_q7_labels_evidence_strength_not_causation() -> None:
    payload = build_part1_answers(pd.DataFrame([_row()]), pd.DataFrame())
    answer = payload["questions"]["q7"]["direct_answer"]
    assert "evidence strength" in answer.lower()
    factors = {r["factor"] for r in payload["questions"]["q7"]["tables"]["factors"]}
    assert factors == {"FIT", "SIZE", "STYLING", "PRICE", "REVIEWS", "OCCASION", "SOCIAL VALIDATION"}


def test_q8_uses_intent_signals_not_conversion_rate() -> None:
    payload = build_part1_answers(pd.DataFrame([_row()]), pd.DataFrame())
    text = payload["questions"]["q8"]["direct_answer"]
    assert "signals associated with purchase intent" in text.lower()
    assert "actual 30-day conversion" in text.lower() or "not actual" in text.lower()


def test_chains_require_three_supporting_conversations() -> None:
    one = pd.DataFrame([_row()])
    payload = build_part1_answers(one, pd.DataFrame())
    assert payload["chains"] == []
    three = pd.DataFrame([_row(), _row(source_url="https://reddit.com/r/test/2"), _row(source_url="https://reddit.com/r/test/3")])
    payload2 = build_part1_answers(three, pd.DataFrame())
    assert any("fit/size" in c["chain"] for c in payload2["chains"])
    assert all(c["supporting_conversations"] >= 3 for c in payload2["chains"])


def test_handoff_has_ten_hypotheses_and_unknowns() -> None:
    payload = build_part1_answers(pd.DataFrame([_row()]), pd.DataFrame())
    h = payload["handoff"]
    assert len(h["interview_hypotheses"]) == 10
    cannot = " ".join(h["questions_public_data_cannot_answer"]).lower()
    assert "wishlist-to-purchase" in cannot
    assert "30-day" in cannot
    assert "myntra users" in cannot or "customer" in cannot


def test_classify_motivation_price_watch() -> None:
    row = pd.Series(_row(wishlist_behavior="price_watch", blockers=["waiting_for_price_drop"], purchase_blocker="waiting_for_price_drop"))
    assert classify_motivation(row) == "waiting for sale"
