"""Audio sync between simultaneous recordings (04 §4.3, corrected by 08 §3).

1. A 100 Hz onset envelope (log-spectral flux in the speech band) is computed per recording;
   it survives band-limiting, gain changes and different noise floors.
2. GCC-PHAT on the envelopes gives a coarse lag (10 ms) and a peak-to-sidelobe ratio (PSR,
   peak over the highest sidelobe outside +-0.5 s). The pair is accepted when PSR >= 4.
3. The lag is refined on raw audio (1 s windows at the full rate, PHAT in the speech band,
   parabolic peak interpolation), at two windows when the overlap allows it, which also gives
   the clock drift in ppm.

Sign convention (matches :class:`SyncResult`): ``b time + offset = a time``. An event at
``t`` in A that appears at ``t + lag`` in B gives ``offset = -lag``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.fft import irfft, next_fast_len, rfft
from scipy.signal import resample_poly

from videoflow.analysis.types import SyncResult
from videoflow.core.time import US_PER_SECOND

ENV_RATE = 100
ENV_CLIP = 3.0
BAND_HZ = (200.0, 3400.0)
PSR_ACCEPT = 4.0
SIDELOBE_EXCLUDE_S = 0.5
REFINE_WINDOW_S = 1.0
REFINE_SEARCH_S = 0.05

type Float = npt.NDArray[np.float64]


def onset_envelope(audio: Float, sr: int, rate: int = ENV_RATE) -> Float:
    """Positive log-spectral flux per ``1/rate`` s frame, mean-removed and unit variance."""
    hop = sr // rate
    win = 2 * hop
    n_frames = max(0, (len(audio) - win) // hop + 1)
    if n_frames < 3:
        return np.zeros(max(n_frames, 0))
    idx = np.arange(win)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = audio[idx] * np.hanning(win)
    spec = np.abs(rfft(frames, axis=1))
    freqs = np.arange(spec.shape[1]) * sr / win
    band = (freqs >= BAND_HZ[0]) & (freqs <= min(BAND_HZ[1], sr / 2))
    logmag = np.log1p(spec[:, band] * 20.0)
    flux = np.maximum(np.diff(logmag, axis=0, prepend=logmag[:1]), 0.0).sum(axis=1)
    flux -= flux.mean()
    std = flux.std()
    # Clip outliers: a single loud click would otherwise correlate with any other click.
    return np.clip(flux / std, -ENV_CLIP, ENV_CLIP) if std > 0 else flux


def gcc_phat(a: Float, b: Float, *, max_lag: int, beta: float = 1.0) -> tuple[Float, int]:
    """Cross-correlation of ``a`` and ``b`` with PHAT^beta weighting.

    Returns ``(corr, zero_index)``: ``corr[zero_index + k]`` is large when ``b[n] ~ a[n - k]``,
    i.e. B lags A by ``k`` samples, for ``k`` in ``[-max_lag, max_lag]``.
    """
    n = next_fast_len(len(a) + len(b))
    cross = np.conj(rfft(a, n)) * rfft(b, n)
    mag = np.abs(cross)
    weighted = cross / np.maximum(mag, 1e-12 * max(mag.max(), 1e-30)) ** beta
    full = irfft(weighted, n)
    corr = np.concatenate([full[-max_lag:], full[: max_lag + 1]])
    return corr, max_lag


def peak_to_sidelobe(corr: Float, peak: int, exclude: int) -> float:
    """Peak over the highest sidelobe magnitude outside ``peak +- exclude`` (about 1 if unrelated).

    A z-score against the sidelobes would sit near 4 even for pure noise on a wide lag
    search; the max-sidelobe ratio separates matching (about 9) from unrelated (about 1).
    """
    mask = np.ones(len(corr), dtype=bool)
    mask[max(0, peak - exclude) : peak + exclude + 1] = False
    side = np.abs(corr[mask])
    if side.size < 8 or corr[peak] <= 0:
        return 0.0
    top = float(side.max())
    return float(corr[peak] / top) if top > 0 else float("inf")


@dataclass(frozen=True)
class CoarseLag:
    lag_s: float
    psr: float
    peak: float


def coarse_lag(
    env_a: Float, env_b: Float, *, max_lag_s: float = 600.0, beta: float = 1.0
) -> CoarseLag:
    """Lag of B behind A (seconds, resolution 1/ENV_RATE) with its PSR."""
    max_lag = min(int(max_lag_s * ENV_RATE), max(len(env_a), len(env_b)) - 1)
    corr, zero = gcc_phat(env_a, env_b, max_lag=max_lag, beta=beta)
    peak = int(np.argmax(corr))
    psr = peak_to_sidelobe(corr, peak, int(SIDELOBE_EXCLUDE_S * ENV_RATE))
    return CoarseLag((peak - zero) / ENV_RATE, psr, float(corr[peak]))


def _refine_window(
    a: Float, b: Float, sr: int, start_a: int, lag0: int, win: int, search: int
) -> float | None:
    """Fine lag (samples, fractional) of B vs A around ``lag0`` for the window at ``start_a``."""
    seg_a = a[start_a : start_a + win]
    start_b = start_a + lag0 - search
    if start_b < 0 or start_b + win + 2 * search > len(b) or len(seg_a) < win:
        return None
    seg_b = b[start_b : start_b + win + 2 * search]
    n = next_fast_len(len(seg_a) + len(seg_b))
    fa, fb = rfft(seg_a, n), rfft(seg_b, n)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    cross = np.conj(fa) * fb
    cross = cross / np.maximum(np.abs(cross), 1e-12)
    cross[(freqs < BAND_HZ[0]) | (freqs > BAND_HZ[1])] = 0.0
    corr = irfft(cross, n)
    # corr[k]: B lags A by k samples, relative to the window start in B.
    cand = corr[: 2 * search + 1]
    peak = int(np.argmax(cand))
    delta = 0.0
    if 0 < peak < len(cand) - 1:
        y0, y1, y2 = cand[peak - 1], cand[peak], cand[peak + 1]
        denom = y0 - 2 * y1 + y2
        delta = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
    # candidate c: B window starts at start_b + c, so the lag is lag0 + (c - search)
    return lag0 + (peak - search) + delta


def _loudest_window(x: Float, win: int, lo: int, hi: int) -> int | None:
    """Start of the loudest ``win``-sample window fully inside ``[lo, hi)``."""
    if hi - lo < win:
        return None
    step = max(1, win // 4)
    starts = np.arange(lo, hi - win + 1, step)
    power = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    energy = power[starts + win] - power[starts]
    return int(starts[int(np.argmax(energy))])


def estimate_sync(
    audio_a: npt.ArrayLike,
    audio_b: npt.ArrayLike,
    sr: int,
    *,
    asset_a: str = "a",
    asset_b: str = "b",
    psr_accept: float = PSR_ACCEPT,
    max_lag_s: float = 600.0,
    beta: float = 1.0,
) -> SyncResult:
    """Offset and drift between two mono recordings at the same sample rate ``sr``."""
    a = np.asarray(audio_a, dtype=np.float64)
    b = np.asarray(audio_b, dtype=np.float64)
    if sr > 16_000:  # the speech band needs no more; keeps the FFTs small
        g = np.gcd(sr, 16_000)
        a, b = resample_poly(a, 16_000 // g, sr // g), resample_poly(b, 16_000 // g, sr // g)
        sr = 16_000
    env_a, env_b = onset_envelope(a, sr), onset_envelope(b, sr)
    if len(env_a) < 3 or len(env_b) < 3:
        return SyncResult(asset_a=asset_a, asset_b=asset_b, offset_us=0, psr=0.0, accepted=False)
    coarse = coarse_lag(env_a, env_b, max_lag_s=max_lag_s, beta=beta)
    lag_samples = round(coarse.lag_s * sr)
    accepted = coarse.psr >= psr_accept

    win = int(REFINE_WINDOW_S * sr)
    search = int(REFINE_SEARCH_S * sr)
    # A-side range where the B window (shifted by the lag) stays inside B.
    lo = max(0, -lag_samples + search)
    hi = min(len(a), len(b) - lag_samples - search)
    points: list[tuple[float, float]] = []  # (time in A [s], fine lag [s])
    if accepted and hi - lo >= win:
        span = hi - lo
        third = max(win, span // 3)
        for lo_i, hi_i in ((lo, lo + third), (hi - third, hi)):
            start = _loudest_window(a, win, lo_i, hi_i)
            if start is None:
                continue
            fine = _refine_window(a, b, sr, start, lag_samples, win, search)
            if fine is not None:
                points.append(((start + win / 2) / sr, fine / sr))
    lag_s, drift = coarse.lag_s, 0.0
    if len(points) == 2 and points[1][0] - points[0][0] >= 5.0:
        (t1, l1), (t2, l2) = points
        drift = (l2 - l1) / (t2 - t1)
        lag_s = l1 - drift * t1  # lag at A time 0
    elif points:
        lag_s = float(np.median([p[1] for p in points]))
    return SyncResult(
        asset_a=asset_a,
        asset_b=asset_b,
        offset_us=-round(lag_s * US_PER_SECOND),
        drift_ppm=drift * 1e6,
        psr=coarse.psr,
        accepted=accepted,
    )
