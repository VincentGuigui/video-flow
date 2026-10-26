"""Cancellable, validated MP4 output. Publish only after frame/duration checks pass."""

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoflow.core.time import frame_to_us
from videoflow.hw.video import EncoderOption, choose_encoder, software_encoder
from videoflow.media import ffmpeg
from videoflow.media.caps import get_caps
from videoflow.media.proxy import default_hw_report
from videoflow.project.models import Project
from videoflow.project.store import Bundle, save_atomic
from videoflow.render.graph import Preset, RenderGraph, compile_graph
from videoflow.render.loudness import measured_filter, measurement

type Progress = Callable[[float, str], None]


@dataclass(frozen=True)
class RenderResult:
    path: Path
    report: Path
    frames: int


def _inputs(paths: list[Path]) -> list[str]:
    return [arg for path in paths for arg in ("-threads", "1", "-i", str(path))]


def audio_graph(
    graph: RenderGraph, *, offset: int = 0, normalize: str | None = None, sample_rate: int = 48000
) -> str:
    result = re.sub(r"\[(\d+):a:0\]", lambda m: f"[{int(m[1]) + offset}:a:0]", graph.audio)
    chain = normalize + "," if normalize else ""
    return (
        result + f";\n[aout]{chain}aresample={sample_rate},apad=whole_len={graph.samples},"
        f"atrim=end_sample={graph.samples}[arender]"
    )


