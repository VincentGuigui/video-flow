"""Draw the Video-Flow icon files into assets/icons/.

The mark matches the editor header: a green rounded square tilted 7 degrees with the
upright Lucide "Film" glyph in white. Outputs:

- video-flow.png: 256 px, used for the desktop window and taskbar icon
- video-flow.ico: 16 to 256 px, embedded in the Windows executable

Run after changing the mark: uv run --project backend python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ICONS = Path(__file__).resolve().parent.parent / "assets" / "icons"
GREEN = (43, 88, 68, 255)  # .brand-mark background in frontend/src/style.css
WHITE = (251, 252, 248, 255)
CANVAS = 1024  # drawn large, then downscaled
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def draw() -> Image.Image:
    # Square of side s, tilted 7 degrees, fitting the canvas with a small margin.
    side = round(CANVAS * 0.84)
    tile = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    offset = (CANVAS - side) // 2
    ImageDraw.Draw(tile).rounded_rectangle(
        (offset, offset, offset + side, offset + side), radius=round(side * 9 / 31), fill=GREEN
    )
    image = tile.rotate(7, resample=Image.Resampling.BICUBIC)
    # Lucide Film on a 24-unit grid, drawn at 19/31 of the square (as in the header).
    unit = side * 19 / 31 / 24
    origin = (CANVAS - 24 * unit) / 2
    width = round(2 * unit)

    def point(x: float, y: float) -> tuple[float, float]:
        return origin + x * unit, origin + y * unit

    pen = ImageDraw.Draw(image)
    # SVG strokes are centred on the path; Pillow draws outlines inside the box.
    half = width / 2
    (x0, y0), (x1, y1) = point(3, 3), point(21, 21)
    pen.rounded_rectangle(
        (x0 - half, y0 - half, x1 + half, y1 + half),
        radius=round(2 * unit + half),
        outline=WHITE,
        width=width,
    )
    for (x1, y1), (x2, y2) in [
        ((7, 3), (7, 21)),
        ((3, 7.5), (7, 7.5)),
        ((3, 12), (21, 12)),
        ((3, 16.5), (7, 16.5)),
        ((17, 3), (17, 21)),
        ((17, 7.5), (21, 7.5)),
        ((17, 16.5), (21, 16.5)),
    ]:
        a, b = point(x1, y1), point(x2, y2)
        pen.line((a, b), fill=WHITE, width=width)
        for x, y in (a, b):  # round caps
            r = width / 2
            pen.ellipse((x - r, y - r, x + r, y + r), fill=WHITE)
    return image


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    image = draw()
    image.resize((256, 256), Image.Resampling.LANCZOS).save(ICONS / "video-flow.png")
    image.save(ICONS / "video-flow.ico", sizes=[(s, s) for s in SIZES])
    print(f"Wrote {ICONS / 'video-flow.png'} and {ICONS / 'video-flow.ico'}")


if __name__ == "__main__":
    main()
