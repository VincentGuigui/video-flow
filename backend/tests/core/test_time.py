from fractions import Fraction
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from videoflow.core.time import (
    Rational,
    TimeRange,
    clip_frames,
    format_timecode,
    frame_to_us,
    frames,
    frames_to_samples,
    parse_timecode,
    samples,
    seconds_to_us,
)

RATES = [Rational.of(25), Rational.of(30000, 1001), Rational.of(24000, 1001)]
RATE_IDS = ["25", "29.97", "23.976"]


@pytest.mark.parametrize(
    ("fps", "expected"),
    [
        (25.0, (25, 1)),
        (29.97, (30000, 1001)),
        (29.97002997, (30000, 1001)),
        (23.976, (24000, 1001)),
        (59.94, (60000, 1001)),
        (24.0, (24, 1)),
        (12.5, (25, 2)),
    ],
)
def test_rational_from_float(fps: float, expected: tuple[int, int]) -> None:
    r = Rational.from_float(fps)
    assert (r.num, r.den) == expected


def test_rational_validation_and_json() -> None:
    with pytest.raises(ValueError):
        Rational(num=0, den=1)
    r = Rational.of(30000, 1001)
    assert r.dump() == {"num": 30000, "den": 1001}
    assert r.nominal == 30 and r.is_ntsc
    assert r.fraction == Fraction(30000, 1001)


def test_quantisation_rule_round_half_up() -> None:
    r = Rational.of(25)
    assert frames(0, r) == 0
    assert frames(19_999, r) == 0  # 0.499975 frames
    assert frames(20_000, r) == 1  # exactly half a frame rounds up
    assert frames(40_000, r) == 1
    assert frames(-20_000, r) == -1  # symmetric
    assert clip_frames(1_000_000, 3_000_000, r) == 50


@pytest.mark.parametrize("rate", RATES, ids=RATE_IDS)
@given(n=st.integers(min_value=-(10**7), max_value=10**8))
def test_frame_start_round_trip(rate: Rational, n: int) -> None:
    assert frames(frame_to_us(n, rate), rate) == n


@pytest.mark.parametrize("rate", RATES, ids=RATE_IDS)
@settings(max_examples=25, deadline=None)
@given(
    start=st.integers(min_value=0, max_value=10**9),
    durations=st.lists(st.integers(min_value=1, max_value=20_000_000), min_size=300, max_size=300),
)
def test_no_drift_over_300_contiguous_clips(
    rate: Rational, start: int, durations: list[int]
) -> None:
    """Cutting one source into 300 contiguous clips loses or gains no frame."""
    bounds = [start]
    for d in durations:
        bounds.append(bounds[-1] + d)
    per_clip = [clip_frames(a, b, rate) for a, b in pairwise(bounds)]
    assert sum(per_clip) == clip_frames(bounds[0], bounds[-1], rate)
    # Timeline positions are integer cumulative sums: exact, no float accumulation.
    position = 0
    for count in per_clip:
        assert count >= 0
        position += count
    assert position == frames(bounds[-1], rate) - frames(bounds[0], rate)


@pytest.mark.parametrize("rate", RATES, ids=RATE_IDS)
@settings(max_examples=25, deadline=None)
@given(
    clips=st.lists(
        st.tuples(st.integers(0, 10**6), st.integers(1, 2_000)), min_size=300, max_size=300
    )
)
def test_frame_aligned_clips_are_exact(rate: Rational, clips: list[tuple[int, int]]) -> None:
    """Clips whose in/out sit on source frame starts keep their exact frame counts, so
    the timeline total over 300 clips equals the sum of the intended lengths."""
    total = 0
    for first_frame, length in clips:
        s_in = frame_to_us(first_frame, rate)
        s_out = frame_to_us(first_frame + length, rate)
        count = clip_frames(s_in, s_out, rate)
        assert count == length
        total += count
    assert total == sum(length for _, length in clips)


@pytest.mark.parametrize("rate", RATES, ids=RATE_IDS)
@given(a=st.integers(0, 10**10), b=st.integers(0, 10**10))
def test_per_clip_error_below_one_frame(rate: Rational, a: int, b: int) -> None:
    s_in, s_out = min(a, b), max(a, b)
    exact = Fraction(s_out - s_in, 1_000_000) * rate.fraction
    assert abs(clip_frames(s_in, s_out, rate) - exact) < 1


def test_samples_follow_video_frames() -> None:
    r = Rational.of(30000, 1001)
    assert frames_to_samples(30000, r, 48_000) == 48_048_000
    assert samples(1_000_000, 48_000) == 48_000
    assert frames_to_samples(565, Rational.of(30), 48_000) == 904_000


def test_seconds_to_us() -> None:
    assert seconds_to_us(12.05) == 12_050_000
    assert seconds_to_us(0.0000005) == 1
    assert seconds_to_us(48.2) == 48_200_000


@pytest.mark.parametrize(
    ("frame", "rate", "text"),
    [
        (0, Rational.of(25), "00:00:00:00"),
        (25 * 3600 + 24, Rational.of(25), "01:00:00:24"),
        (1799, Rational.of(30000, 1001), "00:00:59:29"),
        (1800, Rational.of(30000, 1001), "00:01:00:00"),  # non-drop: no frame skipped
        (-1, Rational.of(24), "-00:00:00:01"),
    ],
)
def test_timecode_non_drop(frame: int, rate: Rational, text: str) -> None:
    assert format_timecode(frame, rate) == text
    assert parse_timecode(text, rate) == frame


def test_timecode_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_timecode("00:00:00:30", Rational.of(30))
    with pytest.raises(ValueError):
        parse_timecode("00:00:00", Rational.of(30))


def test_time_range() -> None:
    a = TimeRange(start_us=0, end_us=10)
    b = TimeRange(start_us=5, end_us=15)
    assert a.overlap_us(b) == 5
    assert a.iou(b) == pytest.approx(5 / 15)
    with pytest.raises(ValueError):
        TimeRange(start_us=5, end_us=4)
