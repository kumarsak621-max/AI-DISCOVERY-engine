"""Language detection for English, Hindi, and Hinglish. Original evidence is preserved."""

from __future__ import annotations

import re

try:
    from langdetect import LangDetectException, detect
except ImportError:  # pragma: no cover
    detect = None  # type: ignore[assignment]

    class LangDetectException(Exception):  # type: ignore[no-redef]
        pass

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

HINGLISH_MARKERS = {
    "yaar", "na", "nahi", "haan", "kya", "hai", "bhai", "yaar", "accha",
    "theek", "mat", "lena", "lo", "kar", "raha", "rahe", "wala", "wali",
    "fit", "size", "sasta", "mehnga", "sale", "wishlist", "cart",
}


def detect_language(text: str) -> str:
    if not text or not text.strip():
        return "unknown"
    has_devanagari = bool(_DEVANAGARI_RE.search(text))
    latin_words = [w.lower() for w in _LATIN_WORD_RE.findall(text)]
    hinglish_hits = sum(1 for w in latin_words if w in HINGLISH_MARKERS)

    if has_devanagari and latin_words:
        return "hinglish"
    if has_devanagari:
        return "hi"
    if hinglish_hits >= 2 and latin_words:
        return "hinglish"

    if detect is None:
        return "en" if latin_words else "unknown"
    try:
        code = detect(text)
        if code == "hi":
            return "hi"
        if code == "en":
            return "en"
        return code
    except LangDetectException:
        return "unknown"


def should_preserve_original(language: str) -> bool:
    return language in {"hi", "hinglish"}
