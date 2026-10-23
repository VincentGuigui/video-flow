"""S12 clustering into beats: constrained average linkage (08 D Clustering, H16).

1. SIMULTANEOUS relations and user must-links are contracted first (union-find).
2. Average linkage on ``distance = 1 - weight`` (missing edge = 1), merging the closest
   pair while its distance is ``<= tau``. Two clusters linked by a cannot-link are never
   merged, so the result can never violate one. A cannot-link inside a must-link group is
   a conflict: the must-link wins and the pair is reported.
3. Edges only join segments of the same kind, so beats are speech or visual.

The graph is sparse (top-k candidates), so the merge loop runs on adjacency dicts and a
lazy heap: re-clustering 2000 segments for a slider move takes milliseconds. Ties are
broken by input order, so the output is deterministic for a given input order.
"""

import heapq
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from videoflow.analysis.types import Relation, Segment, ThresholdProfile

CONTRACTED = frozenset({"simultaneous"})

TAU_MIN = 0.05
TAU_MAX = 0.95


def tau_for_sensitivity(sensitivity: float, profile: ThresholdProfile) -> float:
    """Slider (0 = only near-identical takes, 1 = loose) -> distance threshold.

    Piecewise linear through ``(0, TAU_MIN)``, ``(0.5, profile.tau)``, ``(1, TAU_MAX)``.
    """
    s = min(1.0, max(0.0, sensitivity))
    mid = min(TAU_MAX, max(TAU_MIN, profile.tau))
    if s <= 0.5:
        return TAU_MIN + (mid - TAU_MIN) * (s / 0.5)
    return mid + (TAU_MAX - mid) * ((s - 0.5) / 0.5)


@dataclass
class ClusterResult:
    clusters: list[list[str]] = field(default_factory=list)
    """Each cluster lists node ids in input order; clusters sorted by first member."""
    conflicts: list[tuple[str, str]] = field(default_factory=list)
    """Cannot-links overridden by must-links / sync groups."""

    def cluster_of(self) -> dict[str, int]:
        return {node: k for k, members in enumerate(self.clusters) for node in members}


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def cluster(
    nodes: Sequence[str],
    kinds: Mapping[str, str],
    relations: Iterable[Relation],
    tau: float,
    must_link: Iterable[tuple[str, str]] = (),
    cannot_link: Iterable[tuple[str, str]] = (),
) -> ClusterResult:
    index = {node: i for i, node in enumerate(nodes)}
    n = len(nodes)
    uf = _UnionFind(n)
    pair_weight: dict[tuple[int, int], float] = {}
    for rel in relations:
        ia, ib = index.get(rel.a), index.get(rel.b)
        if ia is None or ib is None or ia == ib:
            continue
        if rel.kind in CONTRACTED:
            uf.union(ia, ib)
            continue
        if kinds.get(rel.a) != kinds.get(rel.b):
            continue
        key = (min(ia, ib), max(ia, ib))
        pair_weight[key] = max(pair_weight.get(key, 0.0), min(1.0, max(0.0, rel.score)))
    for a, b in must_link:
        if a in index and b in index:
            uf.union(index[a], index[b])

    roots = [uf.find(i) for i in range(n)]
    size: dict[int, int] = {}
    for r in roots:
        size[r] = size.get(r, 0) + 1

    result = ClusterResult()
    cannot: dict[int, set[int]] = {r: set() for r in size}
    for a, b in cannot_link:
        if a not in index or b not in index:
            continue
        ra, rb = roots[index[a]], roots[index[b]]
        if ra == rb:
            result.conflicts.append((a, b))
        else:
            cannot[ra].add(rb)
            cannot[rb].add(ra)

    weight: dict[int, dict[int, float]] = {r: {} for r in size}
    for (ia, ib), w in pair_weight.items():
        ra, rb = roots[ia], roots[ib]
        if ra != rb and w > 0:
            weight[ra][rb] = weight[ra].get(rb, 0.0) + w
            weight[rb][ra] = weight[rb].get(ra, 0.0) + w

    version = dict.fromkeys(size, 0)
    heap: list[tuple[float, int, int, int, int]] = []

    def push(x: int, y: int) -> None:
        if y in cannot[x]:
            return
        dist = 1.0 - weight[x][y] / (size[x] * size[y])
        if dist <= tau:
            a, b = (x, y) if x < y else (y, x)
            heapq.heappush(heap, (dist, a, b, version[a], version[b]))

    for x in sorted(weight):
        for y in sorted(weight[x]):
            if x < y:
                push(x, y)

    while heap:
        _, x, y, vx, vy = heapq.heappop(heap)
        if x not in size or y not in size or version[x] != vx or version[y] != vy:
            continue
        # merge y into x (x has the smaller key: deterministic survivor)
        for c, w in weight.pop(y).items():
            del weight[c][y]
            if c != x:
                weight[x][c] = weight[x].get(c, 0.0) + w
                weight[c][x] = weight[c].get(x, 0.0) + w
        for c in cannot.pop(y):
            cannot[c].discard(y)
            cannot[c].add(x)
            cannot[x].add(c)
        size[x] += size.pop(y)
        del version[y]
        uf.parent[y] = x
        version[x] += 1
        for c in weight[x]:
            push(x, c)

    members: dict[int, list[str]] = {}
    for i, node in enumerate(nodes):
        members.setdefault(uf.find(i), []).append(node)
    result.clusters = sorted(members.values(), key=lambda m: index[m[0]])
    return result


def find_orphans(
    clusters: Sequence[Sequence[str]],
    segments: Mapping[str, Segment],
    mean_prob: Mapping[str, float | None] | None = None,
    false_starts: Iterable[str] = (),
    min_duration_us: int = 1_000_000,
    min_prob: float = 0.4,
) -> list[str]:
    """Singleton clusters flagged as noise: too short, low ASR confidence, or a lone
    false start (ends with a restart cue). Off-topic (LLM) is added after S15."""
    probs = mean_prob or {}
    fs = set(false_starts)
    out: list[str] = []
    for members in clusters:
        if len(members) != 1:
            continue
        sid = members[0]
        seg = segments.get(sid)
        if seg is None:
            continue
        prob = probs.get(sid)
        if (
            seg.end_us - seg.start_us < min_duration_us
            or (prob is not None and prob < min_prob)
            or sid in fs
        ):
            out.append(sid)
    return out
