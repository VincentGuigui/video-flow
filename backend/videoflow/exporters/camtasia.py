"""Camtasia project (.tscproj) writer, template-driven (spec 19).

The .tscproj JSON format is undocumented and versioned. The writer never invents
structure it can take from a template: media, track, transition and source-bin objects
are cloned from a template project saved by the user's Camtasia, then filled with paths,
positions and source ranges from the edit. Without a user template it uses
DEFAULT_TEMPLATE, modelled on Camtasia 2024 (Windows) as documented by community tools;
that default is unverified until opened in Camtasia.
"""

import copy
import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from videoflow.core.time import frames
from videoflow.editor.models import EditorClip
from videoflow.editor.resolve import document_for, editable_document
from videoflow.editor.transitions import active_transitions
from videoflow.project.models import Asset, Project

EDIT_RATE = 705_600_000
"""Camtasia ticks per second (divisible by every common frame rate)."""

TEMPLATE_NAME = "camtasia.tscproj"
TRANSITION_NAMES = {"dissolve": "Fade", "dip_black": "FadeThroughBlack", "dip_white": "Fade"}

DEFAULT_TEMPLATE: dict[str, Any] = {
    "title": "",
    "description": "",
    "author": "",
    "targetLoudness": -18.0,
    "shouldApplyLoudnessNormalization": False,
    "videoFormatFrameRate": 30,
    "audioFormatSampleRate": 48000,
    "allowSubFrameEditing": False,
    "width": 1920.0,
    "height": 1080.0,
    "version": "9.0",
    "editRate": EDIT_RATE,
    "authoringClientName": {"name": "Camtasia", "platform": "Windows", "version": "24.0"},
    "sourceBin": [
        {
            "id": 1,
            "src": "",
            "rect": [0, 0, 1920, 1080],
            "lastMod": "19700101T000000",
            "loudnessNormalization": False,
            "sourceTracks": [
                {
                    "range": [0, 0],
                    "type": 0,
                    "editRate": EDIT_RATE,
                    "trackRect": [0, 0, 1920, 1080],
                    "sampleRate": 30,
                    "bitDepth": 24,
                    "numChannels": 0,
                    "integratedLUFS": 100.0,
                    "peakLevel": -1.0,
                    "metaData": "",
                },
                {
                    "range": [0, 0],
                    "type": 2,
                    "editRate": EDIT_RATE,
                    "trackRect": [0, 0, 0, 0],
                    "sampleRate": 48000,
                    "bitDepth": 16,
                    "numChannels": 2,
                    "integratedLUFS": -23.0,
                    "peakLevel": -1.0,
                    "metaData": "",
                },
            ],
            "metadata": {"timeAdded": "19700101T000000"},
        }
    ],
    "timeline": {
        "id": 2,
        "sceneTrack": {
            "scenes": [
                {
                    "csml": {
                        "tracks": [
                            {
                                "trackIndex": 0,
                                "medias": [
                                    {
                                        "id": 3,
                                        "_type": "VMFile",
                                        "src": 1,
                                        "trackNumber": 0,
                                        "attributes": {"ident": ""},
                                        "parameters": {
                                            "translation0": 0.0,
                                            "translation1": 0.0,
                                            "scale0": 1.0,
                                            "scale1": 1.0,
                                        },
                                        "effects": [],
                                        "start": 0,
                                        "duration": 0,
                                        "mediaStart": 0,
                                        "mediaDuration": 0,
                                        "scalar": 1,
                                        "metadata": {"clipSpeedAttribute": False},
                                        "animationTracks": {},
                                    },
                                    {
                                        "id": 4,
                                        "_type": "AMFile",
                                        "src": 1,
                                        "trackNumber": 1,
                                        "attributes": {"ident": "", "gain": 1.0},
                                        "channelNumber": "0,1",
                                        "parameters": {"volume": 1.0},
                                        "effects": [],
                                        "start": 0,
                                        "duration": 0,
                                        "mediaStart": 0,
                                        "mediaDuration": 0,
                                        "scalar": 1,
                                        "metadata": {"clipSpeedAttribute": False},
                                        "animationTracks": {},
                                    },
                                ],
                                "transitions": [
                                    {
                                        "name": "Fade",
                                        "duration": 0,
                                        "leftMedia": 3,
                                        "rightMedia": 3,
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
        "gain": 1.0,
        "backgroundColor": [0, 0, 0, 255],
    },
}


@dataclass
class Prototypes:
    """Objects cloned from the template; each fills a part of the output."""

    video: dict[str, Any]
    audio: dict[str, Any]
    transitions: dict[str, dict[str, Any]]
    track: dict[str, Any]
    track_attributes: dict[str, Any]
    bin_entry: dict[str, Any]
    bin_tracks: dict[int, dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def _walk_medias(template: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for scene in template.get("timeline", {}).get("sceneTrack", {}).get("scenes", []):
        for track in scene.get("csml", {}).get("tracks", []):
            for media in track.get("medias", []):
                found.append(media)
                # UnifiedMedia pairs a VMFile with an AMFile.
                for key in ("video", "audio"):
                    if isinstance(media.get(key), dict):
                        found.append(media[key])
    return found


def _tracks(template: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        track
        for scene in template.get("timeline", {}).get("sceneTrack", {}).get("scenes", [])
        for track in scene.get("csml", {}).get("tracks", [])
    ]


def prototypes(template: dict[str, Any]) -> Prototypes:
    default = DEFAULT_TEMPLATE
    medias, fallback = _walk_medias(template), _walk_medias(default)

    def pick(kind: str, pool: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next((m for m in pool if m.get("_type") == kind), None)

    warnings: list[str] = []
    video = pick("VMFile", medias)
    audio = pick("AMFile", medias)
    if template is not default and (video is None or audio is None):
        warnings.append("Template lacks a video or audio clip; using built-in defaults for it.")
    transitions: dict[str, dict[str, Any]] = {}
    for source in (default, template):
        for track in _tracks(source):
            for transition in track.get("transitions", []):
                transitions[str(transition.get("name"))] = transition
    bins = template.get("sourceBin") or default["sourceBin"]
    bin_tracks = {
        int(t.get("type", -1)): t
        for entry in (*default["sourceBin"], *bins)
        for t in entry.get("sourceTracks", [])
    }
    track = (_tracks(template) or _tracks(default))[0]
    attributes = (template.get("timeline", {}).get("trackAttributes") or [None])[0]
    return Prototypes(
        video=video or pick("VMFile", fallback) or {},
        audio=audio or pick("AMFile", fallback) or {},
        transitions=transitions,
        track=track,
        track_attributes=attributes or default["timeline"]["trackAttributes"][0],
        bin_entry=bins[0],
        bin_tracks=bin_tracks,
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
    return DEFAULT_TEMPLATE, "built-in (unverified)"


@dataclass
class CamtasiaExport:
    text: str
    warnings: list[str]


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

    document = document_for(project) or editable_document(project)
    assets = {a.id: a for a in project.assets}

    def source_frames(clip: EditorClip) -> int:
        asset = assets.get(clip.asset_id or "")
        return frames(asset.probe.duration_us, rate) if asset else clip.source_out

    clips, _, active = active_transitions(document, source_frames)
    media_clips = [c for c in clips if c.kind != "gap" and c.asset_id in assets]
    if not media_clips:
        raise ValueError("The edit has no enabled media clips to export")

    output = copy.deepcopy(template)
    output["width"], output["height"] = float(settings.width), float(settings.height)
    output["videoFormatFrameRate"] = round(rate.num / rate.den)
    output["editRate"] = EDIT_RATE
    next_id = 1

    def new_id() -> int:
        nonlocal next_id
        next_id += 1
        return next_id - 1

    # Source bin: one entry per used asset.
    bin_ids: dict[str, int] = {}
    entries = []
    for asset_id in dict.fromkeys(c.asset_id or "" for c in media_clips):
        bin_ids[asset_id] = new_id()
        entries.append(_bin_entry(proto, assets[asset_id], bin_ids[asset_id], ticks))
    output["sourceBin"] = entries

    # One Camtasia track per editor lane: video lanes bottom-up, then audio lanes.
    lanes = sorted({("video", c.layer) for c in media_clips if c.kind == "video"}) + sorted(
        {("audio", c.layer) for c in media_clips if c.kind == "audio"}
    )
    tracks, media_ids = [], {}
    for index, (kind, layer) in enumerate(lanes):
        medias = []
        for clip in sorted(
            (c for c in media_clips if c.kind == kind and c.layer == layer), key=lambda c: c.start
        ):
            media = copy.deepcopy(proto.video if kind == "video" else proto.audio)
            media_ids[clip.id] = media["id"] = new_id()
            media.update(
                src=bin_ids[clip.asset_id or ""],
                trackNumber=0 if kind == "video" else 1,
                start=ticks(clip.start),
                duration=ticks(clip.duration),
                mediaStart=ticks(clip.source_in),
                mediaDuration=ticks(clip.duration),
                scalar=1,
            )
            media.setdefault("attributes", {})["ident"] = clip.name
            parameters = media.setdefault("parameters", {})
            if kind == "video":
                parameters.update(_placement(clip, assets[clip.asset_id or ""], settings))
            else:
                parameters["volume"] = round(10 ** (clip.gain_db / 20), 6)
            medias.append(media)
        track = copy.deepcopy(proto.track)
        track.update(trackIndex=index, medias=medias, transitions=[])
        tracks.append(track)
    if any(
        c.transform.crop_left
        or c.transform.crop_right
        or c.transform.crop_top
        or c.transform.crop_bottom
        for c in media_clips
        if c.kind == "video"
    ):
        warnings.append("Crop is not exported to Camtasia; clips are placed uncropped.")
    if any(c.background.mode != "transparent" for c in media_clips if c.kind == "video"):
        warnings.append("Clip backgrounds (colour, blur) are not exported to Camtasia.")

    for item in active:
        t = item.transition
        name = TRANSITION_NAMES[t.type]
        prototype = proto.transitions.get(name) or proto.transitions.get("Fade")
        if prototype is None:
            warnings.append(f"Transition {t.id}: no transition in the template; exported as a cut.")
            continue
        if t.type == "dip_white" or prototype.get("name") != name:
            warnings.append(f"Transition {t.id}: {t.type} exported as {prototype.get('name')}.")
        left = next(c for c in media_clips if c.id == t.left_id)
        track = tracks[lanes.index(("video", left.layer))]
        transition = copy.deepcopy(prototype)
        transition.update(
            duration=ticks(item.duration),
            leftMedia=media_ids[t.left_id],
            rightMedia=media_ids[t.right_id],
        )
        track["transitions"].append(transition)
    if active:
        warnings.append("Camtasia transitions do not carry the audio crossfades of the edit.")

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


def _bin_entry(proto: Prototypes, asset: Asset, identifier: int, ticks: Any) -> dict[str, Any]:
    entry = copy.deepcopy(proto.bin_entry)
    video = asset.probe.video
    width, height = (video.width, video.height) if video else (0, 0)
    if video and video.rotation in (90, 270):
        width, height = height, width
    length = round(Fraction(asset.probe.duration_us, 1_000_000) * EDIT_RATE)
    tracks = []
    if video:
        track = copy.deepcopy(proto.bin_tracks.get(0, {}))
        track.update(range=[0, length], trackRect=[0, 0, width, height], editRate=EDIT_RATE)
        tracks.append(track)
    if asset.probe.has_audio:
        track = copy.deepcopy(proto.bin_tracks.get(2, {}))
        track.update(range=[0, length], editRate=EDIT_RATE)
        tracks.append(track)
    entry.update(id=identifier, src=asset.path, rect=[0, 0, width, height], sourceTracks=tracks)
    return entry


def _placement(clip: EditorClip, asset: Asset, settings: Any) -> dict[str, float]:
    """Centre offset (Camtasia y points up) and scale relative to the source size."""
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
