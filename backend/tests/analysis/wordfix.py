"""Word fixtures mirroring the WP4 retake scripts (``videoflow.samples.SCRIPTS``).

Timing is synthetic but deterministic: each word lasts 320 ms, words are 60 ms apart,
utterances are separated by ``samples.GAP_S`` (1 s), starting at 0.5 s like the samples.
"""

from collections.abc import Callable, Iterator, Sequence

from videoflow.analysis.types import Word
from videoflow.samples import GAP_S, SCRIPTS

WORD_US = 320_000
INTRA_GAP_US = 60_000
START_US = 500_000


def words_for(
    utterances: Sequence[str], gaps_us: Sequence[int] | None = None, start_us: int = START_US
) -> list[Word]:
    """Words for consecutive utterances; ``gaps_us[i]`` follows utterance ``i``."""
    gaps = list(gaps_us) if gaps_us is not None else [round(GAP_S * 1e6)] * len(utterances)
    t = start_us
    out: list[Word] = []
    for k, text in enumerate(utterances):
        for n, w in enumerate(text.split()):
            if n:
                t += INTRA_GAP_US
            out.append(Word(text=w, start_us=t, end_us=t + WORD_US, prob=0.9))
            t += WORD_US
        if k < len(utterances) - 1:
            t += gaps[k]
    return out


def retake_script(lang: str) -> list[str]:
    """False start then three full takes, as in ``samples.py``."""
    d = SCRIPTS[lang]
    return [d["false_start"], d["take"], d["take"], d["take"]]


def counter(prefix: str = "seg") -> Iterator[str]:
    n = 0
    while True:
        n += 1
        yield f"{prefix}_{n:03d}"


def id_factory(prefix: str = "seg") -> Callable[[], str]:
    it = counter(prefix)
    return lambda: next(it)
