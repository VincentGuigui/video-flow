from videoflow.analysis.align_tokens import align_global, align_local
from videoflow.analysis.textnorm import (
    Vocab,
    content_tokens,
    cue_spans,
    ends_with_cue,
    normalise_text,
    tokenize,
    word_keys,
)


def test_normalise_fr_elisions_accents_numbers() -> None:
    assert normalise_text("L'appareil coûte DEUX cents euros !", "fr") == (
        "l appareil coute 2 cents euros"
    )
    assert word_keys("qu’il", "fr") == ["qu", "il"]
    assert word_keys("aujourd'hui", "fr") == ["aujourd", "hui"]
    # "un" / "one" are articles too: kept as words
    assert normalise_text("un câble", "fr") == "un cable"
    assert normalise_text("Twenty-one cables", "en") == "20 one cables"


def test_fillers_tagged_not_removed() -> None:
    toks = tokenize(["euh", "alors", "on", "ouvre", "hum", "la", "boîte"], "fr")
    assert [t.key for t in toks] == ["euh", "alors", "on", "ouvre", "hum", "la", "boite"]
    assert [t.filler for t in toks] == [True, False, False, False, True, False, False]
    assert [t.key for t in content_tokens(toks)] == ["alors", "on", "ouvre", "la", "boite"]


def test_restart_cues_fr_en() -> None:
    fr = tokenize(["alors", "dans", "la...", "attends", "je", "reprends"], "fr")
    assert cue_spans(fr) == [(3, 6)]
    assert ends_with_cue(fr)
    en = tokenize(["so", "in", "the...", "wait", "let", "me", "start", "over"], "en")
    assert [t.key for t in en if t.cue] == ["wait", "let", "me", "start", "over"]
    assert ends_with_cue(en)
    assert not ends_with_cue(tokenize(["today", "we", "assemble", "the", "video"], "en"))
    # a filler after the cue does not hide it
    assert ends_with_cue(tokenize(["so", "wait", "let", "me", "start", "over", "uh"], "en"))


def test_vocab_merges_fuzzy_spellings_only_for_long_keys() -> None:
    v = Vocab()
    assert v.id("assembler") == v.id("assembl")
    assert v.id("la") != v.id("le")
    assert v.id("2") != v.id("3")


def test_local_alignment_ignores_stray_matches() -> None:
    long_ = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 21, 22, 23]
    short = [5, 20, 21, 22, 23]
    glob = align_global(short, long_)
    assert glob.matched == 5
    loc = align_local(short, long_, max_gap=3)
    assert loc.matched == 4
    assert loc.span_b == (12, 16)
    assert loc.cov_a == 0.8
