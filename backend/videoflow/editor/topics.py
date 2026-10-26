"""Deterministic transcript sentences, topic sections and extractive summaries.

Topic boundaries follow lexical cohesion between neighbouring sentence windows
(TextTiling-style) plus long pauses. Titles are the most section-specific words.
"""

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence

from pydantic import Field

from videoflow.analysis.textnorm import strip_accents
from videoflow.analysis.types import Word
from videoflow.core.base import CamelModel

SENTENCE_GAP_US = 700_000
MAX_SENTENCE_WORDS = 30
MIN_TOPIC_US = 15_000_000
MIN_BOUNDARY_SCORE = 0.6
MAX_TOPICS = 12
TITLE_WORDS = 5
WINDOW = 3

_STOP_WORDS = """
    the and this that with from have here there what when where which while your you
    they them then than just like will would could should about into been were very
    also some more most only over such these those other being really because going
    dans pour avec sans sous mais donc alors cette ceci cela celle celui sont nous vous
    elle elles ils leur leurs comme plus tres tout tous toute toutes aussi bien encore
    voila quoi quand avoir etre fait faire peut veux voir juste parce euh hmm ben bah
"""
STOP = frozenset(_STOP_WORDS.split())


class Sentence(CamelModel):
    start_us: int
    end_us: int
    text: str


class Topic(CamelModel):
    start_us: int
    end_us: int
    title: str
    sentences: list[Sentence] = Field(default_factory=list)


def sentences(words: Sequence[Word]) -> list[Sentence]:
    """Split on sentence punctuation, pauses and a maximum length."""
    result: list[Sentence] = []
    current: list[Word] = []

    def close() -> None:
        if current:
            text = " ".join(w.text.strip() for w in current if w.text.strip())
            start, end = current[0].start_us, current[-1].end_us
            result.append(Sentence(start_us=start, end_us=end, text=text))
            current.clear()

    for index, word in enumerate(words):
        current.append(word)
        following = words[index + 1] if index + 1 < len(words) else None
        if (
            following is None
            or re.search(r"[.!?…]$", word.text.strip())
            or following.start_us - word.end_us >= SENTENCE_GAP_US
            or len(current) >= MAX_SENTENCE_WORDS
        ):
            close()
    return result


def keys(text: str) -> list[str]:
    folded = strip_accents(text.casefold())
    tokens = re.findall(r"\w+", folded)
    return [t for t in tokens if len(t) > 3 and t not in STOP and not t.isdigit()]


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    dot = sum(v * b[k] for k, v in a.items())
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm if norm else 0.0


def boundaries(items: Sequence[Sentence]) -> list[int]:
    """Indices i where a topic starts at items[i] (excluding 0).

    A boundary needs a clear drop in vocabulary overlap (and/or a long pause) relative
    to the rest of the clip; every topic lasts at least MIN_TOPIC_US.
    """
    if len(items) < 2 or items[-1].end_us - items[0].start_us < 2 * MIN_TOPIC_US:
        return []
    bags = [Counter(keys(s.text)) for s in items]
    scored: list[tuple[float, int]] = []
    for i in range(1, len(items)):
        before = sum(bags[max(0, i - WINDOW) : i], Counter[str]())
        after = sum(bags[i : i + WINDOW], Counter[str]())
        pause = items[i].start_us - items[i - 1].end_us
        scored.append((1 - _cosine(before, after) + 0.5 * min(pause / 2_000_000, 1.0), i))
    values = [v for v, _ in scored]
    mean = sum(values) / len(values)
    spread = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    threshold = max(MIN_BOUNDARY_SCORE, mean + 0.5 * spread)
    chosen: list[int] = []
    for value, i in sorted(scored, key=lambda x: (-x[0], x[1])):
        if value < threshold or len(chosen) == MAX_TOPICS - 1:
            break
        cuts = sorted([*chosen, i])
        starts = [items[0].start_us, *(items[c].start_us for c in cuts)]
        ends = [*(items[c - 1].end_us for c in cuts), items[-1].end_us]
        if all(e - s >= MIN_TOPIC_US for s, e in zip(starts, ends, strict=True)):
            chosen = cuts
    return chosen


def keyword_title(section: Sequence[Sentence], others: Sequence[Sequence[Sentence]]) -> str:
    """Up to five words most specific to this section, in order of first use."""
    tokens = [t for s in section for t in keys(s.text)]
    if not tokens:
        words = " ".join(s.text for s in section).split()
        return " ".join(words[:TITLE_WORDS]) or "Untitled"
    counts = Counter(tokens)
    present = [set(t for s in other for t in keys(s.text)) for other in others]
    total = len(present) + 1

    def weight(token: str) -> float:
        df = 1 + sum(token in p for p in present)
        return counts[token] * math.log(1 + total / df)

    best = set(sorted(counts, key=lambda t: (-weight(t), tokens.index(t)))[:TITLE_WORDS])
    ordered = [t for t in dict.fromkeys(tokens) if t in best]
    original = {strip_accents(w.casefold()): w for s in section for w in re.findall(r"\w+", s.text)}
    title = " ".join(original.get(t, t) for t in ordered)
    return title[:1].upper() + title[1:]


def detect_topics(words: Sequence[Word], title: Callable[[str], str] | None = None) -> list[Topic]:
    """Topic sections with titles; `title` (e.g. a local LLM) falls back to keywords."""
    items = sentences(words)
    if not items:
        return []
    cuts = [0, *boundaries(items), len(items)]
    sections = [items[a:b] for a, b in zip(cuts, cuts[1:], strict=False)]
    topics: list[Topic] = []
    for index, section in enumerate(sections):
        name = ""
        if title is not None:
            try:
                name = title(" ".join(s.text for s in section))
            except (ValueError, RuntimeError):
                name = ""
        name = " ".join(name.split()[:TITLE_WORDS]) or keyword_title(
            section, sections[:index] + sections[index + 1 :]
        )
        topics.append(
            Topic(
                start_us=section[0].start_us,
                end_us=section[-1].end_us,
                title=name,
                sentences=list(section),
            )
        )
    return topics


def extractive_summary(words: Sequence[Word], limit: int = 280) -> str:
    """The most representative sentences, in spoken order, within `limit` characters."""
    items = sentences(words)
    if not items:
        return ""
    counts = Counter(t for s in items for t in keys(s.text))
    ranked = sorted(
        range(len(items)),
        key=lambda i: (
            -sum(counts[t] for t in set(keys(items[i].text)))
            / math.sqrt(len(keys(items[i].text)) or 1)
        ),
    )
    picked: list[int] = []
    length = 0
    for i in ranked:
        size = len(items[i].text) + 1
        if picked and length + size > limit:
            continue
        picked.append(i)
        length += size
        if len(picked) == 2:
            break
    text = " ".join(items[i].text for i in sorted(picked))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
