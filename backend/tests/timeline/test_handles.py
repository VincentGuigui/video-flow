from hypothesis import given
from hypothesis import strategies as st

from videoflow.timeline import handles


def test_split_follows_corrected_alignment_semantics() -> None:
    # (before the cut = right clip head, after the cut = left clip tail)
    assert handles.split(16, "center") == (8, 8)
    assert handles.split(15, "center") == (7, 8)
    assert handles.split(12, "start") == (0, 12)  # start: left tail T
    assert handles.split(12, "end") == (12, 0)  # end: right head T
    assert handles.split(0, "center") == (0, 0)


@given(
    st.sampled_from(handles.ALIGNMENTS),
    st.integers(min_value=0, max_value=500),
    st.integers(min_value=0, max_value=500),
)
def test_max_duration_is_tight(alignment: handles.AlignmentName, before: int, after: int) -> None:
    best = handles.max_duration(alignment, before, after)
    b, a = handles.split(best, alignment)
    assert b <= before and a <= after
    b, a = handles.split(best + 1, alignment)
    assert b > before or a > after


def test_check_reports_shortfall_and_fixes() -> None:
    result = handles.check(20, "center", right_head_available=4, left_tail_available=30)
    assert not result.ok
    assert (result.missing_before, result.missing_after) == (6, 0)
    assert result.max_by_alignment == {"center": 9, "start": 20, "end": 4}
    assert "freeze frame" in result.describe()


def test_check_unknown_availability_is_unlimited() -> None:
    assert handles.check(20, "end", None, None).ok


def test_check_fixes_bounded_by_visible_frames() -> None:
    result = handles.check(30, "end", 0, 100, before_visible=50, after_visible=10)
    assert result.max_by_alignment == {"center": 1, "start": 10, "end": 0}
