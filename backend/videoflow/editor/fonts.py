"""Bundled title fonts: Inter Regular and Bold (SIL OFL 1.1, see assets/fonts/OFL.txt)."""

from functools import cache
from pathlib import Path

from PIL import ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FILES = {False: "Inter-Regular.otf", True: "Inter-Bold.otf"}
FAMILY = "Inter"


def font_path(bold: bool) -> Path:
    return FONTS_DIR / FONT_FILES[bold]


@cache
def load_font(bold: bool, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(bold)), size)
