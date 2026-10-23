from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from videoflow.analysis.cache import (
    META_FILE,
    TMP_PREFIX,
    EntryWriter,
    StageCache,
    canonical_json,
    stage_key,
)

BACKEND = Path(__file__).resolve().parents[2]
H = "ab" * 20  # a content hash


def test_key_is_deterministic_and_order_independent():
    a = stage_key(H, "asr", 1, {"model": "parakeet", "lang": "fr", "beam": 4})
    b = stage_key(H, "asr", 1, {"beam": 4, "lang": "fr", "model": "parakeet"})
    assert a == b and len(a) == 32 and all(c in "0123456789abcdef" for c in a)
    assert stage_key([H], "asr", 1, {"model": "parakeet", "lang": "fr", "beam": 4}) == a


@pytest.mark.parametrize(
    "variant",
    [
        dict(inputs="cd" * 20),
        dict(stage="vad"),
        dict(version=2),
        dict(params={"model": "whisper", "lang": "fr", "beam": 4}),
        dict(params={"model": "parakeet", "lang": "fr", "beam": 4.5}),
        dict(params={"model": "parakeet", "lang": "fr", "beam": 4, "extra": None}),
    ],
)
def test_key_changes_with_each_component(variant):
    base = dict(
        inputs=H, stage="asr", version=1, params={"model": "parakeet", "lang": "fr", "beam": 4}
    )
    assert stage_key(**base) != stage_key(**{**base, **variant})


def test_canonical_json_types():
    txt = canonical_json({"b": Fraction(30000, 1001), "a": Path("x") / "y", "c": {3, 1}})
    assert txt == '{"a":"x/y","b":"30000/1001","c":[1,3]}'
    with pytest.raises(TypeError):
        canonical_json({"x": object()})
    with pytest.raises(ValueError):
        stage_key(H, "Bad Stage", 1)


def test_ensure_computes_once_and_reads_back(tmp_path: Path):
    cache = StageCache(tmp_path)
    key = stage_key(H, "embed", 1, {"model": "e5-small"})
    calls = 0

    def produce(w: EntryWriter) -> None:
        nonlocal calls
        calls += 1
        w.write_json({"segments": ["s1", "s2"], "text": "été"})
        w.write_npy("vectors", np.eye(2, 384, dtype=np.float32))
        w.write_bytes("raw.bin", b"\x00\x01")

    entry, computed = cache.ensure("embed", key, produce, meta={"version": 1})
    assert computed and calls == 1
    again, computed2 = cache.ensure("embed", key, produce)
    assert not computed2 and calls == 1 and again == entry
    assert entry.read_json() == {"segments": ["s1", "s2"], "text": "été"}
    vec = entry.read_npy("vectors.npy")
    assert vec.shape == (2, 384) and vec.dtype == np.float32
    assert entry.read_npy("vectors.npy", mmap=True)[0, 0] == 1.0
    assert entry.read_bytes("raw.bin") == b"\x00\x01"
    meta = entry.meta
    assert meta["stage"] == "embed" and meta["key"] == key and meta["version"] == 1
    assert meta["files"] == ["data.json", "raw.bin", "vectors.npy"]
    assert cache.keys("embed") == [key]
    assert not [p for p in (tmp_path / "embed").iterdir() if p.name.startswith(TMP_PREFIX)]


def test_failed_producer_leaves_nothing(tmp_path: Path):
    cache = StageCache(tmp_path)
    key = stage_key(H, "asr", 1)

    def produce(w: EntryWriter) -> None:
        w.write_json({"partial": True})
        raise RuntimeError("engine crashed")

    with pytest.raises(RuntimeError):
        cache.ensure("asr", key, produce)
    assert cache.get("asr", key) is None
    assert list((tmp_path / "asr").iterdir()) == []


def test_concurrent_writer_loses_gracefully(tmp_path: Path):
    cache = StageCache(tmp_path)
    key = stage_key(H, "vad", 1)
    with cache.writer("vad", key) as outer:
        outer.write_json({"who": "outer"})
        with cache.writer("vad", key) as inner:
            inner.write_json({"who": "inner"})
    # first commit wins, the second is discarded without error
    entry = cache.get("vad", key)
    assert entry is not None and entry.read_json() == {"who": "inner"}
    assert [p.name for p in (tmp_path / "vad").iterdir()] == [key]


