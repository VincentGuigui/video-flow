"""Text normalisation for matching (04 "Text normalisation", 08 §3): FR first, EN second.

A word becomes one or more :class:`Token` (elisions are split). Each token carries a
comparison key (lowercase, NFKC, accent-free, punctuation removed, number words as
digits) and two tags: ``filler`` (ignored in matching, counted in quality) and ``cue``
(part of a restart cue such as "attends je reprends"; stripped before coverage).

:class:`Vocab` maps keys to integer ids, merging near-identical spellings (rapidfuzz
ratio >= 85 on keys of 4+ characters), so alignment runs on plain int lists.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz, process


def _lexicon(text: str) -> frozenset[str]:
    return frozenset(text.split())


FILLERS: dict[str, frozenset[str]] = {
    "fr": _lexicon("euh euhm heu hum hmm mmh mm bah ben beh bon ba hein pfff pff ah oh"),
    "en": _lexicon("uh um uhm erm er hmm mm mmm ah oh huh like"),
}
"""Filler lexicon per language (keys after normalisation)."""

RESTART_CUES: dict[str, tuple[tuple[str, ...], ...]] = {
    "fr": tuple(
        tuple(p.split())
        for p in (
            "attends je reprends",
            "attendez je reprends",
            "je reprends",
            "je recommence",
            "on recommence",
            "on reprend",
            "je refais",
            "on la refait",
            "on refait",
            "recommence",
            "reprends",
            "coupez",
            "pardon",
            "attends",
            "non attends",
        )
    ),
    "en": tuple(
        tuple(p.split())
        for p in (
            "wait let me start over",
            "let me start over",
            "let me start again",
            "let me try again",
            "let me redo that",
            "let me do that again",
            "start over",
            "one more time",
            "take two",
            "sorry",
            "wait",
        )
    ),
}
"""Restart-cue phrases per language (normalised keys). Longest match wins."""

_ELISION_RE = re.compile(r"^(?P<head>[a-z]{1,4})['’](?P<tail>\w.*)$")
_ELIDED = {"l", "d", "j", "m", "n", "s", "t", "c", "qu", "jusqu", "lorsqu", "puisqu"}
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)

_NUMBERS: dict[str, dict[str, str]] = {
    "fr": {
        "zero": "0", "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
        "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9", "dix": "10",
        "onze": "11", "douze": "12", "treize": "13", "quatorze": "14", "quinze": "15",
        "seize": "16", "vingt": "20", "trente": "30", "quarante": "40", "cinquante": "50",
        "soixante": "60", "cent": "100", "mille": "1000",
    },
    "en": {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11",
        "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
        "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19",
        "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
        "hundred": "100", "thousand": "1000",
    },
}  # fmt: skip
"""Single number words only; "un"/"one" are articles too, so they are left as words."""
_AMBIGUOUS_NUMBERS = {"un", "une", "one"}


@dataclass(frozen=True, slots=True)
class Token:
    key: str
    """Comparison key (normalised)."""
    word_index: int
    """Index of the source word in the word list given to :func:`tokenize`."""
    filler: bool = False
    cue: bool = False

    @property
    def content(self) -> bool:
        return not (self.filler or self.cue)


def lang_key(language: str | None) -> str:
    """Lexicon language for a project/ASR language code (``fr-FR`` -> ``fr``)."""
    base = (language or "fr").split("-")[0].split("_")[0].lower()
    return base if base in FILLERS else "en"


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _fold(text: str) -> str:
    return strip_accents(unicodedata.normalize("NFKC", text).casefold())


def word_keys(word: str, language: str | None = "fr") -> list[str]:
    """Comparison keys of one ASR word (several when an elision is split)."""
    folded = _fold(word).replace("’", "'")
    parts: list[str] = []
    for chunk in folded.split():
        m = _ELISION_RE.match(chunk)
        if m and m.group("head") in _ELIDED:
            parts += [m.group("head"), m.group("tail")]
        else:
            parts.append(chunk)
    numbers = _NUMBERS[lang_key(language)]
    keys: list[str] = []
    for part in parts:
        for piece in _NON_WORD_RE.split(part.replace("_", " ")):
            if not piece:
                continue
            if piece in numbers and piece not in _AMBIGUOUS_NUMBERS:
                piece = numbers[piece]
            keys.append(piece)
    return keys


def normalise_text(text: str, language: str | None = "fr") -> str:
    """Accent-insensitive comparison form of a whole text."""
    return " ".join(k for w in text.split() for k in word_keys(w, language))


def _mark_cues(keys: Sequence[str], language: str | None) -> list[bool]:
    phrases = sorted(RESTART_CUES[lang_key(language)], key=len, reverse=True)
    marks = [False] * len(keys)
    i = 0
    while i < len(keys):
        for phrase in phrases:
            n = len(phrase)
            if tuple(keys[i : i + n]) == phrase:
                for j in range(i, i + n):
                    marks[j] = True
                i += n
                break
        else:
            i += 1
    return marks


def tokenize(words: Sequence[str], language: str | None = "fr") -> list[Token]:
    """Tokens for a list of words (ASR word texts), tagging fillers and restart cues."""
    fillers = FILLERS[lang_key(language)]
    flat: list[tuple[str, int]] = [
        (key, wi) for wi, w in enumerate(words) for key in word_keys(w, language)
    ]
    cues = _mark_cues([k for k, _ in flat], language)
    return [
        Token(key=k, word_index=wi, filler=k in fillers, cue=cue)
        for (k, wi), cue in zip(flat, cues, strict=True)
    ]


def content_tokens(tokens: Iterable[Token]) -> list[Token]:
    return [t for t in tokens if t.content]


def cue_spans(tokens: Sequence[Token]) -> list[tuple[int, int]]:
    """Restart-cue runs as ``(first token, one past last token)``."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for i, t in enumerate(tokens):
        if t.cue and start is None:
            start = i
        elif not t.cue and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(tokens)))
    return spans


def ends_with_cue(tokens: Sequence[Token]) -> bool:
    """True when the last non-filler token belongs to a restart cue."""
    for t in reversed(tokens):
        if t.filler:
            continue
        return t.cue
    return False


class Vocab:
    """Key -> int id, merging fuzzy-equal keys (ratio >= ``fuzzy_cutoff``, len >= 4).

    Ids depend on insertion order; feed keys in a canonical order for determinism.
    """

    def __init__(self, fuzzy_cutoff: float = 85.0, min_fuzzy_len: int = 4) -> None:
        self.fuzzy_cutoff = fuzzy_cutoff
        self.min_fuzzy_len = min_fuzzy_len
        self._ids: dict[str, int] = {}
        self._long_keys: list[str] = []
        self._long_ids: list[int] = []

    def __len__(self) -> int:
        return len(self._ids)

    def id(self, key: str) -> int:
        found = self._ids.get(key)
        if found is not None:
            return found
        new = len(self._ids)
        if len(key) >= self.min_fuzzy_len and self._long_keys and not key.isdigit():
            hit = process.extractOne(
                key, self._long_keys, scorer=fuzz.ratio, score_cutoff=self.fuzzy_cutoff
            )
            if hit is not None:
                new = self._long_ids[hit[2]]
        self._ids[key] = new
        if len(key) >= self.min_fuzzy_len and new == len(self._ids) - 1:
            self._long_keys.append(key)
            self._long_ids.append(new)
        return new

    def ids(self, tokens: Iterable[Token]) -> list[int]:
        return [self.id(t.key) for t in tokens]
