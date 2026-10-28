"""Zoom & pan curves (spec 21): one definition for preview parity, render and export."""

from collections.abc import Iterable

from videoflow.editor.models import EditorClip, Zoom


def _ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def ramps(zoom: Zoom) -> tuple[int, int]:
    """Ease-in and ease-out lengths, shortened to fit the zoom."""
    length = zoom.end - zoom.start
    ease_in = min(zoom.ease_in, length)
    return ease_in, min(zoom.ease_out, length - ease_in)


def amount(zoom: Zoom, source_frame: float) -> float:
    """0 outside the zoom, 1 while holding, smoothstep ramps in between."""
    ease_in, ease_out = ramps(zoom)
    f = source_frame
    if f < zoom.start or f >= zoom.end:
        return 0.0
    if ease_in and f < zoom.start + ease_in:
        return _ease((f - zoom.start) / ease_in)
    if ease_out and f >= zoom.end - ease_out:
        return _ease((zoom.end - f) / ease_out)
    return 1.0


def factor(zooms: Iterable[Zoom], source_frame: float) -> float:
    return 1 + sum((z.scale - 1) * amount(z, source_frame) for z in zooms)


def zoompan_expressions(clip: EditorClip) -> tuple[str, str, str] | None:
    """FFmpeg zoompan z/x/y expressions over the clip's output frame number `on`."""
    zooms = [z for z in clip.zooms if z.end > clip.source_in and z.start < clip.source_out]
    if not zooms:
        return None
    src = f"({clip.source_in}+on*{clip.speed:g})"

    def smooth(u: str) -> str:
        return f"(({u})*({u})*(3-2*({u})))"

    terms = []
    for z in zooms:
        ease_in, ease_out = ramps(z)
        hold = f"{z.scale - 1:g}"
        rise = f"{hold}*{smooth(f'({src}-{z.start})/{ease_in}')}" if ease_in else hold
        fall = f"{hold}*{smooth(f'({z.end}-{src})/{ease_out}')}" if ease_out else hold
        terms.append(
            f"if(lt({src},{z.start}),0,"
            f"if(lt({src},{z.start + ease_in}),{rise},"
            f"if(lt({src},{z.end - ease_out}),{hold},"
            f"if(lt({src},{z.end}),{fall},0))))"
        )
    # Each zoom keeps its own focus point; outside zooms the factor is 1 and x/y do not matter.
    fx, fy = "0.5", "0.5"
    for zm in reversed(zooms):
        inside = f"between({src},{zm.start},{zm.end})"
        fx, fy = f"if({inside},{zm.x:g},{fx})", f"if({inside},{zm.y:g},{fy})"
    return "1+" + "+".join(terms), f"{fx}*(iw-iw/zoom)", f"{fy}*(ih-ih/zoom)"
