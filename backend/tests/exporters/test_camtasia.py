import json

import pytest

from tests.timeline.builders import asset
from videoflow.core.time import Rational
from videoflow.editor.models import EditorClip, EditorDocument, EditorTransition, Transform
from videoflow.exporters import camtasia as cm
from videoflow.exporters.service import export_project
from videoflow.project.commands import SetEditor
from videoflow.project.models import ProjectSettings, new_project

TICKS = cm.EDIT_RATE // 25  # per frame at 25 fps


def project(transition="dissolve"):
    p = new_project("Camtasia")
    p.settings = ProjectSettings(width=1920, height=1080, frame_rate=Rational.of(25))
    p.assets = [asset("a", 10_000_000, Rational.of(25)), asset("b", 10_000_000, Rational.of(25))]
    full = Transform(width=1920, height=1080)

    def clip(id, kind, asset_id, start, source_in, length, layer=0, link=None, **values):
        return EditorClip(
            id=id,
            kind=kind,
            asset_id=asset_id,
            name=id,
            start=start,
            source_in=source_in,
            source_out=source_in + length,
            layer=layer,
            link_id=link,
            transform=values.pop("transform", full),
            **values,
        )

    doc = EditorDocument(
        clips=[
            clip("v1", "video", "a", 0, 10, 50, link="p"),
            clip("a1", "audio", "a", 0, 10, 50, link="p", gain_db=-6),
            clip("v2", "video", "b", 50, 25, 50),
            clip(
                "pip",
                "video",
                "b",
                20,
                0,
                25,
                layer=1,
                transform=Transform(x=1440, y=0, width=480, height=270),
            ),
        ],
        transitions=[
            EditorTransition(id="t", left_id="v1", right_id="v2", type=transition, duration=10)
        ],
    )
    p, _ = SetEditor(document=doc).apply(p)
    return p


def tracks(data):
    return data["timeline"]["sceneTrack"]["scenes"][0]["csml"]["tracks"]


def test_lanes_clips_and_exact_ticks():
    result = cm.export_camtasia(project())
    data = json.loads(result.text)
    assert (data["width"], data["height"], data["videoFormatFrameRate"]) == (1920.0, 1080.0, 25)
    assert [b["src"] for b in data["sourceBin"]] == ["/media/a.mp4", "/media/b.mp4"]
    names = [[m["attributes"]["ident"] for m in t["medias"]] for t in tracks(data)]
    assert names == [["v1", "v2"], ["pip"], ["a1"]]
    v1 = tracks(data)[0]["medias"][0]
    assert (v1["start"], v1["duration"], v1["mediaStart"]) == (0, 50 * TICKS, 10 * TICKS)
    assert v1["_type"] == "VMFile" and tracks(data)[2]["medias"][0]["_type"] == "AMFile"
    assert tracks(data)[2]["medias"][0]["parameters"]["volume"] == round(10 ** (-6 / 20), 6)
    pip = tracks(data)[1]["medias"][0]["parameters"]
    assert (pip["translation0"], pip["translation1"], pip["scale0"]) == (720.0, 405.0, 0.25)
    ids = [b["id"] for b in data["sourceBin"]] + [
        m["id"] for t in tracks(data) for m in t["medias"]
    ]
    assert len(ids) == len(set(ids + [data["timeline"]["id"]])) - 1
    assert {m["src"] for t in tracks(data) for m in t["medias"]} <= {
        b["id"] for b in data["sourceBin"]
    }
    assert [a["ident"] for a in data["timeline"]["trackAttributes"]] == [
        "Video 1",
        "Video 2",
        "Audio 1",
    ]
    assert "Camtasia template: built-in." in result.warnings


def test_dissolve_becomes_a_fade_between_adjacent_medias():
    data = json.loads(cm.export_camtasia(project()).text)
    (transition,) = tracks(data)[0]["transitions"]
    first, second = tracks(data)[0]["medias"]
    assert transition["name"] == "Fade" and transition["duration"] == 10 * TICKS
    assert (transition["leftMedia"], transition["rightMedia"]) == (first["id"], second["id"])


def test_user_template_structures_are_cloned():
    template = json.loads(json.dumps(cm.DEFAULT_TEMPLATE))
    media = tracks(template)[0]["medias"][0]
    media["customKey"] = "kept"
    tracks(template)[0]["transitions"].append(
        dict(tracks(template)[0]["transitions"][0], name="FadeThroughBlack", custom=1)
    )
    template["sourceBin"][0]["extra"] = True
    result = cm.export_camtasia(project("dip_black"), template, "user.tscproj")
    data = json.loads(result.text)
    assert all(m.get("customKey") == "kept" for m in tracks(data)[0]["medias"])
    assert tracks(data)[0]["transitions"][0]["name"] == "FadeThroughBlack"
    assert tracks(data)[0]["transitions"][0]["custom"] == 1
    assert all(b["extra"] for b in data["sourceBin"])
    assert not any("exported as" in w for w in result.warnings)


def test_unsupported_types_warn():
    result = cm.export_camtasia(project("dip_white"))
    assert any("dip_white exported as Fade" in w for w in result.warnings)


def test_service_writes_tscproj_and_report(tmp_path):
    paths = export_project(project(), tmp_path, ["camtasia"])
    assert {p.name for p in paths} >= {"edit.tscproj", "edit.report.json"}
    json.loads((tmp_path / "edit.tscproj").read_text(encoding="utf-8"))
    report = json.loads((tmp_path / "edit.report.json").read_text(encoding="utf-8"))
    assert any("Camtasia template" in w for w in report["warnings"])


def test_template_file_is_read_and_validated(tmp_path):
    good = tmp_path / "t.tscproj"
    good.write_text(json.dumps(cm.DEFAULT_TEMPLATE), encoding="utf-8-sig")
    assert cm.load_template(good)[1] == str(good)
    bad = tmp_path / "bad.tscproj"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not a Camtasia project"):
        cm.load_template(bad)
