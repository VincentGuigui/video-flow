"""Text clips (spec 21): layout and the transparent picture drawn for the render and preview.

Every line sits in its own font box (ascender to descender), padded when the title has a
box. A title is centred in the picture; a lower third is aligned to the left margin with
its last line ending at LOWER_THIRD_BOTTOM. The first line is bold; a lower third's other
lines are regular, at DETAIL_SIZE of the first line. Text without a box gets a soft shadow.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from videoflow.editor.fonts import load_font
from videoflow.editor.models import Title

DETAIL_SIZE = 0.7
LOWER_THIRD_LEFT = 0.06
LOWER_THIRD_BOTTOM = 0.9
PAD_X, PAD_Y = 0.35, 0.12
"""Box padding, relative to the first line's font size."""
GAP = 0.15
"""Space between line boxes, relative to the first line's font size."""
SHADOW = 0.04
"""Offset of the shadow under text without a box, relative to the font size."""
SHADOW_OPACITY = 0.5


@dataclass(frozen=True)
class TitleLine:
    text: str
    bold: bool
    size: float
    """Font size in pixels."""
    left: float
    top: float
    """Top-left of the line's font box (ascender line), in pixels."""
    width: float
    height: float


@dataclass(frozen=True)
class TitleLayout:
    lines: list[TitleLine]
    centred: bool
    pad_x: float
    pad_y: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Left, top, right, bottom of everything drawn, boxes included."""
        return (
            min(line.left for line in self.lines) - self.pad_x,
            self.lines[0].top - self.pad_y,
            max(line.left + line.width for line in self.lines) + self.pad_x,
            self.lines[-1].top + self.lines[-1].height + self.pad_y,
        )


def title_lines(title: Title) -> list[str]:
    return [line.strip() for line in title.text.splitlines() if line.strip()]


def layout_title(title: Title, width: float, height: float) -> TitleLayout:
    first = title.size * height
    pad_x, pad_y = (PAD_X * first, PAD_Y * first) if title.box else (0.0, 0.0)
    gap = GAP * first if title.box else 0.0
    lower = title.style == "lower_third"
    entries = []
    for index, text in enumerate(title_lines(title)):
        bold = index == 0 or not lower
        size = first if index == 0 or not lower else first * DETAIL_SIZE
        font = load_font(bold, size)
        ascent, descent = font.getmetrics()
        entries.append((text, bold, size, font.getlength(text), float(ascent + descent)))
    total = sum(h + 2 * pad_y for *_, h in entries) + gap * max(0, len(entries) - 1)
    top = LOWER_THIRD_BOTTOM * height - total if lower else (height - total) / 2
    lines = []
    for text, bold, size, advance, line_height in entries:
        left = LOWER_THIRD_LEFT * width + pad_x if lower else (width - advance) / 2
        lines.append(TitleLine(text, bold, size, left, top + pad_y, advance, line_height))
        top += line_height + 2 * pad_y + gap
    return TitleLayout(lines, not lower, pad_x, pad_y)


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _layer(
    size: tuple[int, int],
    color: str,
    opacity: float,
    paint: Callable[[ImageDraw.ImageDraw], None],
    blur: float = 0,
) -> Image.Image:
    """A flat colour whose alpha is the painted coverage (no dark fringes)."""
    mask = Image.new("L", size, 0)
    paint(ImageDraw.Draw(mask))
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    if opacity < 1:
        mask = mask.point(lambda value: round(value * opacity))
    layer = Image.new("RGBA", size, (*_rgb(color), 0))
    layer.putalpha(mask)
    return layer


def title_image(title: Title, width: int, height: int) -> Image.Image:
    """The title on a transparent picture of the output size."""
    layout = layout_title(title, width, height)
    size = (width, height)
    image = Image.new("RGBA", size, (0, 0, 0, 0))

    def text(offset: float) -> Callable[[ImageDraw.ImageDraw], None]:
        def paint(draw: ImageDraw.ImageDraw) -> None:
            for line in layout.lines:
                shift = offset * line.size
                draw.text(
                    (line.left + shift, line.top + shift),
                    line.text,
                    fill=255,
                    font=load_font(line.bold, line.size),
                    anchor="la",
                )

        return paint

    def boxes(draw: ImageDraw.ImageDraw) -> None:
        for line in layout.lines:
            draw.rectangle(
                (
                    round(line.left - layout.pad_x),
                    round(line.top - layout.pad_y),
                    round(line.left + line.width + layout.pad_x) - 1,
                    round(line.top + line.height + layout.pad_y) - 1,
                ),
                fill=255,
            )

    if title.box:
        image.alpha_composite(_layer(size, title.box_color, title.box_opacity, boxes))
    else:
        blur = SHADOW * title.size * height
        image.alpha_composite(_layer(size, "#000000", SHADOW_OPACITY, text(SHADOW), blur))
    image.alpha_composite(_layer(size, title.color, 1, text(0)))
    return image


@lru_cache(maxsize=64)
def _png(key: str, width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    title_image(Title.model_validate_json(key), width, height).save(
        buffer, format="PNG", compress_level=1
    )
    return buffer.getvalue()


def title_png(title: Title, width: int, height: int) -> bytes:
    return _png(title.model_dump_json(), width, height)
