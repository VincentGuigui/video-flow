import json

import pytest

from tests.timeline.builders import asset
from videoflow.core.time import Rational
from videoflow.editor.models import EditorClip, EditorDocument, EditorTransition, Transform
from videoflow.editor.resolve import document_for
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


def ident(media):
    inner = media.get("video", media)
    return inner["attributes"]["ident"]


def value(parameters, key):
    return parameters[key]["defaultValue"]


def test_lanes_linked_pairs_and_exact_ticks():
    result = cm.export_camtasia(project())
    data = json.loads(result.text)
    assert (data["width"], data["height"], data["videoFormatFrameRate"]) == (1920.0, 1080.0, 25)
    assert data["title"] == "Camtasia" and data["version"] == "7.0"
    assert [b["src"] for b in data["sourceBin"]] == ["/media/a.mp4", "/media/b.mp4"]
    assert [[ident(m) for m in t["medias"]] for t in tracks(data)] == [["v1", "v2"], ["pip"]]
    v1, v2 = tracks(data)[0]["medias"]
    assert v1["_type"] == "UnifiedMedia" and v2["_type"] == "VMFile"
    for media in (v1, v1["video"], v1["audio"]):
        assert (media["start"], media["duration"], media["mediaStart"]) == (
            0,
            50 * TICKS,
            10 * TICKS,
        )
    assert v1["audio"]["attributes"]["gain"] == round(10 ** (-6 / 20), 6)
    assert "parameters" not in v1["audio"]
    pip = tracks(data)[1]["medias"][0]["parameters"]
    assert (value(pip, "translation0"), value(pip, "translation1"), value(pip, "scale0")) == (
        720.0,
        405.0,
        0.25,
    )
    ids = [b["id"] for b in data["sourceBin"]]
    for t in tracks(data):
        for m in t["medias"]:
            ids += [m["id"]] + [m[k]["id"] for k in ("video", "audio") if k in m]
    assert len(ids) == len(set(ids)) and data["timeline"]["id"] not in ids
    bin_ids = {b["id"] for b in data["sourceBin"]}
    assert v1["video"]["src"] in bin_ids and v1["audio"]["src"] == v1["video"]["src"]
    video_track = data["sourceBin"][0]["sourceTracks"][0]
    assert video_track["range"] == [0, 10 * video_track["editRate"]]
    assert [a["ident"] for a in data["timeline"]["trackAttributes"]] == ["Video 1", "Video 2"]
    assert result.warnings[0] == "Camtasia template: built-in."


def test_dissolve_becomes_a_fade_between_adjacent_medias():
    data = json.loads(cm.export_camtasia(project()).text)
    (transition,) = tracks(data)[0]["transitions"]
    first, second = tracks(data)[0]["medias"]
    assert transition["name"] == "Fade" and transition["duration"] == 10 * TICKS
    assert (transition["leftMedia"], transition["rightMedia"]) == (first["id"], second["id"])


def test_user_template_structures_are_cloned_and_private_metadata_dropped():
    template = json.loads(json.dumps(cm.DEFAULT_TEMPLATE))
    unified = tracks(template)[0]["medias"][0]
    unified["customKey"] = "kept"
    unified["video"]["parameters"]["scale0"] = {
        "type": "double",
        "defaultValue": 1.0,
        "interp": "eioe",
        "keyframes": [{"time": 0, "value": 2.0}],
    }
    tracks(template)[0]["transitions"].append(
        dict(tracks(template)[0]["transitions"][0], name="FadeThroughBlack", custom=1)
    )
    template["sourceBin"][0]["extra"] = True
    template["metadata"] = {"AutoSaveFile": "C:/secret.tscproj", "CanvasZoom": 50}
    result = cm.export_camtasia(project("dip_black"), template, "user.tscproj")
    data = json.loads(result.text)
    v1 = tracks(data)[0]["medias"][0]
    assert v1["customKey"] == "kept"
    assert "keyframes" not in v1["video"]["parameters"]["scale0"]
    assert tracks(data)[0]["transitions"][0]["name"] == "FadeThroughBlack"
    assert tracks(data)[0]["transitions"][0]["custom"] == 1
    assert all(b["extra"] for b in data["sourceBin"])
    assert data["metadata"] == {"CanvasZoom": 50}
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


def test_edge_fades_become_one_sided_fades_without_duplicating_transitions():
    p = project()
    doc = document_for(p)
    clips = []
    for c in doc.clips:
        if c.id in ("v1", "a1"):
            c = c.model_copy(update={"fade_in": 15, "fade_out": 5})
        if c.id == "pip":
            c = c.model_copy(update={"fade_out": 10})
        clips.append(c)
    p, _ = SetEditor(document=doc.model_copy(update={"clips": clips})).apply(p)
    data = json.loads(cm.export_camtasia(p).text)
    main, pip = tracks(data)
    v1 = main["medias"][0]
    sides = [(t.get("leftMedia"), t.get("rightMedia"), t["duration"]) for t in main["transitions"]]
    assert (None, v1["id"], 15 * TICKS) in sides
    assert sum(1 for left, _, _ in sides if left == v1["id"]) == 1  # the dissolve keeps the edge
    (edge,) = pip["transitions"]
    assert edge["leftMedia"] == pip["medias"][0]["id"] and "rightMedia" not in edge


def test_speed_becomes_camtasia_scalar():
    p = project()
    doc = document_for(p)
    clips = [c.model_copy(update={"speed": 2.0}) if c.id in ("v2",) else c for c in doc.clips]
    doc = doc.model_copy(update={"clips": clips, "transitions": []})
    p, _ = SetEditor(document=doc).apply(p)
    v2 = tracks(json.loads(cm.export_camtasia(p).text))[0]["medias"][1]
    assert v2["scalar"] == "1/2" and v2["mediaDuration"] == 50 * TICKS
    assert v2["duration"] == 25 * TICKS and v2["metadata"]["clipSpeedAttribute"] is True
