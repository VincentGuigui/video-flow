"""Token alignment on integer id lists (08 §3 for 04 §4.1 and §6).

The base alignment is the LCS (rapidfuzz, C speed): matched pairs in order, gaps free.
:func:`align_local` then keeps the densest chain of matches (consecutive matches at most
``max_gap`` tokens apart on both sides), which behaves like a local / semi-global
alignment: a short take matched inside a long one is not polluted by stray common words
("la", "the") far away in the long one.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz.distance import LCSseq


@dataclass(frozen=True, slots=True)
class Alignment:
    pairs: tuple[tuple[int, int], ...]
    """Matched positions ``(i in a, j in b)``, increasing on both sides."""
    len_a: int
    len_b: int

    @property
    def matched(self) -> int:
        return len(self.pairs)

    @property
    def cov_a(self) -> float:
        return self.matched / self.len_a if self.len_a else 0.0

    @property
    def cov_b(self) -> float:
        return self.matched / self.len_b if self.len_b else 0.0

    @property
    def lex(self) -> float:
        total = self.len_a + self.len_b
        return 2 * self.matched / total if total else 0.0

    @property
    def span_a(self) -> tuple[int, int]:
        """Matched span in ``a`` as ``(first, one past last)``; ``(0, 0)`` if empty."""
        return (self.pairs[0][0], self.pairs[-1][0] + 1) if self.pairs else (0, 0)

    @property
    def span_b(self) -> tuple[int, int]:
        return (self.pairs[0][1], self.pairs[-1][1] + 1) if self.pairs else (0, 0)


def align_global(a: Sequence[int], b: Sequence[int]) -> Alignment:
    """All LCS matches between ``a`` and ``b``."""
    pairs: list[tuple[int, int]] = []
    if a and b:
        for block in LCSseq.editops(a, b).as_matching_blocks():
            pairs.extend((block.a + k, block.b + k) for k in range(block.size))
    return Alignment(tuple(pairs), len(a), len(b))


def align_local(a: Sequence[int], b: Sequence[int], max_gap: int = 3) -> Alignment:
    """Densest chain of LCS matches: consecutive pairs skip at most ``max_gap`` tokens."""
    full = align_global(a, b)
    if not full.pairs:
        return full
    best: tuple[int, int] = (0, 0)
    start = 0
    pairs = full.pairs
    for k in range(1, len(pairs) + 1):
        end_chain = k == len(pairs) or (
            pairs[k][0] - pairs[k - 1][0] - 1 > max_gap
            or pairs[k][1] - pairs[k - 1][1] - 1 > max_gap
        )
        if end_chain:
            if k - start > best[1] - best[0]:
                best = (start, k)
            start = k
    return Alignment(pairs[best[0] : best[1]], len(a), len(b))
