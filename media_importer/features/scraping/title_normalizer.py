"""Conservative title normalization shared by all identity matching paths."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "＇": "'"})
_DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-"})
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class TitleComparison:
    strict_exact: bool
    loose_exact: bool
    similarity: float


class TitleNormalizer:
    """Normalize punctuation and Unicode without transliteration or NLP guesses."""

    @staticmethod
    def strict(value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = text.translate(_APOSTROPHES).translate(_DASHES).casefold()
        text = _NON_WORD.sub(" ", text)
        return _WHITESPACE.sub(" ", text).strip()

    @classmethod
    def strict_key(cls, value: str) -> str:
        return cls.strict(value).replace(" ", "")

    @classmethod
    def loose(cls, value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        # Treat ampersand as the word "and" only in the loose comparison path.
        text = re.sub(r"\s*&\s*", " and ", text)
        text = unicodedata.normalize("NFKD", text)
        text = "".join(char for char in text if not unicodedata.combining(char))
        return cls.strict(text)

    @classmethod
    def loose_key(cls, value: str) -> str:
        return cls.loose(value).replace(" ", "")

    @classmethod
    def compare(cls, left: str, right: str) -> TitleComparison:
        left_strict = cls.strict_key(left)
        right_strict = cls.strict_key(right)
        left_loose = cls.loose_key(left)
        right_loose = cls.loose_key(right)
        return TitleComparison(
            strict_exact=bool(left_strict and left_strict == right_strict),
            loose_exact=bool(left_loose and left_loose == right_loose),
            similarity=(
                SequenceMatcher(None, left_loose, right_loose).ratio()
                if left_loose and right_loose else 0.0
            ),
        )
