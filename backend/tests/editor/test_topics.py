import json

from videoflow.analysis.types import Transcript, Word
from videoflow.editor.analysis import AnalysisFile, describe, read_sidecar
from videoflow.editor.topics import detect_topics, extractive_summary, sentences
from videoflow.engines.summary import parse_title

BATTERY = [
    "The battery charger plugs into the wall.",
    "This battery charger delivers sixty five watts.",
    "The cable for the battery charger is braided.",
    "A battery charger this small is convenient.",
    "The charger cable is two meters long.",
    "Charging the battery takes one hour.",
]
SCREEN = [
    "Now look at the screen display.",
    "The screen brightness reaches one thousand nits.",
    "Display colours on this screen are accurate.",
    "The screen refresh rate is high.",
    "Brightness and display contrast look great.",
    "The display panel covers the whole front.",
]


def words(lines: list[str], start_s: float = 0, step_s: float = 7.5) -> list[Word]:
    result: list[Word] = []
    for index, line in enumerate(lines):
        t = int((start_s + index * step_s) * 1_000_000)
        for token in line.split():
            result.append(Word(text=token, start_us=t, end_us=t + 300_000))
            t += 350_000
    return result


def test_sentences_split_on_punctuation_and_pauses() -> None:
    items = sentences(words(["One two three.", "Four five"]) + words(["six"], start_s=30))
    assert [s.text for s in items] == ["One two three.", "Four five", "six"]
    assert items[0].start_us == 0


def test_two_subjects_give_two_titled_topics_with_timecodes() -> None:
    topics = detect_topics(words(BATTERY + SCREEN))
    assert len(topics) == 2
    first, second = topics
    assert first.start_us == 0 and first.end_us < second.start_us
    assert second.start_us == 45_000_000
    assert "battery" in first.title.casefold() or "charger" in first.title.casefold()
    assert "screen" in second.title.casefold() or "display" in second.title.casefold()
    assert all(len(t.title.split()) <= 5 for t in topics)
    assert [s.text for s in second.sentences] == SCREEN


def test_short_clip_is_one_topic_and_llm_title_is_capped() -> None:
    topics = detect_topics(words(BATTERY[:2]), title=lambda _: "A very long generated title here")
    assert len(topics) == 1
    assert topics[0].title == "A very long generated title"


def test_failed_llm_title_falls_back_to_keywords() -> None:
    def broken(_: str) -> str:
        raise ValueError("no title")

    assert detect_topics(words(BATTERY), title=broken)[0].title


def test_extractive_summary_is_short_and_from_transcript() -> None:
    summary = extractive_summary(words(BATTERY + SCREEN))
    assert 0 < len(summary) <= 280
    assert all(part in " ".join(BATTERY + SCREEN) for part in summary.split(". ")[:1])


def test_describe_and_old_sidecars_include_topics(tmp_path) -> None:
    analysis = describe(Transcript(words=words(BATTERY + SCREEN)), "hash")
    assert len(analysis.topics) == 2 and analysis.summary
    source = tmp_path / "clip.mov"
    old = AnalysisFile(source_hash="hash", words=words(BATTERY)).dump()
    old.pop("topics")
    source.with_suffix(".json").write_text(json.dumps(old), encoding="utf-8")
    loaded = read_sidecar(source, "hash")
    assert loaded is not None and len(loaded.topics) == 1


def test_parse_title_strips_label_and_quotes() -> None:
    assert parse_title('Title: "Unboxing the new phone today now"\nextra') == (
        "Unboxing the new phone today"
    )


def test_one_subject_over_ninety_seconds_stays_one_topic() -> None:
    assert len(detect_topics(words(BATTERY + BATTERY))) == 1