async def test_aensure_with_coroutine(tmp_path: Path):
    cache = StageCache(tmp_path)
    key = stage_key(H, "peaks", 1)

    async def produce(w: EntryWriter) -> None:
        w.path("peaks.bin").write_bytes(b"xyz")  # e.g. written by FFmpeg

    entry, computed = await cache.aensure("peaks", key, produce)
    assert computed and entry.read_bytes("peaks.bin") == b"xyz"
    assert "peaks.bin" in entry.meta["files"]
    _, computed = await cache.aensure("peaks", key, produce)
    assert not computed


def test_invalidate_and_bad_names(tmp_path: Path):
    cache = StageCache(tmp_path)
    key = stage_key(H, "vad", 1)
    cache.ensure("vad", key, lambda w: w.write_json([]))
    assert cache.invalidate("vad", key)
    assert cache.get("vad", key) is None and not cache.invalidate("vad", key)
    assert list((tmp_path / "vad").iterdir()) == []
    with pytest.raises(ValueError):
        cache.get("vad", "../etc")
    with pytest.raises(ValueError):
        cache.ensure("vad", key, lambda w: w.write_bytes("../x", b""))
    with pytest.raises(ValueError):
        cache.ensure("vad", key, lambda w: w.write_bytes(META_FILE, b""))


def test_sweep_respects_age(tmp_path: Path):
    cache = StageCache(tmp_path)
    stale = tmp_path / "asr" / f"{TMP_PREFIX}deadbeef-1"
    stale.mkdir(parents=True)
    (stale / "data.json").write_text("{")
    assert cache.sweep(max_age_s=3600) == 0
    old = time.time() - 7200
    os.utime(stale, (old, old))
    assert cache.sweep(max_age_s=3600) == 1
    assert not stale.exists()


PIPELINE = textwrap.dedent(
    """
    import json
    import sys
    import time
    from pathlib import Path

    from videoflow.analysis.cache import StageCache, stage_key

    root, log, slow = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "slow"
    cache = StageCache(root)


    def note(line):
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(line + "\\n")
            fh.flush()


    def stage(name, inputs, value):
        key = stage_key(inputs, name, 1, {"p": 1})

        def produce(w):
            note("start " + name)
            w.write_json({"value": value})
            if name == "b" and slow:
                note("waiting")
                time.sleep(60)
            note("done " + name)

        entry, computed = cache.ensure(name, key, produce)
        if not computed:
            note("skip " + name)
        return key, entry.read_json()["value"]


    if __name__ == "__main__":
        ka, va = stage("a", "ab" * 20, 1)
        kb, vb = stage("b", ka, va + 1)
        kc, vc = stage("c", kb, vb + 1)
        note(f"result {vc}")
    """
)


def test_kill_mid_stage_then_rerun_skips_completed(tmp_path: Path):
    """NFR-04: a process killed during stage b leaves a; the rerun skips a only."""
    script = tmp_path / "pipeline.py"
    script.write_text(PIPELINE, encoding="utf-8")
    root, log = tmp_path / "analysis", tmp_path / "log.txt"
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    cmd = [sys.executable, str(script), str(root), str(log)]
    proc = subprocess.Popen([*cmd, "slow"], env=env)
    try:
        deadline = time.monotonic() + 30
        while "waiting" not in (log.read_text() if log.exists() else ""):
            assert time.monotonic() < deadline, "pipeline did not reach stage b"
            assert proc.poll() is None, "pipeline exited early"
            time.sleep(0.02)
    finally:
        proc.kill()  # SIGKILL / TerminateProcess: no cleanup handlers run
        proc.wait(10)
    assert log.read_text().splitlines() == ["start a", "done a", "start b", "waiting"]
    cache = StageCache(root)
    assert len(cache.keys("a")) == 1 and cache.keys("b") == [] and cache.keys("c") == []
    leftovers = [p for p in (root / "b").iterdir() if p.name.startswith(TMP_PREFIX)]
    assert len(leftovers) == 1  # the half-written temp dir is never visible as an entry

    log.unlink()
    subprocess.run([*cmd, "fast"], env=env, check=True, timeout=60)
    assert log.read_text().splitlines() == [
        "skip a",
        "start b",
        "done b",
        "start c",
        "done c",
        "result 3",
    ]
    assert cache.sweep(max_age_s=0) == 1
    assert json.loads((root / "c" / cache.keys("c")[0] / "data.json").read_text()) == {"value": 3}
