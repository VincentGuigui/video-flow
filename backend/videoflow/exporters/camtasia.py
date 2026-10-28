"""Camtasia project (.tscproj) writer, template-driven (spec 19).

The .tscproj JSON format is undocumented and versioned. The writer takes every structure
it can from a template project saved by the user's Camtasia (UnifiedMedia, VMFile, AMFile,
transitions, track attributes, source-bin entries), then fills in paths, positions and
source ranges from the edit. DEFAULT_TEMPLATE reproduces the structures of a real Camtasia
2023.4.3 (Windows, format 7.0) project with neutral values.

Units: clip start, duration and mediaStart are project ticks (EDIT_RATE per second); a
source track's range uses that track's own editRate. Parameters are in pixels from the
canvas centre (translation, y up) and relative to the source size (scale).
"""

import copy
import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from videoflow.core.time import frames
from videoflow.editor.fonts import FAMILY
from videoflow.editor.models import EditorClip, Title
from videoflow.editor.resolve import document_for, editable_document
from videoflow.editor.titles import layout_title, title_lines
from videoflow.editor.transitions import active_transitions
from videoflow.editor.zoom import ramps
from videoflow.project.models import Asset, Project, ProjectSettings

EDIT_RATE = 705_600_000
"""Camtasia ticks per second (divisible by every common frame rate)."""

TEMPLATE_NAME = "camtasia.tscproj"
TRANSITION_NAMES = {"dissolve": "Fade", "dip_black": "FadeThroughBlack", "dip_white": "Fade"}
NEUTRAL_METADATA = ("CanvasZoom", "Fit", "Language", "ProfileName")
"""Project metadata kept from a template; the rest (autosave path, thumbnail...) is dropped."""
CROP_KEYS = ("crop_left", "crop_right", "crop_top", "crop_bottom")


def _param(value: float) -> dict[str, Any]:
    return {"type": "double", "defaultValue": value, "interp": "eioe"}


_MEDIA_METADATA = {"audiateLinkedSession": "", "clipSpeedAttribute": False}
_VIDEO: dict[str, Any] = {
    "id": 0,
    "_type": "VMFile",
    "src": 0,
    "trackNumber": 0,
    "attributes": {"ident": ""},
    "parameters": {f"geometryCrop{i}": _param(0.0) for i in range(4)},
    "effects": [],
    "start": 0,
    "duration": 0,
    "mediaStart": 0,
    "mediaDuration": 0,
    "scalar": 1,
    "metadata": dict(_MEDIA_METADATA),
    "animationTracks": {},
}
_AUDIO: dict[str, Any] = {
    "id": 0,
    "_type": "AMFile",
    "src": 0,
    "trackNumber": 1,
    "attributes": {
        "ident": "",
        "gain": 1.0,
        "mixToMono": False,
        "loudnessNormalization": True,
        "sourceFileOffset": 0,
    },
    "channelNumber": "0,1",
    "effects": [],
    "start": 0,
    "duration": 0,
    "mediaStart": 0,
    "mediaDuration": 0,
    "scalar": 1,
    "metadata": dict(_MEDIA_METADATA),
    "animationTracks": {},
}
_UNIFIED: dict[str, Any] = {
    "id": 0,
    "_type": "UnifiedMedia",
    "video": {k: v for k, v in _VIDEO.items() if k != "metadata"},
    "audio": {k: v for k, v in _AUDIO.items() if k != "metadata"},
    "start": 0,
    "duration": 0,
    "mediaStart": 0,
    "mediaDuration": 0,
    "scalar": 1,
    "metadata": dict(_MEDIA_METADATA),
}
_CALLOUT_METADATA = {
    **_MEDIA_METADATA,
    "default-HAlign": "center",
    "default-LineSpace": 0.0,
    "default-VAlign": "center",
    **{f"default-{k}{i}": v for k, v in (("anchor", 0.0), ("rotation", 0.0)) for i in range(3)},
    **{f"default-scale{i}": 1.0 for i in range(3)},
    **{f"default-shear{i}": 0.0 for i in range(3)},
    **{f"default-translation{i}": 0.0 for i in range(3)},
    "default-height": 250.0,
    "default-width": 400.0,
    "default-text-attributes": None,
}


def _double(value: float) -> dict[str, Any]:
    return {"type": "double", "defaultValue": value, "interp": "linr"}


