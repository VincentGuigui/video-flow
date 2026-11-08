import os

import pytest

from videoflow.analysis.types import Word
from videoflow.editor import analysis as module
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def test_correction_survives_read_only_source_and_rejects_stale_edits(tmp_path, monkeypatch):
    bundle = Bundle.create(tmp_path / "edit.video-flow", new_project("Words"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original")
    original = module.AnalysisFile(words=[Word(text="wrong", start_us=0, end_us=500000)])
    module.write_sidecar(source, original)
    os.utime(module.sidecar_path(source), (1, 1))
    save = module.save_atomic

    def write(path, data):
        if path.parent == source.parent:
            raise PermissionError("read-only source folder")
        save(path, data)

    monkeypatch.setattr(module, "save_atomic", write)
    module.correct_word(source, "digest", bundle, 0, "correct", "wrong")
    loaded = module.load_analysis(source, "digest", bundle)
    assert loaded.words[0].text == "correct"
    assert loaded.words[0].end_us == 500000
    assert source.read_bytes() == b"original"
    with pytest.raises(ValueError, match="changed"):
        module.correct_word(source, "digest", bundle, 0, "another", "wrong")
