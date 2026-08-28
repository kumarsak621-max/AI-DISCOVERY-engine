"""Deduplication tests."""

from processing.deduplication import deduplicate_records, flag_syndicated


def test_deduplicate_by_content_hash() -> None:
    records = [
        {"title": "A", "text": "Same body text about a Myntra wishlist item size issue.", "source": "reddit"},
        {"title": "A", "text": "Same body text about a Myntra wishlist item size issue.", "source": "youtube"},
        {"title": "B", "text": "A completely different conversation about waiting for EORS sale prices.", "source": "reddit"},
    ]
    unique, dupes = deduplicate_records(records)
    assert dupes == 1
    assert len(unique) == 2


def test_flag_syndicated_across_sources() -> None:
    text = "I will wait until the Myntra price drops on this dress before buying it ever."
    records = [
        {"text": text, "source": "reddit", "title": "one"},
        {"text": text, "source": "rss", "title": "two"},
    ]
    flagged = flag_syndicated(records)
    assert all(r["is_syndicated"] for r in flagged)


def test_not_syndicated_when_single_source() -> None:
    records = [
        {"text": "Unique text alpha about fit uncertainty on a kurta wishlist add.", "source": "reddit"},
        {"text": "Unique text beta about fake reviews on a saved Myntra product.", "source": "reddit"},
    ]
    flagged = flag_syndicated(records)
    assert all(r["is_syndicated"] is False for r in flagged)
