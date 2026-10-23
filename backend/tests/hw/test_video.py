import shutil
import sys

import pytest

from videoflow.hw import video
from videoflow.media.caps import FFmpegCaps, probe_caps


def fake_caps(**kw) -> FFmpegCaps:
    base = dict(
        ffmpeg="ffmpeg", ffprobe="ffprobe", version="7.0", version_tuple=(7, 0, 0),
        graph_flag="-/filter_complex",
        encoders=frozenset({"libx264", "h264_nvenc", "h264_qsv", "h264_vaapi", "h264_amf",
                            "h264_mf", "hevc_nvenc"}),
        hwaccels=frozenset({"cuda", "qsv", "vaapi", "d3d11va"}),
    )  # fmt: skip
    base.update(kw)
    return FFmpegCaps(**base)


def runner_allowing(*needles: str):
    calls: list[list[str]] = []

    def run(args: list[str]) -> bool:
        calls.append(args)
        return any(n in args for n in needles)

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_candidate_order_windows():
    names = [e.encoder for e in video.encoder_candidates("h264", "win32")]
    assert names == ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"]
    assert [d.hwaccel for d in video.decode_candidates("win32")] == ["cuda", "qsv", "d3d11va"]


def test_candidate_order_linux(monkeypatch):
    monkeypatch.setattr(video, "_vaapi_device", lambda: "/dev/dri/renderD128")
    names = [e.encoder for e in video.encoder_candidates("h264", "linux")]
    assert names == ["h264_nvenc", "h264_qsv", "h264_vaapi"]
    vaapi = video.encoder_candidates("h264", "linux")[-1]
    assert "-vaapi_device" in vaapi.init_args and "hwupload" in (vaapi.upload_filter or "")
    assert video.decode_candidates("linux")[-1].input_args()[:2] == ["-hwaccel", "vaapi"]


def test_probe_keeps_only_working(monkeypatch):
    monkeypatch.setattr(video, "_vaapi_device", lambda: "/dev/dri/renderD128")
    runner = runner_allowing("h264_qsv", "qsv", "libx264")
    rep = video.probe_video_hw(fake_caps(), runner=runner, platform="linux")
    assert [e.encoder for e in rep.encoders["h264"]] == ["h264_qsv"]
    assert rep.encoders["hevc"] == []
    assert [d.hwaccel for d in rep.decoders] == ["qsv"]
    assert "encode:h264_nvenc" in rep.failed and "decode:cuda" in rep.failed
    assert video.choose_encoder(rep).encoder == "h264_qsv"
    assert video.choose_encoder(rep, prefer="cpu").encoder == "libx264"
    assert video.choose_encoder(rep, "hevc").encoder == "libx265"
    assert video.choose_encoder(rep, prefer="h264_nvenc").encoder == "libx264"
    assert video.choose_decoder(rep).hwaccel == "qsv"  # type: ignore[union-attr]
    assert video.choose_decoder(rep, "cpu") is None


def test_probe_skips_unlisted():
    caps = fake_caps(encoders=frozenset({"libx264"}), hwaccels=frozenset())
    runner = runner_allowing("libx264")
    rep = video.probe_video_hw(caps, runner=runner, platform="win32")
    assert rep.decoders == [] and rep.encoders == {"h264": [], "hevc": []}
    assert rep.failed == [] and runner.calls == []  # type: ignore[attr-defined]
    assert video.choose_encoder(rep).encoder == "libx264"


def test_order_preserved_when_several_work():
    rep = video.probe_video_hw(
        fake_caps(), runner=lambda a: True, platform="win32", codecs=("h264",)
    )
    assert [e.encoder for e in rep.encoders["h264"]] == [
        "h264_nvenc", "h264_qsv", "h264_amf", "h264_mf",
    ]  # fmt: skip
    assert video.choose_encoder(rep).encoder == "h264_nvenc"


def test_quality_args():
    sw = video.software_encoder()
    assert sw.quality_args(20) == ["-crf", "20"] and sw.is_software


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_real_probe_falls_back_to_software_without_gpu():
    caps = probe_caps()
    assert video.test_encode(caps, video.software_encoder())
    rep = video.probe_video_hw(caps, platform=sys.platform)
    assert video.choose_encoder(rep).encoder in {"libx264"} | {
        e.encoder for e in rep.encoders["h264"]
    }
