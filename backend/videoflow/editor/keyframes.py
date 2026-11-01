"""Keyframed transforms (docs/features/keyframes.md): one definition of the interpolation for
the preview (mirrored in frontend/src/keyframes.ts), the render and the exports."""

from collections.abc import Callable, Sequence

from videoflow.editor.models import EditorClip, Keyframe, Transform

ANIMATED = (
    "x",
    "y",
    "width",
    "height",
    "crop_left",
    "crop_right",
    "crop_top",
    "crop_bottom",
    "rotation",
    "opacity",
)
"""Transform values interpolated between keyframes."""


def smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def transform_at(clip: EditorClip, source_frame: float) -> Transform:
    """The clip's transform at a source frame: its keyframes interpolated, or its transform."""
    keys = clip.keyframes
    if not keys:
        return clip.transform
    if source_frame <= keys[0].frame:
        return keys[0].transform
    if source_frame >= keys[-1].frame:
        return keys[-1].transform
    index = max(i for i, k in enumerate(keys) if k.frame <= source_frame)
    a, b = keys[index], keys[index + 1]
    u = (source_frame - a.frame) / (b.frame - a.frame)
    if a.ease == "smooth":
        u = smooth(u)
    values = {}
    for name in ANIMATED:
        start, end = getattr(a.transform, name), getattr(b.transform, name)
        values[name] = start + (end - start) * u
    return a.transform.model_copy(update=values)


def animated(clip: EditorClip) -> bool:
    """Whether the render needs the per-frame path: keyframes, rotation or opacity."""
    t = clip.transform
    return bool(clip.keyframes) or t.rotation != 0 or t.opacity != 1


def keys_of(clip: EditorClip) -> Sequence[Keyframe]:
    """Keyframes, or the static transform as a single keyframe."""
    return clip.keyframes or [Keyframe(frame=clip.source_in, transform=clip.transform)]


def piecewise(keys: Sequence[Keyframe], value: Callable[[Transform], float], position: str) -> str:
    """FFmpeg expression of one value over `position` (an expression in source frames)."""
    values = [value(k.transform) for k in keys]
    if all(v == values[0] for v in values):
        return _number(values[0])
    expression = _number(values[-1])
    for a, b, va, vb in reversed(list(zip(keys, keys[1:], values, values[1:], strict=False))):
        u = f"(({position})-{a.frame})/{b.frame - a.frame}"
        if a.ease == "smooth":
            u = f"(({u})*({u})*(3-2*({u})))"
        segment = _number(va) if va == vb else f"({_number(va)}+{_number(vb - va)}*{u})"
        expression = f"if(lt({position},{b.frame}),{segment},{expression})"
    return f"if(lt({position},{keys[0].frame}),{_number(values[0])},{expression})"


def _number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