_TEXT_DEF: dict[str, Any] = {
    "kind": "remix",
    "shape": "text",
    "style": "basic",
    "enable-ligatures": 1.0,
    "height": 250.0,
    "line-spacing": 0.0,
    "width": 400.0,
    "word-wrap": 1.0,
    "horizontal-alignment": "center",
    "resize-behavior": "resizeText",
    "text": "",
    "vertical-alignment": "center",
    "font": {
        "color-blue": 1.0,
        "color-green": 1.0,
        "color-red": 1.0,
        "size": 64.0,
        "tracking": 0.0,
        "name": "Montserrat",
        "weight": "Regular",
    },
    "textAttributes": {"type": "textAttributeList", "keyframes": []},
}
_CALLOUT: dict[str, Any] = {
    "id": 0,
    "_type": "Callout",
    "def": _TEXT_DEF,
    "attributes": {"ident": "", "autoRotateText": True},
    "parameters": {
        "translation0": _param(0.0),
        "translation1": _param(0.0),
        **{f"geometryCrop{i}": _param(0.0) for i in range(4)},
    },
    "effects": [],
    "start": 0,
    "duration": 0,
    "mediaStart": 0,
    "mediaDuration": 0,
    "scalar": 1,
    "metadata": _CALLOUT_METADATA,
    "animationTracks": {},
}
_BOX_CALLOUT: dict[str, Any] = {
    **_CALLOUT,
    "def": {
        **_TEXT_DEF,
        "shape": "text-rectangle",
        **{f"fill-color-{c}": _double(0.0) for c in ("red", "green", "blue")},
        "fill-color-opacity": _double(1.0),
        **{f"stroke-color-{c}": _double(0.0) for c in ("red", "green", "blue")},
        "stroke-color-opacity": _double(1.0),
        "stroke-width": _double(0.0),
        "tail-x": 0.0,
        "tail-y": -20.0,
        "fill-style": "solid",
        "stroke-style": "solid",
    },
}
TEXT_SHAPES = ("text", "text-rectangle")
_SOURCE_TRACK = {
    "range": [0, 0],
    "trackRect": [0, 0, 0, 0],
    "bitDepth": 24,
    "numChannels": 0,
    "integratedLUFS": 100.0,
    "peakLevel": -1.0,
    "metaData": "",
}

