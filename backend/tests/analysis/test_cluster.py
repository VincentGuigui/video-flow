import random
import time

from hypothesis import given, settings
from hypothesis import strategies as st

from videoflow.analysis.cluster import cluster, find_orphans, tau_for_sensitivity
from videoflow.analysis.types import Relation, Segment, ThresholdProfile


def _rel(a: str, b: str, w: float, kind: str = "retake") -> Relation:
    return Relation(a=a, b=b, kind=kind, score=w)


NODES = ["s1", "s2", "s3", "s4", "s5"]
KINDS = dict.fromkeys(NODES, "speech")


def test_average_linkage_threshold() -> None:
    rels = [_rel("s1", "s2", 0.9), _rel("s2", "s3", 0.8), _rel("s4", "s5", 0.3)]
    # s1-s2 (d=0.1), then {s1,s2}-s3: avg d = 1 - 0.8/2 = 0.6
    assert cluster(NODES, KINDS, rels, tau=0.5).clusters == [["s1", "s2"], ["s3"], ["s4"], ["s5"]]
    assert cluster(NODES, KINDS, rels, tau=0.7).clusters == [
        ["s1", "s2", "s3"],
        ["s4", "s5"],
    ]


def test_cannot_link_never_merged_and_must_link_first() -> None:
    rels = [_rel("s1", "s2", 0.95), _rel("s2", "s3", 0.95), _rel("s1", "s3", 0.95)]
    res = cluster(NODES, KINDS, rels, tau=0.9, cannot_link=[("s1", "s3")])
    assert res.clusters == [["s1", "s2"], ["s3"], ["s4"], ["s5"]]
    res = cluster(NODES, KINDS, rels, tau=0.9, must_link=[("s4", "s5")])
    assert res.clusters == [["s1", "s2", "s3"], ["s4", "s5"]]
    # must-link wins over a contradictory cannot-link, reported as a conflict
    res = cluster(NODES, KINDS, [], tau=0.5, must_link=[("s1", "s5")],
                  cannot_link=[("s5", "s1")])  # fmt: skip
    assert res.clusters[0] == ["s1", "s5"] and res.conflicts == [("s5", "s1")]


def test_simultaneous_contracted_and_kinds_separate() -> None:
    kinds = {"s1": "speech", "s2": "speech", "v1": "visual", "v2": "visual"}
    rels = [
        _rel("s1", "s2", 1.0, "simultaneous"),
        _rel("s1", "v1", 0.99),  # cross-kind edge ignored
        _rel("v1", "v2", 0.9, "visual_duplicate"),
    ]
    res = cluster(list(kinds), kinds, rels, tau=0.5)
    assert res.clusters == [["s1", "s2"], ["v1", "v2"]]


def test_sensitivity_mapping() -> None:
    prof = ThresholdProfile(model_id="m", tau=0.4)
    assert tau_for_sensitivity(0.5, prof) == 0.4
    assert tau_for_sensitivity(0.0, prof) < tau_for_sensitivity(0.25, prof) < 0.4
    assert 0.4 < tau_for_sensitivity(0.75, prof) < tau_for_sensitivity(1.0, prof) <= 0.95


def test_orphans() -> None:
    segs = {
        "s1": Segment(id="s1", asset_id="a", kind="speech", start_us=0, end_us=500_000),
        "s2": Segment(id="s2", asset_id="a", kind="speech", start_us=0, end_us=3_000_000),
        "s3": Segment(id="s3", asset_id="a", kind="speech", start_us=0, end_us=3_000_000),
        "s4": Segment(id="s4", asset_id="a", kind="speech", start_us=0, end_us=3_000_000),
        "s5": Segment(id="s5", asset_id="a", kind="speech", start_us=0, end_us=3_000_000),
    }
    clusters = [["s1"], ["s2"], ["s3"], ["s4", "s5"]]
    assert find_orphans(clusters, segs, {"s2": 0.2}, false_starts=["s3"]) == ["s1", "s2", "s3"]


def _random_graph(n: int, k: int, seed: int) -> tuple[list[str], list[Relation]]:
    rng = random.Random(seed)
    nodes = [f"seg_{i:05d}" for i in range(n)]
    rels: list[Relation] = []
    for i in range(n):
        for _ in range(k // 2):
            j = rng.randrange(n)
            if j != i:
                rels.append(_rel(nodes[i], nodes[j], round(rng.random(), 3)))
    # planted beats: groups of 4 retakes
    for g in range(0, n - 3, 4):
        for a in range(g, g + 4):
            for b in range(a + 1, g + 4):
                rels.append(_rel(nodes[a], nodes[b], 0.9))
    return nodes, rels


@settings(max_examples=60, deadline=None)
@given(
    n=st.integers(min_value=2, max_value=25),
    seed=st.integers(min_value=0, max_value=10_000),
    tau=st.floats(min_value=0.05, max_value=0.99),
)
def test_property_cannot_link_respected_and_deterministic(n: int, seed: int, tau: float) -> None:
    nodes, rels = _random_graph(n, 6, seed)
    rng = random.Random(seed + 1)
    cannot = [(rng.choice(nodes), rng.choice(nodes)) for _ in range(n // 2)]
    cannot = [(a, b) for a, b in cannot if a != b]
    kinds = dict.fromkeys(nodes, "speech")
    res = cluster(nodes, kinds, rels, tau, cannot_link=cannot)
    where = res.cluster_of()
    assert sorted(where) == sorted(nodes)
    for a, b in cannot:
        assert where[a] != where[b]
    shuffled = rels[:]
    rng.shuffle(shuffled)
    assert cluster(nodes, kinds, shuffled, tau, cannot_link=cannot).clusters == res.clusters


def test_recluster_2000_segments_under_200ms() -> None:
    nodes, rels = _random_graph(2000, 10, 7)
    kinds = dict.fromkeys(nodes, "speech")
    cannot = [(nodes[i], nodes[i + 1]) for i in range(0, 2000, 50)]
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        res = cluster(nodes, kinds, rels, 0.5, cannot_link=cannot)
        best = min(best, time.perf_counter() - t0)
    assert best < 0.2, f"re-cluster took {best * 1000:.0f} ms"
    assert len(res.clusters) < 2000
