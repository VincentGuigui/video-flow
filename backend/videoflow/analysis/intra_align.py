"""S13 intra-beat alignment (04 §6): lay alternates under the reference take.

* Speech: global token alignment (LCS) of each take against the reference. Anchors at
  matched word starts; divergences are runs of unmatched take words; the lane offset is
  ``t_ref(first anchor) - t_take(first anchor)``.
* Visual: DTW over frame embeddings; the offset is taken at the first strong match.
* Sync groups: exact asset offset from :class:`SyncResult`.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from videoflow.analysis.align_tokens import align_global
from videoflow.analysis.relations import SegmentTokens
from videoflow.analysis.types import (
    AlignmentAnchor,
    Segment,
    SyncResult,
    TakeAlignment,
    Word,
)
from videoflow.core.time import Micros, TimeRange

type Matrix = npt.NDArray[np.floating]


def align_speech(
    reference: Segment,
    take: Segment,
    ref_tokens: SegmentTokens,
    take_tokens: SegmentTokens,
    ref_words: Sequence[Word],
    take_words: Sequence[Word],
) -> TakeAlignment:
    al = align_global(ref_tokens.ids, take_tokens.ids)
    anchors: list[AlignmentAnchor] = []
    last_word: tuple[int, int] | None = None
    for i, j in al.pairs:
        rw, tw = ref_tokens.word_index[i], take_tokens.word_index[j]
        if (rw, tw) == last_word:
            continue  # several tokens of one word (elision)
        last_word = (rw, tw)
        anchors.append(
            AlignmentAnchor(ref_us=ref_words[rw].start_us, take_us=take_words[tw].start_us)
        )

    matched_take_words = {take_tokens.word_index[j] for _, j in al.pairs}
    content_words = sorted(set(take_tokens.word_index))
    divergences: list[TimeRange] = []
    run: list[int] = []
    for w in [*content_words, None]:
        if w is not None and w not in matched_take_words:
            run.append(w)
            continue
        if run:
            divergences.append(
                TimeRange(start_us=take_words[run[0]].start_us, end_us=take_words[run[-1]].end_us)
            )
            run = []

    offset = (
        anchors[0].ref_us - anchors[0].take_us if anchors else reference.start_us - take.start_us
    )
    return TakeAlignment(
        reference_segment_id=reference.id,
        segment_id=take.id,
        offset_us=offset,
        anchors=anchors,
        divergences=divergences,
    )


def dtw_path(a: Matrix, b: Matrix) -> list[tuple[int, int]]:
    """DTW warping path on cosine distance between two embedding sequences."""
    an = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    bn = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    cost = 1.0 - an @ bn.T
    n, m = cost.shape
    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            acc[i, j] = cost[i - 1, j - 1] + min(acc[i - 1, j], acc[i, j - 1], acc[i - 1, j - 1])
    path: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        step = int(np.argmin((acc[i - 1, j - 1], acc[i - 1, j], acc[i, j - 1])))
        if step == 0:
            i, j = i - 1, j - 1
        elif step == 1:
            i -= 1
        else:
            j -= 1
    return path[::-1]


def align_visual(
    reference: Segment,
    take: Segment,
    ref_frames: Matrix,
    take_frames: Matrix,
    frame_step_us: Micros = 500_000,
    strong: float = 0.8,
) -> TakeAlignment:
    """Frames sampled every ``frame_step_us`` from each segment start (2 fps default)."""
    anchors: list[AlignmentAnchor] = []
    if len(ref_frames) and len(take_frames):
        an = ref_frames / np.maximum(np.linalg.norm(ref_frames, axis=1, keepdims=True), 1e-12)
        bn = take_frames / np.maximum(np.linalg.norm(take_frames, axis=1, keepdims=True), 1e-12)
        for i, j in dtw_path(ref_frames, take_frames):
            if float(an[i] @ bn[j]) >= strong:
                anchors.append(
                    AlignmentAnchor(
                        ref_us=reference.start_us + i * frame_step_us,
                        take_us=take.start_us + j * frame_step_us,
                    )
                )
    offset = (
        anchors[0].ref_us - anchors[0].take_us if anchors else reference.start_us - take.start_us
    )
    return TakeAlignment(
        reference_segment_id=reference.id, segment_id=take.id, offset_us=offset, anchors=anchors
    )


def align_sync(reference: Segment, take: Segment, sync: SyncResult) -> TakeAlignment:
    """Offset from the asset sync (``asset_b time + offset = asset_a time``)."""
    if reference.asset_id == sync.asset_a and take.asset_id == sync.asset_b:
        offset = sync.offset_us
    elif reference.asset_id == sync.asset_b and take.asset_id == sync.asset_a:
        offset = -sync.offset_us
    else:
        raise ValueError("sync result does not link these segments' assets")
    return TakeAlignment(reference_segment_id=reference.id, segment_id=take.id, offset_us=offset)
