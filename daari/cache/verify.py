"""Second-stage verification for L1 semantic-cache hits (#168).

A cosine threshold cannot separate a paraphrase from a near-miss, because the
similarity distributions of correct and incorrect matches overlap. "what is 15%
of 200" and "what is 15% of 300" are nearly identical textually and have
different answers; "how do I list files" and "how can I list files" are further
apart textually and have the same answer. Embedding distance ranks these in the
wrong order, so a second stage has to look at the text itself.

The guards are deliberately lexical and cheap. They target the specific edits
that change an answer while barely moving an embedding: different numbers,
different or reordered units, a flipped negation, a reversed comparison, and
differing content words. Politeness, filler, and casing are ignored, because
those move an embedding without changing the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'._-]*")

_NEGATIONS = frozenset(
    {"not", "no", "never", "none", "cannot", "cant", "dont", "doesnt", "isnt", "wont", "without"}
)

# Swapping one of these for its partner inverts the answer.
_OPPOSITES: tuple[frozenset[str], ...] = (
    frozenset({"greater", "less"}),
    frozenset({"greater", "smaller"}),
    frozenset({"more", "fewer"}),
    frozenset({"more", "less"}),
    frozenset({"larger", "smaller"}),
    frozenset({"bigger", "smaller"}),
    frozenset({"faster", "slower"}),
    frozenset({"before", "after"}),
    frozenset({"first", "last"}),
    frozenset({"ascending", "descending"}),
    frozenset({"asc", "desc"}),
    frozenset({"max", "min"}),
    frozenset({"maximum", "minimum"}),
    frozenset({"highest", "lowest"}),
    frozenset({"oldest", "newest"}),
    frozenset({"enable", "disable"}),
    frozenset({"add", "remove"}),
    frozenset({"start", "stop"}),
    frozenset({"true", "false"}),
    frozenset({"allow", "deny"}),
    frozenset({"include", "exclude"}),
    frozenset({"encode", "decode"}),
    frozenset({"increase", "decrease"}),
)

_UNITS = frozenset(
    {
        "ms", "millisecond", "milliseconds",
        "sec", "secs", "second", "seconds",
        "min", "mins", "minute", "minutes",
        "hr", "hrs", "hour", "hours",
        "day", "days", "week", "weeks", "month", "months", "year", "years",
        "byte", "bytes", "kb", "mb", "gb", "tb",
        "km", "cm", "mm", "meter", "meters", "metre", "metres",
        "mile", "miles", "ft", "feet", "inch", "inches",
        "kg", "mg", "lb", "lbs", "oz", "gram", "grams",
        "celsius", "fahrenheit", "kelvin",
        "usd", "eur", "gbp", "dollars", "euros",
    }
)

# British/American spelling that does not change the answer (#208).
_SPELLING = {
    "summarise": "summarize",
    "summarises": "summarizes",
    "summarised": "summarized",
    "summarising": "summarizing",
    "normalise": "normalize",
    "normalises": "normalizes",
    "normalised": "normalized",
    "normalising": "normalizing",
    "colour": "color",
    "colours": "colors",
}

# Curated verb/adj pairs from the SYN corpus. Do not add antonyms here
# (start/stop stays in _OPPOSITES).
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"quickest", "fastest", "quicker", "faster", "quick", "fast"}),
    frozenset({"resolve", "fix"}),
    frozenset({"triggers", "causes", "trigger", "cause"}),
    frozenset({"create", "write"}),
    frozenset({"launch", "start"}),
)

# Filler that moves an embedding without changing the answer.
_STOPWORDS = frozenset(
    {
        "a", "about", "an", "and", "any", "are", "as", "at", "be", "but", "by", "can", "could",
        "describe", "did", "do", "does", "explain", "for", "from", "get", "give", "had", "has",
        "have", "help", "how", "i", "if", "in", "into", "is", "it", "its", "just", "kindly",
        "like", "list", "me", "my", "of", "on", "or", "please", "show", "so", "some", "tell",
        "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to",
        "us", "use", "using", "want", "was", "we", "were", "what", "whats", "when", "where",
        "which", "who", "why", "will", "with", "would", "you", "your",
    }
)


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    reason: str | None = None


class LexicalVerifier:
    """Rejects cache candidates whose wording changes the answer."""

    name = "lexical"

    def verify(self, candidate: str, stored: str) -> VerificationResult:
        if candidate == stored:
            return VerificationResult(True)

        if _numbers(candidate) != _numbers(stored):
            return VerificationResult(False, "numbers differ")

        candidate_words = _tokens(candidate)
        stored_words = _tokens(stored)

        # Order matters: "10 km to miles" and "10 miles to km" use the same
        # units and mean opposite conversions.
        if _sequence(candidate_words, _UNITS) != _sequence(stored_words, _UNITS):
            return VerificationResult(False, "units differ")

        candidate_set = frozenset(candidate_words)
        stored_set = frozenset(stored_words)

        if len(candidate_set & _NEGATIONS) != len(stored_set & _NEGATIONS):
            return VerificationResult(False, "negation differs")

        for pair in _OPPOSITES:
            in_candidate = pair & candidate_set
            in_stored = pair & stored_set
            # Only an actual swap inverts the answer. One side merely using a
            # word the other omits ("start" vs "launch") is not an inversion.
            if in_candidate and in_stored and in_candidate != in_stored:
                return VerificationResult(False, f"opposed terms {sorted(pair)}")

        candidate_content = _content(candidate_set)
        stored_content = _content(stored_set)
        # A substitution risks changing the answer ("staging" for "production");
        # one side simply carrying an extra word does not. Additions are
        # therefore allowed and substitutions are not.
        if (candidate_content - stored_content) and (stored_content - candidate_content):
            return VerificationResult(False, "content words substituted")

        return VerificationResult(True)


def build_verifier(mode: str | None) -> LexicalVerifier | None:
    """Verifier for a `cache.l1.verify` mode. Unknown modes disable it."""
    if mode == "lexical":
        return LexicalVerifier()
    if mode == "model":
        # Reserved for a cross-encoder or small local judge. Falls back to
        # lexical so selecting it never silently means no verification.
        return LexicalVerifier()
    return None


def _tokens(text: str) -> list[str]:
    return [word.lower().replace("'", "").strip("._-") for word in _WORD_RE.findall(text)]


def _sequence(words: list[str], vocabulary: frozenset[str]) -> tuple[str, ...]:
    return tuple(word for word in words if word in vocabulary)


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(match.replace(",", "") for match in _NUMBER_RE.findall(text))


def _canonical(word: str) -> str:
    word = _SPELLING.get(word, word)
    for group in _SYNONYM_GROUPS:
        if word in group:
            return next(iter(sorted(group)))
    return word


def _content(words: frozenset[str]) -> frozenset[str]:
    return frozenset(
        _canonical(word)
        for word in words
        if word and word not in _STOPWORDS and word not in _UNITS and word not in _NEGATIONS
    )
