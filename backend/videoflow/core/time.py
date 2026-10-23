"""Time representation: integer microseconds, rational rates, frame quantisation.

Rules (08 §1 "Time representation"):

* Source and timeline times are stored as integer microseconds (:data:`Micros`).
  Never floats: float seconds give 1-2 frame overshoots in FFmpeg and drift when summed.
* Rates are rationals (``30000/1001``, never ``29.97``).
* **Quantisation rule.** A time ``t`` maps to frame ``round_half_up(t * fps)``
  (:func:`frames`). A clip ``[in, out)`` covers ``frames(out) - frames(in)`` frames
  (:func:`clip_frames`). Timeline positions are cumulative sums of clip frame counts, so
  they are exact integers and never drift, whatever the number of clips or the rate.
  Quantisation happens at compile time only; stored times keep microsecond precision so
  changing the project rate never accumulates rounding errors.
* Timecode is always displayed non-drop (``HH:MM:SS:FF`` with the nominal integer rate);
  NTSC rates (``den == 1001``) carry a UI note instead of drop-frame semicolons.
"""

from fractions import Fraction
from typing import Annotated, Self

from pydantic import ConfigDict, Field, model_validator

from videoflow.core.base import CamelModel

type Micros = int
"""Integer microseconds. Source time, timeline time or a duration."""

US_PER_SECOND = 1_000_000

NonNegativeMicros = Annotated[int, Field(ge=0)]


def _div_round_half_up(num: int, den: int) -> int:
    """``round(num / den)`` with halves rounded away from zero, exact on integers."""
    if den <= 0:
        raise ValueError("denominator must be positive")
    if num >= 0:
        return (2 * num + den) // (2 * den)
    return -((-2 * num + den) // (2 * den))


class Rational(CamelModel):
    """A positive rational rate, e.g. ``Rational(num=30000, den=1001)`` for 29.97 fps."""

    model_config = ConfigDict(frozen=True)

    num: int = Field(gt=0)
    den: int = Field(default=1, gt=0)

    @classmethod
    def of(cls, num: int, den: int = 1) -> Self:
        return cls(num=num, den=den)

    @classmethod
    def from_float(cls, fps: float) -> Self:
        """Best rational for a probed float rate; snaps 29.97-like values to x000/1001."""
        if fps <= 0:
            raise ValueError("fps must be positive")
        nominal = round(fps)
        if abs(fps - nominal) < 1e-3:
            return cls(num=nominal, den=1)
        ntsc = Fraction(nominal * 1000, 1001)
        if abs(fps - float(ntsc)) < 2e-3:
            return cls(num=nominal * 1000, den=1001)
        frac = Fraction(fps).limit_denominator(1001)
        return cls(num=frac.numerator, den=frac.denominator)

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.num, self.den)

    @property
    def nominal(self) -> int:
        """Integer rate used for timecode labels (30 for 30000/1001)."""
        return max(1, _div_round_half_up(self.num, self.den))

    @property
    def is_ntsc(self) -> bool:
        """True for x000/1001 rates (29.97, 23.976, 59.94): shown non-drop with a note."""
        return self.den == 1001

    def __float__(self) -> float:
        return self.num / self.den

    def __str__(self) -> str:
        return f"{self.num}/{self.den}"


class TimeRange(CamelModel):
    """Half-open range ``[start_us, end_us)`` in microseconds."""

    model_config = ConfigDict(frozen=True)

    start_us: Micros
    end_us: Micros

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end_us < self.start_us:
            raise ValueError("end_us must be >= start_us")
        return self

    @property
    def duration_us(self) -> Micros:
        return self.end_us - self.start_us

    def overlap_us(self, other: "TimeRange") -> Micros:
        return max(0, min(self.end_us, other.end_us) - max(self.start_us, other.start_us))

    def iou(self, other: "TimeRange") -> float:
        """Intersection over union, used by the segment id remap (match if >= 0.5)."""
        inter = self.overlap_us(other)
        union = max(self.end_us, other.end_us) - min(self.start_us, other.start_us)
        return inter / union if union > 0 else 0.0


def seconds_to_us(seconds: float) -> Micros:
    """Convert probe/engine float seconds to integer microseconds (round half up)."""
    return _div_round_half_up(round(seconds * 1e9), 1000)


def us_to_seconds(us: Micros) -> float:
    return us / US_PER_SECOND


def frames(us: Micros, rate: Rational) -> int:
    """Frame index of time ``us`` at ``rate``: ``round_half_up(us * fps)``."""
    return _div_round_half_up(us * rate.num, US_PER_SECOND * rate.den)


def frame_to_us(frame: int, rate: Rational) -> Micros:
    """Start time of ``frame`` in microseconds. ``frames(frame_to_us(n)) == n``."""
    return _div_round_half_up(frame * US_PER_SECOND * rate.den, rate.num)


def clip_frames(source_in_us: Micros, source_out_us: Micros, rate: Rational) -> int:
    """Visible frame count of a clip ``[in, out)``: ``frames(out) - frames(in)``."""
    return frames(source_out_us, rate) - frames(source_in_us, rate)


def duration_frames(duration_us: Micros, rate: Rational) -> int:
    """Frame count of a duration that is not anchored in source time (e.g. a transition)."""
    return frames(duration_us, rate)


def samples(us: Micros, sample_rate: int) -> int:
    """Sample index of time ``us`` (same rounding rule as frames)."""
    return _div_round_half_up(us * sample_rate, US_PER_SECOND)


def frames_to_samples(frame_count: int, rate: Rational, sample_rate: int) -> int:
    """Audio samples matching ``frame_count`` video frames (audio follows video at concat)."""
    return _div_round_half_up(frame_count * rate.den * sample_rate, rate.num)


def format_timecode(frame: int, rate: Rational) -> str:
    """Non-drop timecode ``HH:MM:SS:FF`` using the nominal integer rate."""
    sign = "-" if frame < 0 else ""
    frame = abs(frame)
    fps = rate.nominal
    ff = frame % fps
    total_seconds = frame // fps
    hh, rem = divmod(total_seconds, 3600)
    mm, ss = divmod(rem, 60)
    return f"{sign}{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def parse_timecode(text: str, rate: Rational) -> int:
    """Inverse of :func:`format_timecode` (accepts ``;`` as the last separator too)."""
    sign = -1 if text.startswith("-") else 1
    parts = text.lstrip("-").replace(";", ":").split(":")
    if len(parts) != 4:
        raise ValueError(f"invalid timecode: {text!r}")
    hh, mm, ss, ff = (int(p) for p in parts)
    fps = rate.nominal
    if not (0 <= mm < 60 and 0 <= ss < 60 and 0 <= ff < fps):
        raise ValueError(f"invalid timecode: {text!r}")
    return sign * (((hh * 60 + mm) * 60 + ss) * fps + ff)