DEFAULT_TEMPLATE: dict[str, Any] = {
    "title": "",
    "description": "",
    "author": "",
    "targetLoudness": -18.0,
    "shouldApplyLoudnessNormalization": True,
    "videoFormatFrameRate": 30,
    "audioFormatSampleRate": 44100,
    "allowSubFrameEditing": False,
    "width": 1920.0,
    "height": 1080.0,
    "version": "7.0",
    "editRate": EDIT_RATE,
    "authoringClientName": {"name": "Camtasia", "platform": "Windows", "version": "2023.4.3"},
    "sourceBin": [
        {
            "id": 0,
            "src": "",
            "rect": [0, 0, 1920, 1080],
            "lastMod": "19700101T000000",
            "loudnessNormalization": True,
            "sourceTracks": [
                {**_SOURCE_TRACK, "type": 0, "editRate": 90000, "sampleRate": "30/1"},
                {
                    **_SOURCE_TRACK,
                    "type": 2,
                    "editRate": 10000,
                    "sampleRate": 48000,
                    "bitDepth": 16,
                    "numChannels": 2,
                },
            ],
            "metadata": {"timeAdded": "19700101T000000"},
        }
    ],
    "timeline": {
        "id": 0,
        "sceneTrack": {
            "scenes": [
                {
                    "csml": {
                        "tracks": [
                            {
                                "trackIndex": 0,
                                "medias": [_UNIFIED, _VIDEO, _AUDIO, _CALLOUT, _BOX_CALLOUT],
                                "transitions": [
                                    {
                                        "name": "Fade",
                                        "duration": 0,
                                        "leftMedia": 0,
                                        "rightMedia": 0,
                                        "attributes": {
                                            "bypass": False,
                                            "reverse": False,
                                            "trivial": False,
                                            "useAudioPreRoll": True,
                                            "useVisualPreRoll": True,
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                }
            ]
        },
        "trackAttributes": [
            {
                "ident": "",
                "audioMuted": False,
                "videoHidden": False,
                "magnetic": False,
                "matte": 0,
                "solo": False,
                "metadata": {"IsLocked": "False", "WinTrackHeight": "56"},
            }
        ],
        "captionAttributes": {
            "enabled": True,
            "fontName": "Arial",
            "fontSize": 64,
            "backgroundColor": [0, 0, 0, 191],
            "foregroundColor": [255, 255, 255, 255],
            "lang": "en",
            "alignment": 0,
            "defaultFontSize": True,
            "opacity": 0.5,
            "backgroundEnabled": True,
            "backgroundOnlyAroundText": True,
        },
        "gain": 1.0,
        "legacyAttenuateAudioMix": False,
        "backgroundColor": [0, 0, 0, 255],
    },
    "metadata": {"CanvasZoom": 25, "Fit": 0, "Language": "ENU", "ProfileName": ""},
}


@dataclass
class Prototypes:
    """Objects cloned from the template; each fills a part of the output."""

    unified: dict[str, Any]
    video: dict[str, Any]
    audio: dict[str, Any]
    transitions: dict[str, dict[str, Any]]
    track: dict[str, Any]
    track_attributes: dict[str, Any]
    bin_entry: dict[str, Any]
    bin_tracks: dict[int, dict[str, Any]]
    callouts: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Text callouts by shape: plain text, and text on a filled rectangle."""
    warnings: list[str] = field(default_factory=list)


def _tracks(template: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        track
        for scene in template.get("timeline", {}).get("sceneTrack", {}).get("scenes", [])
        for track in scene.get("csml", {}).get("tracks", [])
    ]


def _medias(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Top-level medias first, so standalone prototypes are not taken from inside a pair."""
    top = [media for track in _tracks(template) for media in track.get("medias", [])]
    # UnifiedMedia pairs a VMFile with an AMFile.
    inner = [m[k] for m in top for k in ("video", "audio") if isinstance(m.get(k), dict)]
    return top + inner


def prototypes(template: dict[str, Any]) -> Prototypes:
    medias, fallback = _medias(template), _medias(DEFAULT_TEMPLATE)
    warnings: list[str] = []

    def pick(kind: str) -> dict[str, Any]:
        own = next((m for m in medias if m.get("_type") == kind), None)
        if own is None and template is not DEFAULT_TEMPLATE:
            warnings.append(f"Template has no {kind}; using the built-in structure.")
        return own or next(m for m in fallback if m.get("_type") == kind)

    unified, video, audio = pick("UnifiedMedia"), pick("VMFile"), pick("AMFile")
    transitions: dict[str, dict[str, Any]] = {}
    for source in (DEFAULT_TEMPLATE, template):
        for track in _tracks(source):
            for transition in track.get("transitions", []):
                transitions[str(transition.get("name"))] = transition
    bins = template.get("sourceBin") or DEFAULT_TEMPLATE["sourceBin"]
    bin_tracks = {
        int(t.get("type", -1)): t
        for entry in (*DEFAULT_TEMPLATE["sourceBin"], *bins)
        for t in entry.get("sourceTracks", [])
    }
    bin_entry = next(
        (b for b in bins if any(t.get("type") == 0 for t in b.get("sourceTracks", []))), bins[0]
    )
    attributes = (template.get("timeline", {}).get("trackAttributes") or [None])[0]
    callouts = {
        shape: next(
            m
            for source in (medias, fallback)
            for m in source
            if m.get("_type") == "Callout"
            and isinstance(m.get("def"), dict)
            and m["def"].get("kind") == "remix"
            and m["def"].get("shape") == shape
        )
        for shape in TEXT_SHAPES
    }
    return Prototypes(
        unified=unified,
        video=video,
        audio=audio,
        transitions=transitions,
        track=(_tracks(template) or _tracks(DEFAULT_TEMPLATE))[0],
        track_attributes=attributes or DEFAULT_TEMPLATE["timeline"]["trackAttributes"][0],
        bin_entry=bin_entry,
        bin_tracks=bin_tracks,
        callouts=callouts,
        warnings=warnings,
    )


def user_template_path() -> Path:
    from videoflow.runtime import application_dir

    return application_dir() / "templates" / TEMPLATE_NAME


def load_template(path: Path | None = None) -> tuple[dict[str, Any], str]:
    """The template to clone and where it came from."""
    candidate = path or user_template_path()
    if candidate.is_file():
        data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or "timeline" not in data:
            raise ValueError(f"{candidate} is not a Camtasia project")
        return data, str(candidate)
    if path is not None:
        raise FileNotFoundError(f"Camtasia template not found: {path}")
    return DEFAULT_TEMPLATE, "built-in (Camtasia 2023.4 structure)"


@dataclass
class CamtasiaExport:
    text: str
    warnings: list[str]


def _set(parameters: dict[str, Any], key: str, value: float) -> None:
    """Static parameter value, keeping the object form when the template uses it."""
    current = parameters.get(key)
    if isinstance(current, dict):
        current.pop("keyframes", None)
        current["defaultValue"] = value
    else:
        parameters[key] = _param(value)


def export_camtasia(
    project: Project, template: dict[str, Any] | None = None, source: str = "built-in"
) -> CamtasiaExport:
    template = template if template is not None else DEFAULT_TEMPLATE
    proto = prototypes(template)
    warnings = [f"Camtasia template: {source}.", *proto.warnings]
    settings = project.settings
    rate = settings.frame_rate
    ticks_per_frame = Fraction(EDIT_RATE * rate.den, rate.num)

    def ticks(frame_count: int) -> int:
        return round(frame_count * ticks_per_frame)

    def timing(media: dict[str, Any], clip: EditorClip) -> None:
        duration, media_duration = ticks(clip.duration), ticks(clip.span)
        # Speed (spec 21): Camtasia's scalar is timeline length over media length.
        scalar = Fraction(duration, media_duration)
        media.update(
            start=ticks(clip.start),
            duration=duration,
            mediaStart=ticks(clip.source_in),
            mediaDuration=media_duration,
            scalar=1 if scalar == 1 else f"{scalar.numerator}/{scalar.denominator}",
        )
        if scalar != 1 and isinstance(media.get("metadata"), dict):
            media["metadata"]["clipSpeedAttribute"] = True

    document = document_for(project) or editable_document(project)
    assets = {a.id: a for a in project.assets}

    def source_frames(clip: EditorClip) -> int:
        asset = assets.get(clip.asset_id or "")
        return frames(asset.probe.duration_us, rate) if asset else clip.source_out

    clips, _, active = active_transitions(document, source_frames)
    media_clips = [c for c in clips if c.kind in ("video", "audio") and c.asset_id in assets]
    text_clips = [c for c in clips if c.kind == "text" and c.title]
    if not media_clips and not text_clips:
        raise ValueError("The edit has no enabled media or text clips to export")
    by_id = {c.id: c for c in media_clips}
    partner = {
        c.id: o.id
        for c in media_clips
        for o in media_clips
        if c.link_id and o.link_id == c.link_id and o.id != c.id
    }

    output = copy.deepcopy(template)
    output.update(
        title=project.name,
        width=float(settings.width),
        height=float(settings.height),
        videoFormatFrameRate=round(rate.num / rate.den),
        editRate=EDIT_RATE,
    )
    metadata = output.get("metadata") or {}
    output["metadata"] = {k: metadata[k] for k in NEUTRAL_METADATA if k in metadata}
    next_id = 1

    def new_id() -> int:
        nonlocal next_id
        next_id += 1
        return next_id - 1

    bin_ids: dict[str, int] = {}
    entries = []
    for asset_id in dict.fromkeys(c.asset_id or "" for c in media_clips):
        bin_ids[asset_id] = new_id()
        entries.append(_bin_entry(proto, assets[asset_id], bin_ids[asset_id]))
    output["sourceBin"] = entries

    def video_media(clip: EditorClip, model: dict[str, Any]) -> dict[str, Any]:
        media = copy.deepcopy(model)
        media.update(id=new_id(), src=bin_ids[clip.asset_id or ""], trackNumber=0)
        timing(media, clip)
        media.setdefault("attributes", {})["ident"] = clip.name
        parameters = media.setdefault("parameters", {})
        placement = _placement(clip, assets[clip.asset_id or ""], settings)
        for key, value in placement.items():
            _set(parameters, key, value)
        for key, keyframes in _zoom_keyframes(clip, placement, ticks).items():
            parameters[key]["keyframes"] = keyframes
        return media

    def audio_media(clip: EditorClip, model: dict[str, Any]) -> dict[str, Any]:
        media = copy.deepcopy(model)
        media.update(id=new_id(), src=bin_ids[clip.asset_id or ""], trackNumber=1)
        timing(media, clip)
        media.setdefault("attributes", {})["gain"] = round(10 ** (clip.gain_db / 20), 6)
        media.pop("parameters", None)  # the template's volume keyframes do not apply
        if keyframes := _volume_keyframes(clip, ticks):
            media["parameters"] = {"volume": {"type": "double", "keyframes": keyframes}}
        return media

    def text_media(clip: EditorClip, title: Title) -> dict[str, Any]:
        media = copy.deepcopy(proto.callouts["text-rectangle" if title.box else "text"])
        media.update(
            id=new_id(),
            start=ticks(clip.start),
            duration=ticks(clip.duration),
            mediaStart=0,
            mediaDuration=ticks(clip.duration),
            scalar=1,
        )
        media.setdefault("attributes", {})["ident"] = clip.name
        media["effects"] = []
        media["def"] = _callout_def(media.get("def") or {}, title, settings)
        parameters = media.setdefault("parameters", {})
        layout = layout_title(title, settings.width, settings.height)
        left, top, right, bottom = layout.bounds
        _set(parameters, "translation0", round((left + right - settings.width) / 2, 4))
        _set(parameters, "translation1", round((settings.height - top - bottom) / 2, 4))
        return media

    # One Camtasia track per editor lane: video lanes bottom-up (linked audio travels
    # inside UnifiedMedia, text clips become callouts), then lanes of independent audio.
    lanes = sorted(
        {("video", c.layer) for c in [*media_clips, *text_clips] if c.kind != "audio"}
    ) + sorted(
        {("audio", c.layer) for c in media_clips if c.kind == "audio" and c.id not in partner}
    )
    tracks, media_ids = [], {}
    for index, (kind, layer) in enumerate(lanes):
        medias = []
        lane = sorted(
            (
                c
                for c in [*media_clips, *text_clips]
                if (c.kind == kind or kind == "video" and c.kind == "text")
                and c.layer == layer
                and not (kind == "audio" and c.id in partner)
            ),
            key=lambda c: c.start,
        )
        for clip in lane:
            if clip.title is not None:
                media = text_media(clip, clip.title)
            elif kind == "video" and clip.id in partner:
                media = copy.deepcopy(proto.unified)
                media["video"] = video_media(clip, proto.unified.get("video") or proto.video)
                media["audio"] = audio_media(
                    by_id[partner[clip.id]], proto.unified.get("audio") or proto.audio
                )
                media["id"] = new_id()
                timing(media, clip)
            elif kind == "video":
                media = video_media(clip, proto.video)
            else:
                media = audio_media(clip, proto.audio)
            media_ids[clip.id] = media["id"]
            medias.append(media)
        track = copy.deepcopy(proto.track)
        track.update(trackIndex=index, medias=medias, transitions=[])
        tracks.append(track)
    videos = [c for c in media_clips if c.kind == "video"]
    if any(getattr(c.transform, k) for c in videos for k in CROP_KEYS):
        warnings.append("Crop is not exported to Camtasia; clips are placed uncropped.")
    if any(c.background.mode != "transparent" for c in videos):
        warnings.append("Clip backgrounds (colour, blur) are not exported to Camtasia.")

    for item in active:
        t = item.transition
        name = TRANSITION_NAMES[t.type]
        prototype = proto.transitions.get(name) or proto.transitions["Fade"]
        if prototype.get("name") != name or t.type == "dip_white":
            warnings.append(f"Transition {t.id}: {t.type} exported as {prototype.get('name')}.")
        transition = copy.deepcopy(prototype)
        transition.update(
            duration=ticks(item.duration),
            leftMedia=media_ids[t.left_id],
            rightMedia=media_ids[t.right_id],
        )
        tracks[lanes.index(("video", by_id[t.left_id].layer))]["transitions"].append(transition)
    if active:
        warnings.append("Camtasia transitions do not carry the audio crossfades of the edit.")
    # Edge fades (spec 21) become one-sided Fades unless a transition already uses that edge.
    fade = proto.transitions["Fade"]
    for index, (kind, layer) in enumerate(lanes):
        track = tracks[index]
        used_left = {t.get("leftMedia") for t in track["transitions"]}
        used_right = {t.get("rightMedia") for t in track["transitions"]}
        for clip in [*media_clips, *text_clips]:
            lane_kind = "video" if clip.kind == "text" else clip.kind
            if lane_kind != kind or clip.layer != layer or clip.id not in media_ids:
                continue
            identifier = media_ids[clip.id]
            for frames_, side, used in (
                (clip.fade_in, "rightMedia", used_right),
                (clip.fade_out, "leftMedia", used_left),
            ):
                if frames_ and identifier not in used:
                    edge = {
                        k: v
                        for k, v in copy.deepcopy(fade).items()
                        if k not in ("leftMedia", "rightMedia")
                    }
                    edge.update(duration=ticks(min(frames_, clip.duration)), **{side: identifier})
                    track["transitions"].append(edge)

    timeline = output.setdefault("timeline", {})
    timeline["id"] = new_id()
    scenes = timeline.setdefault("sceneTrack", {}).setdefault("scenes", [{}])
    scenes[:] = [scenes[0] if scenes else {}]
    scenes[0].setdefault("csml", {})["tracks"] = tracks
    attributes = []
    for kind, layer in lanes:
        entry = copy.deepcopy(proto.track_attributes)
        entry["ident"] = f"{'Video' if kind == 'video' else 'Audio'} {layer + 1}"
        attributes.append(entry)
    timeline["trackAttributes"] = attributes
    return CamtasiaExport(json.dumps(output, ensure_ascii=False, indent=2) + "\n", warnings)


def _bin_entry(proto: Prototypes, asset: Asset, identifier: int) -> dict[str, Any]:
    entry = copy.deepcopy(proto.bin_entry)
    video = asset.probe.video
    width, height = (video.width, video.height) if video else (0, 0)
    if video and video.rotation in (90, 270):
        width, height = height, width
    seconds = Fraction(asset.probe.duration_us, 1_000_000)
    name = Path(asset.path.replace("\\", "/")).name + ";"
    tracks = []
    if video:
        track = copy.deepcopy(proto.bin_tracks.get(0) or {"editRate": 90000})
        track.update(
            type=0,
            range=[0, round(seconds * int(track.get("editRate", 90000)))],
            trackRect=[0, 0, width, height],
            sampleRate=f"{video.frame_rate.num}/{video.frame_rate.den}",
            metaData=name,
        )
        tracks.append(track)
    if asset.probe.has_audio:
        track = copy.deepcopy(proto.bin_tracks.get(2) or {"editRate": 10000})
        stream = asset.probe.audio_streams[0] if asset.probe.audio_streams else None
        track.update(
            type=2,
            range=[0, round(seconds * int(track.get("editRate", 10000)))],
            sampleRate=stream.sample_rate if stream else 48000,
            numChannels=stream.channels if stream else 2,
            metaData=name,
        )
        tracks.append(track)
    entry.update(id=identifier, src=asset.path, rect=[0, 0, width, height], sourceTracks=tracks)
    return entry


def _callout_def(base: dict[str, Any], title: Title, settings: ProjectSettings) -> dict[str, Any]:
    """A text callout's definition (spec 21): lines, fonts, alignment and box."""
    layout = layout_title(title, settings.width, settings.height)
    left, top, right, bottom = layout.bounds
    lines = title_lines(title)
    red, green, blue = _rgb(title.color)
    attributes, start = [], 0
    for index, (text, line) in enumerate(zip(lines, layout.lines, strict=True)):
        # Ranges count UTF-16 units; the line break belongs to the line before it.
        end = start + len(text.encode("utf-16-le")) // 2 + (index < len(lines) - 1)
        values: list[tuple[str, Any, str]] = [
            ("fontName", FAMILY, "string"),
            ("fontSize", round(line.size, 2), "double"),
            ("fontWeight", 700 if line.bold else 400, "int"),
            (
                "fgColor",
                f"({round(red * 255)},{round(green * 255)},{round(blue * 255)},255)",
                "color",
            ),
            ("fontItalic", 0, "int"),
            ("underline", 0, "int"),
            ("strikethrough", 0, "int"),
            ("kerning", 0.0, "double"),
        ]
        attributes += [
            {"name": n, "rangeEnd": end, "rangeStart": start, "value": v, "valueType": t}
            for n, v, t in values
        ]
        start = end
    definition = copy.deepcopy(base)
    definition.update(
        {
            "text": "\r".join(lines),
            "width": round(right - left, 4),
            "height": round(bottom - top, 4),
            "word-wrap": 0.0,
            "horizontal-alignment": "center" if layout.centred else "left",
            "vertical-alignment": "center",
            "textAttributes": {
                "type": "textAttributeList",
                "keyframes": [{"endTime": 0, "time": 0, "value": attributes, "duration": 0}],
            },
        }
    )
    font = definition.setdefault("font", {})
    font.update(
        {"color-red": red, "color-green": green, "color-blue": blue},
        size=round(layout.lines[0].size, 2),
        name=FAMILY,
        weight="Bold",
    )
    if title.box:
        for channel, value in zip(("red", "green", "blue"), _rgb(title.box_color), strict=True):
            _fill(definition, f"fill-color-{channel}", value)
        _fill(definition, "fill-color-opacity", title.box_opacity)
        _fill(definition, "stroke-width", 0.0)
    return definition


def _fill(definition: dict[str, Any], key: str, value: float) -> None:
    current = definition.get(key)
    if isinstance(current, dict):
        current.pop("keyframes", None)
        current["defaultValue"] = round(value, 6)
    else:
        definition[key] = {"type": "double", "defaultValue": round(value, 6), "interp": "linr"}


def _rgb(color: str) -> tuple[float, float, float]:
    return (
        int(color[1:3], 16) / 255,
        int(color[3:5], 16) / 255,
        int(color[5:7], 16) / 255,
    )


def _volume_keyframes(clip: EditorClip, ticks: Any) -> list[dict[str, Any]]:
    """Mute and ducking ranges (spec 21) as volume keyframes in media time."""
    keyframes = []
    for r in sorted(clip.volume_ranges, key=lambda r: r.start):
        if r.end + r.ramp <= clip.source_in or r.start - r.ramp >= clip.source_out:
            continue
        for time, value in ((r.start - r.ramp, r.factor), (r.end, 1.0)):
            start, span = ticks(max(0, time)), ticks(r.ramp)
            keyframes.append(
                {"endTime": start + span, "time": start, "value": round(value, 6), "duration": span}
            )
    return keyframes


def _zoom_keyframes(
    clip: EditorClip, base: dict[str, float], ticks: Any
) -> dict[str, list[dict[str, Any]]]:
    """Zooms (spec 21) as Camtasia keyframes, in media time.

    Camtasia scales a clip about its centre; translation moves so the focus point stays in
    place. A keyframe ramps from the previous value at `time` to `value` at `endTime`.
    """
    result: dict[str, list[dict[str, Any]]] = {k: [] for k in base}
    t = clip.transform
    for zoom in sorted(clip.zooms, key=lambda z: z.start):
        if zoom.end <= clip.source_in or zoom.start >= clip.source_out:
            continue
        ease_in, ease_out = ramps(zoom)
        k = zoom.scale
        dx = (t.width / 2 - zoom.x * t.width) * (k - 1)
        dy = (t.height / 2 - zoom.y * t.height) * (k - 1)
        zoomed = {
            "scale0": base["scale0"] * k,
            "scale1": base["scale1"] * k,
            "translation0": base["translation0"] + dx,
            "translation1": base["translation1"] - dy,  # Camtasia y points up
        }
        for time, length, values in (
            (zoom.start, ease_in, zoomed),
            (zoom.end - ease_out, ease_out, base),
        ):
            for key, value in values.items():
                start, span = ticks(time), ticks(length)
                result[key].append(
                    {
                        "endTime": start + span,
                        "time": start,
                        "value": round(value, 6),
                        "duration": span,
                    }
                )
    return {k: v for k, v in result.items() if v}


def _placement(clip: EditorClip, asset: Asset, settings: ProjectSettings) -> dict[str, float]:
    """Centre offset (y up) and scale relative to the source size."""
    video = asset.probe.video
    width, height = (video.width, video.height) if video else (settings.width, settings.height)
    if video and video.rotation in (90, 270):
        width, height = height, width
    t = clip.transform
    return {
        "translation0": round(t.x + t.width / 2 - settings.width / 2, 4),
        "translation1": round(settings.height / 2 - (t.y + t.height / 2), 4),
        "scale0": round(t.width / width, 6),
        "scale1": round(t.height / height, 6),
    }
