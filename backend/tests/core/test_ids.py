import pytest

from videoflow.core import ids


def test_new_id_format() -> None:
    value = ids.new_id(ids.SEGMENT)
    assert value.startswith("seg_")
    assert len(value) == len("seg_") + 26
    assert ids.is_id(value, ids.SEGMENT)
    assert not ids.is_id(value, ids.BEAT)
    assert ids.id_prefix(value) == "seg"


def test_ids_unique_and_sorted() -> None:
    values = [ids.new_id(ids.CLIP) for _ in range(20_000)]
    assert len(set(values)) == len(values)
    assert values == sorted(values)  # monotonic, even within one millisecond


@pytest.mark.parametrize("prefix", ["", "Seg", "seg-x", "toolongprefix", "1ab"])
def test_invalid_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        ids.new_id(prefix)


def test_is_id_rejects_non_ids() -> None:
    assert not ids.is_id("seg_a04_12200_26400_sp")
    assert ids.id_prefix("b03") is None
