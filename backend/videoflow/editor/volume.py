"""Volume ranges (spec 21): mutes and ducking as a gain envelope over a clip."""

from videoflow.editor.models import EditorClip, VolumeRange


def range_factor(r: VolumeRange, source_frame: float) -> float:
    """1 outside the range and its ramps, the range factor inside, linear ramps between."""
    if r.ramp:
        u = min(
            (source_frame - (r.start - r.ramp)) / r.ramp, (r.end + r.ramp - source_frame) / r.ramp
        )
    else:
        u = 1.0 if r.start <= source_frame < r.end else 0.0
    u = min(1.0, max(0.0, u))
    return 1 - (1 - r.factor) * u


def envelope(clip: EditorClip, source_frame: float) -> float:
    return min((range_factor(r, source_frame) for r in clip.volume_ranges), default=1.0)


def volume_expression(clip: EditorClip, fps: float) -> str | None:
    """FFmpeg `volume` expression over `t`, seconds since the clip's timeline start."""
    ranges = [
        r
        for r in clip.volume_ranges
        if r.end + r.ramp > clip.source_in and r.start - r.ramp < clip.source_out
    ]
    if not ranges:
        return None

    def seconds(source_frame: float) -> str:
        return f"{(source_frame - clip.source_in) / clip.speed / fps:.6f}"

    terms = []
    for r in ranges:
        a, b = seconds(r.start - r.ramp), seconds(r.end + r.ramp)
        if r.ramp:
            ramp = f"{r.ramp / clip.speed / fps:.6f}"
            u = f"clip(min((t-{a})/{ramp},({b}-t)/{ramp}),0,1)"
        else:
            u = f"between(t,{seconds(r.start)},{seconds(r.end)})"
        terms.append(f"(1-{1 - r.factor:.6f}*{u})")
    expression = terms[0]
    for term in terms[1:]:
        expression = f"min({expression},{term})"
    return expression
