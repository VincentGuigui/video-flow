import csv
import io
import re

import opentimelineio as otio
import pytest

from tests.timeline.builders import ProjectBuilder, S, clip, transition
from tests.timeline.test_golden import short_handles
from videoflow.analysis.types import Transcript, Word
from videoflow.core.time import Rational, TimeRange
from videoflow.exporters.edl import export_edl
from videoflow.exporters.paper_edit import export_csv, export_markdown
from videoflow.exporters.srt import export_srt
from videoflow.project.models import AudioReplacement, TranscriptEdit
from videoflow.timeline.resolve import resolve


def word(text, start, end):
    return Word(text=text, start_us=int(start * S), end_us=int(end * S))


@pytest.mark.parametrize("alignment,offset", [("center", 7), ("start", 0), ("end", 15)])
def test_edl_dissolve_pair_has_correct_timecodes_and_no_spurious_event(alignment, offset):
    b = ProjectBuilder().asset("a", 30 * S).asset("b", 30 * S)
    b.beat("beat", clip("c1", "a", 5 * S, 9 * S), clip("c2", "b", 10 * S, 14 * S))
    b.transitions = [transition("t", "c1", "c2", alignment=alignment)]
    project = b.build()
    result = export_edl(resolve(project), project)
    lines = [v for v in result.text.splitlines() if re.match(r"\d{3} ", v)]
    assert len(lines) == 3
    assert [v.split()[0] for v in lines] == ["001", "002", "002"]
    assert [v.split()[3] for v in lines] == ["C", "C", "D"]
    assert all(len(v) <= 8 for v in result.reels)
    timeline = otio.adapters.read_from_string(result.text, adapter_name="cmx_3600", rate=30)
    track = timeline.video_tracks()[0]
    assert timeline.duration().value == 240
    assert track[0].source_range.duration.value == 120 - offset
    assert track[2].source_range.start_time.value == 300 - offset
    assert track[1].out_offset.value == 15


def test_srt_maps_trimmed_reordered_repeated_clips_and_clamps_at_cuts():
    b = ProjectBuilder(rate=Rational.of(25)).asset("a", 20 * S)
    b.beat("b1", clip("c1", "a", 5 * S, 7 * S))
    b.beat("b2", clip("c2", "a", S, 3 * S))
    b.beat("b3", clip("c3", "a", 5 * S, 7 * S))
    project = b.build()
    transcript = Transcript(
        words=[
            word("removed", 3, 4),
            word("Bonjour.", 5.2, 5.7),
            word("monde.", 6.8, 7.3),
            word("Encore.", 1.1, 1.4),
        ]
    )
    result = export_srt(resolve(project), project, {"a": transcript})
    assert "removed" not in result
    assert result.count("Bonjour.") == 2
    assert "00:00:00,200 --> 00:00:01,200" in result
    assert "00:00:01,800 --> 00:00:02,000" in result
    assert "00:00:02,100 --> 00:00:03,100" in result
    assert "00:00:04,200 --> 00:00:05,200" in result


def test_edl_missing_source_handles_fall_back_to_valid_cuts():
    project = short_handles()
    result = export_edl(resolve(project), project)
    assert any("missing source handles" in warning for warning in result.warnings)
    timeline = otio.adapters.read_from_string(result.text, adapter_name="cmx_3600", rate=25)
    assert timeline.duration().value == resolve(project).duration
    assert not any(isinstance(c, otio.schema.Transition) for c in timeline.video_tracks()[0])


def test_srt_replaced_audio_and_correction_are_used():
    b = ProjectBuilder().asset("a", 20 * S).asset("b", 20 * S)
    b.beat("beat", clip("c", "a", 5 * S, 9 * S))
    project = b.build()
    item = project.beats[0].cut[0]
    item.audio.mode = "replaced"
    item.audio.replacement = AudioReplacement(asset_id="b", source_in_us=10 * S)
    project.overrides.transcript_edits = [
        TranscriptEdit(
            id="edit",
            asset_id="b",
            range=TimeRange(start_us=11 * S, end_us=12 * S),
            text="corrigé.",
        )
    ]
    transcripts = {
        "a": Transcript(words=[word("wrong video", 6, 7)]),
        "b": Transcript(words=[word("euh", 10.1, 10.3), word("incorrect", 11, 12)]),
    }
    text = export_srt(resolve(project), project, transcripts)
    assert "corrigé." in text
    assert "00:00:01,000 --> 00:00:02,000" in text
    assert "incorrect" not in text and "wrong" not in text and "euh" not in text
    item.audio.mode = "muted"
    assert export_srt(resolve(project), project, transcripts) == ""


def test_srt_wraps_long_words_and_sentences_to_two_lines():
    b = ProjectBuilder().asset("a", 30 * S).beat("beat", clip("c", "a", 0, 20 * S))
    project = b.build()
    words = [word("x" * 200, 0, 4)] + [
        word("bonjour", 4 + i * 0.3, 4.2 + i * 0.3) for i in range(30)
    ]
    result = export_srt(resolve(project), project, {"a": Transcript(words=words)})
    for cue in result.strip().split("\n\n"):
        lines = cue.splitlines()
        assert len(lines[2:]) <= 2
        assert all(len(line) <= 42 for line in lines[2:])


def test_paper_edit_quotes_csv_and_escapes_markdown():
    b = ProjectBuilder().asset("a", 20 * S).beat("b", clip("c", "a", S, 3 * S))
    project = b.build()
    project.beats[0].label = "Intro | présentation"
    project.assets[0].path = 'C:/rushes/take, "one".mp4'
    transcripts = {"a": Transcript(words=[word("Bonjour <script> | monde", 1.1, 1.8)])}
    rows = list(csv.reader(io.StringIO(export_csv(resolve(project), project, transcripts))))
    assert rows[1][2] == project.assets[0].path
    assert rows[1][3:6] == ["00:00:01:00", "00:00:03:00", "00:00:02:00"]
    markdown = export_markdown(resolve(project), project, transcripts)
    assert "Intro \\| présentation" in markdown
    assert "&lt;script&gt;" in markdown
