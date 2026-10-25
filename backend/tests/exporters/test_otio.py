import json
import zipfile
from pathlib import Path

import opentimelineio as otio
import pytest

from tests.timeline.builders import ProjectBuilder, S, clip, project_overlay, transition
from tests.timeline.test_golden import alignments, full_fixture, ntsc_ripple, short_handles
from videoflow.core.time import Rational, TimeRange
from videoflow.exporters.otio_compile import compile_timeline, media_url, serialize
from videoflow.exporters.otioz import write_otioz
from videoflow.project.models import TakeRef
from videoflow.timeline.resolve import resolve


@pytest.mark.parametrize("build", [alignments, full_fixture, ntsc_ripple, short_handles])
def test_otio_round_trip_preserves_timing_and_metadata(build):
    project = build()
    original = project.dump()
    resolved = resolve(project)
    timeline = compile_timeline(resolved, project)
    result = otio.adapters.read_from_string(serialize(timeline), adapter_name="otio_json")
    assert result.duration().value == resolved.duration
    assert result.metadata["videoflow"]["rate"]["num"] == resolved.rate.num
    for source in resolved.tracks:
        if source.id not in ("V1", "A1"):
            continue
        track = next(t for t in result.tracks if t.name == source.id)
        clips = [c for c in track if isinstance(c, otio.schema.Clip | otio.schema.Gap)]
        for expected, actual in zip(source.clips, clips, strict=True):
            assert actual.source_range.duration.value == expected.duration
            assert actual.metadata["videoflow"]["itemId"] == expected.item_id
            assert track.range_of_child(actual).start_time.value == expected.timeline_start
        transitions = [t for t in track if isinstance(t, otio.schema.Transition)]
        if source.id == "V1":
            for expected, actual in zip(resolved.transitions, transitions, strict=True):
                assert actual.in_offset.value == expected.left_frames
                assert actual.out_offset.value == expected.right_frames
                assert actual.metadata["videoflow"]["transition"]["type"] == expected.type
    assert project.dump() == original
    assert serialize(timeline) == serialize(compile_timeline(resolved, project))


def test_otio_golden():
    project = alignments()
    data = json.loads(serialize(compile_timeline(resolve(project), project)))
    golden = Path(__file__).with_name("alignments.otio")
    assert data == json.loads(golden.read_text(encoding="utf-8"))


def test_overlapping_overlays_keep_positions_on_separate_lanes():
    b = ProjectBuilder().asset("a", 20 * S).beat("b", clip("c", "a", S, 11 * S))
    b.overlays = [project_overlay("o1", "a", S, 4 * S), project_overlay("o2", "a", 2 * S, 4 * S)]
    project = b.build()
    timeline = compile_timeline(resolve(project), project)
    tracks = [t for t in timeline.tracks if t.name.startswith("V2")]
    assert len(tracks) == 2
    for track, start in zip(tracks, [30, 60], strict=True):
        picture = next(c for c in track if isinstance(c, otio.schema.Clip))
        assert track.range_of_child(picture).start_time.value == start
    assert timeline.duration().value == 300


def test_muted_and_silent_sources_are_gaps():
    b = ProjectBuilder().asset("a", 10 * S).asset("b", 10 * S)
    b.beat("beat", clip("c1", "a", S, 3 * S), clip("c2", "b", S, 3 * S))
    project = b.build()
    project.beats[0].cut[0].audio.mode = "muted"
    project.assets[1].probe.audio_streams = []
    timeline = compile_timeline(resolve(project), project)
    audio = next(t for t in timeline.tracks if t.name == "A1")
    assert all(isinstance(c, otio.schema.Gap) for c in audio)
    assert audio.duration().value == 120


def test_audio_cut_omits_transition_and_replacement_uses_own_source():
    b = ProjectBuilder().asset("a", 10 * S).asset("b", 10 * S)
    b.beat("beat", clip("c1", "a", S, 3 * S), clip("c2", "a", 4 * S, 6 * S))
    b.transitions = [transition("t", "c1", "c2")]
    project = b.build()
    project.transitions[0].audio = "cut"
    from videoflow.project.models import AudioReplacement

    project.beats[0].cut[1].audio.mode = "replaced"
    project.beats[0].cut[1].audio.replacement = AudioReplacement(asset_id="b", source_in_us=2 * S)
    timeline = compile_timeline(resolve(project), project)
    audio = next(t for t in timeline.tracks if t.name == "A1")
    assert len(audio) == 2
    assert audio[1].source_range.start_time.value == 60
    assert audio[1].media_reference.target_url.endswith("b.mp4")


def test_alternates_are_disabled_and_optional():
    b = ProjectBuilder().asset("a", 20 * S).beat("b", clip("c", "a", S, 3 * S))
    project = b.build()
    project.beats[0].takes = [
        TakeRef(segment_id="seg_alt", asset_id="a", range=TimeRange(start_us=5 * S, end_us=15 * S))
    ]
    resolved = resolve(project)
    assert not any(t.name.startswith("ALT") for t in compile_timeline(resolved, project).tracks)
    result = compile_timeline(resolved, project, include_alternates=True)
    alt = next(t for t in result.tracks if t.name.startswith("ALT"))
    assert not alt.enabled
    assert alt[0].metadata["videoflow"]["segmentId"] == "seg_alt"
    assert result.duration().value == resolved.duration


def test_file_urls_escape_windows_and_posix_paths():
    assert media_url("C:\\Rushes\\take 1 é.mp4").startswith("file:///C:/Rushes/take%201%20")
    assert media_url("/rushes/take 1.mp4") == "file:///rushes/take%201.mp4"


def test_otioz_same_basename_round_trip_with_real_files(tmp_path):
    b = ProjectBuilder(rate=Rational.of(25)).asset("a", 10 * S).asset("b", 10 * S)
    b.beat("beat", clip("c1", "a", S, 3 * S), clip("c2", "b", S, 3 * S))
    project = b.build()
    for i, asset in enumerate(project.assets):
        folder = tmp_path / str(i)
        folder.mkdir()
        media = folder / "take.mp4"
        media.write_bytes(bytes([i]) * 100)
        asset.path = str(media)
    timeline = compile_timeline(resolve(project), project)
    original = serialize(timeline)
    destination = tmp_path / "edit.otioz"
    write_otioz(timeline, destination)
    with zipfile.ZipFile(destination) as archive:
        assert archive.read("media/0001_take.mp4") == bytes(100)
        assert archive.read("media/0002_take.mp4") == bytes([1]) * 100
        assert len(archive.namelist()) == 4  # each asset used on V1 and A1, stored once
    result = otio.adapters.read_from_file(str(destination), adapter_name="otioz")
    assert result.duration().value == 100
    assert serialize(timeline) == original
    # Missing media must preserve a previously exported archive and leave no temp file.
    previous = destination.read_bytes()
    Path(project.assets[0].path).unlink()
    with pytest.raises(FileNotFoundError):
        write_otioz(timeline, destination)
    assert destination.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))
