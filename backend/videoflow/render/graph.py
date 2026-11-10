"""Compile the interactive edit to independent video/audio filter graphs."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from videoflow.core.time import Rational, frames, frames_to_samples
from videoflow.editor.keyframes import animated, keys_of, piecewise, transform_at
from videoflow.editor.models import EditorClip, EditorDocument, Title
from videoflow.editor.resolve import document_for, editable_document, validate_assets
from videoflow.editor.titles import title_png
from videoflow.editor.transitions import plan_transitions
from videoflow.editor.volume import volume_expression
from videoflow.project.models import Project

type Preset = Literal["draft", "final"]


@dataclass(frozen=True)
class RenderGraph:
    inputs: list[Path]
    video: str
    audio: str
    audio_inputs: list[Path]
    width: int
    height: int
    frames: int
    samples: int
    rate: Rational
    warnings: list[str]
    titles: dict[Path, Title] = field(default_factory=dict)
    """Title pictures (video inputs) to draw before running FFmpeg; see write_titles."""


def write_titles(graph: RenderGraph) -> None:
    """Draw the transparent title pictures the graph reads, once per title and size."""
    for path, title in graph.titles.items():
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(title_png(title, graph.width, graph.height))


def _window(start: int, end: int, rate: Rational) -> str:
    """Overlay enable expression for frames [start, end), by timestamp.

    Frame counters (n) are unreliable once overlays are chained; half-frame margins
    keep the comparison exact under timestamp rounding.
    """
    return (
        f"gte(t,{2 * start - 1}*{rate.den}/{2 * rate.num})"
        f"*lt(t,{2 * end - 1}*{rate.den}/{2 * rate.num})"
    )


BORDER = 2
"""Transparent pixels around the picture, so `perspective` leaves the outside transparent."""


def _animated(
    clip: EditorClip, index: int, out: tuple[int, int], scale: tuple[float, float], rate: Rational
) -> str:
    """Per-frame transform of [fg{index}] into a full-frame picture [p{index}]
    (docs/features/finishing/keyframes.md): crop, size, position, rotation and opacity.

    `perspective` maps the (cropped) picture, inside a transparent border, onto the corners
    of its box rotated about the box centre; its expressions read the source frame from the
    filter's frame counter.
    """
    keys = keys_of(clip)
    out_w, out_h = out
    sx, sy = scale
    position = f"({clip.source_in}+in*{_number(clip.speed)})"

    def value(name: str) -> str:
        return piecewise(keys, lambda t: float(getattr(t, name)), position)

    steps: list[str] = []
    crops = [value(n) for n in ("crop_left", "crop_right", "crop_top", "crop_bottom")]
    left, right, top, bottom = crops
    if not all(_constant(c) for c in crops):
        # The crop region stretched to the whole frame, per frame.
        steps.append(
            "perspective=sense=source:eval=frame:"
            f"x0='W*{left}':y0='H*{top}':x1='W*(1-{right})':y1='H*{top}':"
            f"x2='W*{left}':y2='H*(1-{bottom})':x3='W*(1-{right})':y3='H*(1-{bottom})'"
        )
    elif any(float(c) for c in crops):
        steps.append(
            f"crop=w='iw*(1-{left}-{right})':h='ih*(1-{top}-{bottom})':x='iw*{left}':y='ih*{top}'"
        )
    # Zoomed-in boxes are drawn on a canvas twice the output size, then scaled down.
    largest = max(
        max(k.transform.width / out_w * sx, k.transform.height / out_h * sy) for k in keys
    )
    k = 2 if largest > 1.25 else 1
    cw, ch = out_w * k, out_h * k
    inner_w, inner_h = cw - 2 * BORDER, ch - 2 * BORDER
    steps.append(
        f"scale={inner_w}:{inner_h},setsar=1,pad={cw}:{ch}:{BORDER}:{BORDER}:color=black@0"
    )
    x, y, w, h = value("x"), value("y"), value("width"), value("height")
    ax, ay = sx * k, sy * k
    cx, cy = f"(({x})+({w})/2)*{_number(ax)}", f"(({y})+({h})/2)*{_number(ay)}"
    # Visible edges relative to the box centre, widened by the border's share.
    vw = f"((1-{left}-{right})*({w})*{_number(ax)})"
    vh = f"((1-{top}-{bottom})*({h})*{_number(ay)})"
    edge_x = f"{vw}*{BORDER}/{inner_w}"
    edge_y = f"{vh}*{BORDER}/{inner_h}"
    lx = f"((-0.5+{left})*({w})*{_number(ax)}-{edge_x})"
    rx = f"((0.5-{right})*({w})*{_number(ax)}+{edge_x})"
    ty = f"((-0.5+{top})*({h})*{_number(ay)}-{edge_y})"
    by = f"((0.5-{bottom})*({h})*{_number(ay)}+{edge_y})"
    rotation = value("rotation")
    corners = []
    for dx, dy in ((lx, ty), (rx, ty), (lx, by), (rx, by)):
        if _constant(rotation) and float(rotation) == 0:
            corners += [f"{cx}+{dx}", f"{cy}+{dy}"]
        else:
            angle = f"({rotation})*PI/180"
            corners += [
                f"{cx}+{dx}*cos({angle})-{dy}*sin({angle})",
                f"{cy}+{dx}*sin({angle})+{dy}*cos({angle})",
            ]
    names = ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3")
    steps.append(
        "perspective=sense=destination:eval=frame:"
        + ":".join(f"{n}='{c}'" for n, c in zip(names, corners, strict=True))
    )
    if k != 1:
        steps.append(f"scale={out_w}:{out_h}")
    opacity = value("opacity")
    if not _constant(opacity):
        # colorchannelmixer has no time expressions: one command per frame that changes.
        commands, last = [], None
        for n in range(clip.duration):
            v = round(transform_at(clip, clip.source_in + n * clip.speed).opacity, 3)
            if v != last:
                commands.append(f"{n * rate.den / rate.num:.4f} colorchannelmixer@o{index} aa {v}")
                last = v
        steps.append(f"sendcmd=c='{';'.join(commands)}',colorchannelmixer@o{index}=aa=1")
    elif float(opacity) != 1:
        steps.append(f"colorchannelmixer=aa={opacity}")
    return ",".join(steps)


def _constant(expression: str) -> bool:
    try:
        float(expression)
    except ValueError:
        return False
    return True


def _volume(clip: EditorClip, rate: Rational) -> str:
    """Mute and ducking ranges as a per-frame gain envelope
    (docs/features/finishing/clip-effects.md)."""
    expression = volume_expression(clip, rate.num / rate.den)
    return f"volume='{expression}':eval=frame," if expression else ""


def _retime(speed: float, fps: str) -> str:
    """Restart timestamps; at another speed, stretch them and resample to the project rate."""
    if speed == 1:
        return "setpts=PTS-STARTPTS,"
    return f"setpts=(PTS-STARTPTS)/{_number(speed)},fps={fps}:round=near,"


def _atempo(speed: float) -> str:
    """Pitch-preserving tempo change; atempo factors are chained within [0.5, 2]."""
    if speed == 1:
        return ""
    factors, rest = [], speed
    while rest > 2:
        factors.append(2.0)
        rest /= 2
    while rest < 0.5:
        factors.append(0.5)
        rest /= 0.5
    factors.append(rest)
    return "".join(f"atempo={_number(f)}," for f in factors)


def _number(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".") or "0"


def render_document(project: Project) -> EditorDocument:
    document = document_for(project)
    if document is None:
        # Do not silently render legacy transitions as hard cuts.
        from videoflow.timeline.resolve import resolve

        resolved = resolve(project)
        if resolved.transitions or any(
            c.audio and (c.audio.fade_in_frames or c.audio.fade_out_frames)
            for t in resolved.tracks
            for c in t.clips
        ):
            raise ValueError(
                "Legacy transitions/fades need a dedicated renderer; "
                "this renderer handles interactive clip edits"
            )
        document = editable_document(project)
    validate_assets(document, project)
    return document


def compile_graph(
    project: Project, preset: Preset = "final", titles_dir: Path = Path("titles")
) -> RenderGraph:
    """Original sources only. Input indices are local to each independent graph.

    Text clips read title pictures from `titles_dir`, drawn by write_titles.
    """
    document = render_document(project)
    assets_by_id = {a.id: a for a in project.assets}

    def source_frames(clip: EditorClip) -> int:
        asset = assets_by_id.get(clip.asset_id or "")
        return frames(asset.probe.duration_us, project.settings.frame_rate) if asset else 0

    plan = plan_transitions(document, source_frames)
    clips, total = plan.clips, plan.total
    if total < 1:
        raise ValueError("The edit has no enabled content to render")
    settings = project.settings
    width, height = settings.width, settings.height
    if width % 2 or height % 2:
        raise ValueError("MP4 output width and height must be even")
    factor = min(1, 960 / max(width, height)) if preset == "draft" else 1.0
    out_w, out_h = max(2, round(width * factor / 2) * 2), max(2, round(height * factor / 2) * 2)
    # Rounding output dimensions can differ by one pixel; transforms follow both axes.
    sx, sy = out_w / width, out_h / height
    rate = settings.frame_rate
    fps = f"{rate.num}/{rate.den}"
    sample_rate = settings.sample_rate
    samples = frames_to_samples(total, rate, sample_rate)
    video = [
        f"color=c=black:s={out_w}x{out_h}:r={fps},format=rgba,"
        f"trim=end_frame={total},setpts=PTS-STARTPTS[v0]"
    ]
    audio = [
        f"anullsrc=r={sample_rate}:cl=stereo,atrim=end_sample={samples},asetpts=PTS-STARTPTS[a0]"
    ]
    inputs: list[Path] = []
    titles: dict[Path, Title] = {}
    audio_inputs: list[Path] = []
    warnings: list[str] = list(plan.warnings)
    assets = {a.id: a for a in project.assets}
    video_count = 0
    for clip in sorted(clips, key=lambda c: (c.layer, c.start, c.id)):
        if clip.kind == "gap":
            continue
        if clip.kind == "text" and clip.title:
            # A transparent picture of the title, repeated for the clip's frames
            # (docs/features/finishing/clip-effects.md).
            index = len(inputs)
            key = f"{clip.title.model_dump_json()}:{out_w}x{out_h}".encode()
            image = titles_dir / f"{hashlib.sha256(key).hexdigest()[:24]}.png"
            inputs.append(image)
            titles[image] = clip.title
            fade_in = plan.video_fade_in.get(clip.id, 0)
            fade_out = plan.video_fade_out.get(clip.id, 0)
            alpha = f",fade=t=in:s=0:n={fade_in}:alpha=1" if fade_in else ""
            if fade_out:
                alpha += f",fade=t=out:s={clip.duration - fade_out}:n={fade_out}:alpha=1"
            video.append(
                f"[{index}:v:0]format=rgba,loop=loop={clip.duration - 1}:size=1:start=0,"
                f"trim=end_frame={clip.duration}{alpha},"
                f"settb=AVTB,setpts=(N+{clip.start})*{rate.den}/{rate.num}/TB[t{index}]"
            )
            video.append(
                f"[v{video_count}][t{index}]overlay=eof_action=pass:repeatlast=0:format=rgb:"
                f"enable='{_window(clip.start, clip.start + clip.duration, rate)}'"
                f"[v{video_count + 1}]"
            )
            video_count += 1
            continue
        asset = assets[clip.asset_id or ""]
        source = Path(asset.path)
        if not source.is_file():
            raise FileNotFoundError(f"Original media is offline: {clip.name}")
        if clip.kind == "video":
            index = len(inputs)
            inputs.append(source)
            transform = clip.transform
            w, h = max(1, round(transform.width * sx)), max(1, round(transform.height * sy))
            crop_x, crop_y = round(w * transform.crop_left), round(h * transform.crop_top)
            crop_w = max(1, w - crop_x - round(w * transform.crop_right))
            crop_h = max(1, h - crop_y - round(h * transform.crop_bottom))
            crop_x, crop_y = min(crop_x, w - 1), min(crop_y, h - 1)
            crop_w, crop_h = min(crop_w, w - crop_x), min(crop_h, h - crop_y)
            x, y = round(transform.x * sx) + crop_x, round(transform.y * sy) + crop_y
            hdr = asset.probe.video.hdr if asset.probe.video else "none"
            tone = ""
            if hdr in ("hlg", "pq"):
                transfer = "arib-std-b67" if hdr == "hlg" else "smpte2084"
                tone = (
                    f"zscale=tin={transfer}:pin=bt2020:min=bt2020nc:rin=tv:t=linear:npl=100,"
                    "format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
                    "zscale=t=bt709:m=bt709:r=tv,"
                )
                warnings.append(f"{clip.name}: {hdr.upper()} tone-mapped to SDR BT.709")
            # Trim once so foreground and backdrop share exactly the same source frames.
            if clip.still_frame is not None:
                # A still clip repeats one picture: the image, or one frame of a video
                # (docs/features/import-analysis/still-images.md).
                held = clip.still_frame
                pick = "" if asset.probe.still else f"fps={fps}:round=near,"
                prepare = (
                    f"[{index}:v:0]{pick}trim=start_frame={held}:end_frame={held + 1},"
                    f"setpts=PTS-STARTPTS,loop=loop={clip.duration - 1}:size=1:start=0,"
                    f"trim=end_frame={clip.duration},"
                    f"settb=AVTB,setpts=N*{rate.den}/{rate.num}/TB,{tone}setsar=1,format=rgba"
                )
            else:
                prepare = (
                    f"[{index}:v:0]fps={fps}:round=near,"
                    f"trim=start_frame={clip.source_in}:end_frame={clip.source_out},"
                    f"{_retime(clip.speed, fps)}tpad=stop_mode=clone:stop={clip.duration},"
                    f"trim=end_frame={clip.duration},settb=AVTB,"
                    f"setpts=N*{rate.den}/{rate.num}/TB,{tone}setsar=1,format=rgba"
                )
            fade_in = plan.video_fade_in.get(clip.id, 0)
            fade_out = plan.video_fade_out.get(clip.id, 0)
            # Dissolves and edge fades blend the picture (and its backdrop) with what lies below.
            alpha = f",fade=t=in:s=0:n={fade_in}:alpha=1" if fade_in else ""
            if fade_out:
                alpha += f",fade=t=out:s={clip.duration - fade_out}:n={fade_out}:alpha=1"
            prepare += alpha
            timing = f"settb=AVTB,setpts=PTS+{clip.start}*{rate.den}/{rate.num}/TB"
            enable = _window(clip.start, clip.start + clip.duration, rate)
            if clip.background.mode == "blur":
                video.append(prepare + f",split=2[fg{index}][bg{index}]")
                # Match preview: cover the viewport with an extra 8% overscan before blur.
                bw, bh = max(2, round(out_w * 1.08)), max(2, round(out_h * 1.08))
                video.append(
                    f"[bg{index}]scale={bw}:{bh}:force_original_aspect_ratio=increase,"
                    f"crop={out_w}:{out_h},gblur=sigma={20 * sx},{timing}[back{index}]"
                )
            else:
                video.append(prepare + f"[fg{index}]")
                if clip.background.mode == "color":
                    color = clip.background.color.replace("#", "0x")
                    video.append(
                        f"color=c={color}:s={out_w}x{out_h}:r={fps},format=rgba,"
                        f"trim=end_frame={clip.duration}{alpha},{timing}[back{index}]"
                    )
            if clip.background.mode != "transparent":
                video.append(
                    f"[v{video_count}][back{index}]overlay=eof_action=pass:"
                    f"repeatlast=0:format=rgb:enable='{enable}'[v{video_count + 1}]"
                )
                video_count += 1
            if animated(clip):
                # Keyframes, rotation or opacity: drawn on a full frame
                # (docs/features/finishing/keyframes.md).
                picture = _animated(clip, index, (out_w, out_h), (sx, sy), rate)
                video.append(f"[fg{index}]{picture},{timing}[p{index}]")
                x = y = 0
            else:
                video.append(
                    f"[fg{index}]scale={w}:{h},"
                    f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}:exact=1,"
                    f"{timing}[p{index}]"
                )
            video.append(
                f"[v{video_count}][p{index}]overlay=x={x}:y={y}:"
                f"eof_action=pass:repeatlast=0:format=rgb:"
                f"enable='{enable}'"
                f"[v{video_count + 1}]"
            )
            video_count += 1
        else:
            index = len(audio_inputs)
            audio_inputs.append(source)
            source_in = frames_to_samples(clip.source_in, rate, sample_rate)
            source_count = frames_to_samples(clip.span, rate, sample_rate)
            count = frames_to_samples(
                clip.start + clip.duration, rate, sample_rate
            ) - frames_to_samples(clip.start, rate, sample_rate)
            delay = frames_to_samples(clip.start, rate, sample_rate)
            fade_in, fade_out = plan.audio_fades.get(clip.id, (0, 0))
            fades = ""
            if fade_in:
                fades += f"afade=t=in:ss=0:ns={frames_to_samples(fade_in, rate, sample_rate)},"
            if fade_out:
                n = frames_to_samples(fade_out, rate, sample_rate)
                fades += f"afade=t=out:ss={max(0, count - n)}:ns={n},"
            audio.append(
                f"[{index}:a:0]aresample={sample_rate},"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"atrim=start_sample={source_in}:end_sample={source_in + source_count},"
                f"asetpts=PTS-STARTPTS,{_atempo(clip.speed)}{_volume(clip, rate)}"
                f"apad=whole_len={count},atrim=end_sample={count},"
                f"{fades}volume={_number(clip.gain_db)}dB,adelay={delay}S:all=1[s{index}]"
            )
    for number, dip in enumerate(plan.dips):
        # A dip covers the whole composite with a colour that fades in, then out.
        ramps: list[str] = []
        if dip.before:
            ramps.append(f"fade=t=in:s=0:n={dip.before}:alpha=1")
        if dip.after:
            ramps.append(f"fade=t=out:s={dip.before}:n={dip.after}:alpha=1")
        length = dip.before + dip.after
        video.append(
            f"color=c={dip.color}:s={out_w}x{out_h}:r={fps},format=rgba,"
            f"trim=end_frame={length},{','.join(ramps)},settb=AVTB,"
            f"setpts=PTS+{dip.start}*{rate.den}/{rate.num}/TB[dip{number}]"
        )
        video.append(
            f"[v{video_count}][dip{number}]overlay=eof_action=pass:repeatlast=0:format=rgb:"
            f"enable='{_window(dip.start, dip.start + length, rate)}'[v{video_count + 1}]"
        )
        video_count += 1
    video.append(
        # The black base is CFR and drives every overlay; an fps filter here drops the
        # final frame at EOF on FFmpeg 6.1-7.x.
        f"[v{video_count}]trim=end_frame={total},"
        f"settb=expr={rate.den}/{rate.num},setpts=N,format=yuv420p[vout]"
    )
    if audio_inputs:
        sources = "[a0]" + "".join(f"[s{i}]" for i in range(len(audio_inputs)))
        audio.append(
            f"{sources}amix=inputs={len(audio_inputs) + 1}:duration=first:"
            f"dropout_transition=0:normalize=0,atrim=end_sample={samples}[aout]"
        )
    else:
        audio.append("[a0]anull[aout]")
    return RenderGraph(
        inputs,
        ";\n".join(video),
        ";\n".join(audio),
        audio_inputs,
        out_w,
        out_h,
        total,
        samples,
        rate,
        warnings,
        titles,
    )