async def render_project(
    project: Project,
    bundle: Bundle,
    *,
    preset: Preset = "final",
    hw: str = "auto",
    normalize: bool = True,
    cancel: asyncio.Event | None = None,
    on_progress: Progress | None = None,
    render_id: str | None = None,
) -> RenderResult:
    identifier = render_id or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
        raise ValueError("Invalid render identifier")
    plan = compile_graph(project, preset)
    folder = bundle.cache_dir / "render" / identifier
    folder.mkdir(parents=True, exist_ok=False)
    bundle.renders_dir.mkdir(parents=True, exist_ok=True)
    target = bundle.renders_dir / f"render-{identifier}.mp4"
    partial = target.with_name(f".{target.stem}.part.mp4")
    report_path = target.with_suffix(".log.json")
    started = time.monotonic()
    attempts: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "projectId": project.id,
        "revision": project.revision,
        "preset": preset,
        "width": plan.width,
        "height": plan.height,
        "rate": plan.rate.dump(),
        "expectedFrames": plan.frames,
        "expectedSamples": plan.samples,
        "warnings": list(plan.warnings),
        "attempts": attempts,
        "state": "running",
    }

    def progress(value: float, phase: str) -> None:
        if cancel and cancel.is_set():
            raise asyncio.CancelledError()
        if on_progress:
            on_progress(value, phase)

    async def run(args: list[str], low: float, high: float, phase: str) -> ffmpeg.Result:
        progress(low, phase)
        attempts.append({"phase": phase, "args": args})
        result = await ffmpeg.run(
            args,
            cancel=cancel,
            duration_us=frame_to_us(plan.frames, plan.rate),
            on_progress=lambda p: progress(low + (high - low) * (p.fraction or 0), phase),
        )
        attempts[-1]["returncode"] = result.returncode
        attempts[-1]["stderr"] = result.stderr_tail
        if result.cancelled or cancel and cancel.is_set():
            raise asyncio.CancelledError()
        return result

    try:
        progress(0, "Checking FFmpeg capabilities")
        caps = await asyncio.to_thread(get_caps)
        report["ffmpeg"] = caps.version
        if plan.warnings and not (caps.has_filter("zscale") and caps.has_filter("tonemap")):
            raise ValueError("This FFmpeg build lacks zscale/tonemap for HDR sources")
        loudness = None
        if normalize and plan.audio_inputs:
            target_loudness = project.settings.loudness_target
            graph = audio_graph(
                plan,
                normalize=(
                    f"loudnorm=I={target_loudness.integrated}:TP={target_loudness.true_peak}:"
                    "LRA=11:print_format=json"
                ),
                sample_rate=project.settings.sample_rate,
            )
            script = folder / "audio.ffgraph"
            save_atomic(script, graph.encode())
            args = [
                "-y",
                *_inputs(plan.audio_inputs),
                "-filter_complex_threads",
                "1",
                caps.graph_flag,
                str(script),
                "-map",
                "[arender]",
                "-vn",
                "-f",
                "null",
                "-",
            ]
            result = await run(args, 0.02, 0.2, "Measuring audio loudness")
            if not result.ok:
                raise ValueError("Loudness measurement failed: " + result.stderr_tail)
            measured = measurement(result.stderr_tail)
            report["loudness"] = measured
            if measured:
                loudness = measured_filter(
                    measured, target_loudness.integrated, target_loudness.true_peak
                )
            else:
                report["warnings"].append(
                    "Silent or below-gate audio: loudness normalization skipped"
                )
        progress(0.2, "Selecting video encoder")
        encoder = software_encoder()
        if hw != "cpu":
            hardware = await asyncio.to_thread(default_hw_report, caps)
            encoder = choose_encoder(hardware, prefer=hw)

        async def encode(option: EncoderOption) -> ffmpeg.Result:
            video = plan.video
            if option.upload_filter:
                video = video.replace("[vout]", "[vsoftware]")
                video += f";\n[vsoftware]{option.upload_filter}[vout]"
            script = folder / (option.encoder + ".ffgraph")
            graph = (
                video
                + ";\n"
                + audio_graph(
                    plan,
                    offset=len(plan.inputs),
                    normalize=loudness,
                    sample_rate=project.settings.sample_rate,
                )
            )
            save_atomic(script, graph.encode())
            args = [
                "-y",
                *option.init_args,
                *_inputs([*plan.inputs, *plan.audio_inputs]),
                "-filter_complex_threads",
                "1",
                caps.graph_flag,
                str(script),
                "-map",
                "[vout]",
                "-map",
                "[arender]",
                "-c:v",
                option.encoder,
                *option.quality_args(28 if preset == "draft" else 18),
            ]
            if option.is_software:
                args += ["-preset", "ultrafast" if preset == "draft" else "medium", "-threads", "2"]
            args += [
                "-c:a",
                "aac",
                "-b:a",
                "128k" if preset == "draft" else "192k",
                "-ar",
                str(project.settings.sample_rate),
                "-ac",
                "2",
                "-fps_mode",
                "cfr",
                "-r",
                f"{plan.rate.num}/{plan.rate.den}",
                "-colorspace",
                "bt709",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-movflags",
                "+faststart",
                "-map_metadata",
                "-1",
                str(partial),
            ]
            return await run(args, 0.2, 0.94, f"Encoding MP4 · {option.encoder}")

        result = await encode(encoder)
        if not result.ok and not encoder.is_software:
            report["warnings"].append(f"{encoder.encoder} failed; retried using libx264")
            encoder = software_encoder()
            result = await encode(encoder)
        if not result.ok:
            raise ValueError("Video encoding failed: " + result.stderr_tail)
        progress(0.95, "Validating frame count and audio duration")
        actual = await ffmpeg.probe(partial)
        tolerance = frame_to_us(1, plan.rate) + 1000
        video = actual.video
        report["validation"] = {
            "frames": video.nb_frames if video else None,
            "width": video.width if video else None,
            "height": video.height if video else None,
            "rate": str(video.fps) if video else None,
        }
        if (
            video is None
            or video.nb_frames != plan.frames
            or (video.width, video.height) != (plan.width, plan.height)
        ):
            raise ValueError(f"Rendered video does not match the edit: {report['validation']}")
        if video.fps != plan.rate.fraction:
            raise ValueError("Rendered frame rate does not match the project")
        if not actual.audio or actual.audio[0].sample_rate != project.settings.sample_rate:
            raise ValueError("Rendered audio stream is missing or has the wrong sample rate")
        audio_us = actual.audio[0].duration_us
        expected_us = frame_to_us(plan.frames, plan.rate)
        if audio_us is None or abs(audio_us - expected_us) > tolerance:
            raise ValueError("Rendered audio duration differs from video by more than one frame")
        progress(0.99, "Publishing validated MP4")
        report.update(
            {
                "state": "done",
                "encoder": encoder.encoder,
                "actualFrames": video.nb_frames,
                "audioDurationUs": audio_us,
                "output": str(target),
            }
        )
        os.replace(partial, target)
        return RenderResult(target, report_path, plan.frames)
    except asyncio.CancelledError:
        report["state"] = "cancelled"
        raise
    except Exception as exc:
        report.update({"state": "failed", "error": str(exc)})
        raise
    finally:
        partial.unlink(missing_ok=True)
        report["elapsedSeconds"] = round(time.monotonic() - started, 3)
        save_atomic(report_path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
