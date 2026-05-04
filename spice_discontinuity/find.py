"""Robust discontinuity-finding utilities for SPICE simulation data.

This module only exposes the MAD-normalized robust detector.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

_EPS = 1e-12
_MAD_TO_SIGMA = 1.4826  # scale factor that makes MAD a consistent estimator of σ for Gaussian data


@dataclass(frozen=True)
class DetectionResult:
    """Structured output of the robust ``detect`` entry point.

    Attributes:
        x: Independent axis aligned with ``score`` (length N-3).
        fda_2: Second derivative on the midpoint grid (length N-2).
        score: Per-point robust sensitivity score on the ``x`` grid.
        indices: Indices into ``score`` / ``x`` that were flagged.
        threshold: Final numeric cutoff applied to the score.
        method: Always ``"robust"``.
    """

    x: np.ndarray
    fda_2: np.ndarray
    score: np.ndarray
    indices: np.ndarray
    threshold: float
    method: str


def load_csv_numeric_columns(path: str | Path) -> dict[str, list[float]]:
    """Load numeric columns from a CSV file.

    A column is included if at least one cell parses as float; non-parseable
    cells within a numeric column are silently skipped.

    Parameters
    ----------
    path:
        Path to a UTF-8 CSV file with a header row.

    Returns
    -------
    dict
        ``{column_name: [float, ...]}`` for every column containing at least
        one parseable float value.

    Raises
    ------
    ValueError
        If the file has no header row or contains no numeric data.
    OSError
        If the file cannot be opened.
    """
    source = Path(path)
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row.")

        columns: dict[str, list[float]] = {name: [] for name in reader.fieldnames}
        for row in reader:
            for name in reader.fieldnames:
                raw = (row.get(name) or "").strip()
                if not raw:
                    continue
                try:
                    columns[name].append(float(raw))
                except ValueError:
                    continue

    numeric_columns = {name: values for name, values in columns.items() if values}
    if not numeric_columns:
        raise ValueError("CSV contains no numeric data.")
    return numeric_columns


def score_series(
    x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MAD-z-score of the step in the second derivative, normalized by Δx.

    For smooth data ``Δfda_2 / Δx`` fluctuates around zero with a scale set
    by genuine curvature evolution (e.g. FET threshold transition). A sharp
    discontinuity in ``y`` produces a single large bump in that series that
    dwarfs the baseline. Converting to a MAD-based z-score gives a unitless
    sensitivity number where:

    - baseline fluctuations (including threshold-region curvature changes on
      a healthy model) typically stay below ``~20``;
    - real SPICE discontinuities produce ``|z|`` in the hundreds or more.

    ``score_k = |Δfda_2_k / Δx_mid2_k| / (1.4826 * MAD(Δfda_2 / Δx_mid2))``

    Returns ``(x_mid3, fda_2, score)`` with lengths ``N-3, N-2, N-3``.
    Raises ``ValueError`` if ``len(x) < 4``.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 4 or y.size < 4:
        raise ValueError("score_series needs at least 4 samples.")
    if x.shape != y.shape:
        raise ValueError("x and y must have the same shape.")

    dx = np.diff(x)
    fda_1 = np.diff(y) / np.where(np.abs(dx) < _EPS, _EPS, dx)
    x_mid1 = (x[:-1] + x[1:]) / 2.0

    dx_mid1 = np.diff(x_mid1)
    fda_2 = np.diff(fda_1) / np.where(np.abs(dx_mid1) < _EPS, _EPS, dx_mid1)
    x_mid2 = (x_mid1[:-1] + x_mid1[1:]) / 2.0

    dx_mid2 = np.diff(x_mid2)
    normalized_jump = np.diff(fda_2) / np.where(np.abs(dx_mid2) < _EPS, _EPS, dx_mid2)

    sigma_mad = _MAD_TO_SIGMA * _mad(normalized_jump)
    if sigma_mad <= 0:
        sigma_mad = _EPS

    score = np.abs(normalized_jump) / sigma_mad
    x_mid3 = x_mid2[1:]
    return x_mid3, fda_2, score


def _mad(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    return float(np.median(np.abs(finite - np.median(finite))))


def detect_robust(
    x: np.ndarray,
    y: np.ndarray,
    *,
    sigma: float = 50.0,
    min_prominence: float = 20.0,
    min_separation: int = 3,
) -> DetectionResult:
    """Prominence-filtered outlier detection in the MAD-z-score space.

    ``score_series`` already returns a MAD-z-score, so ``sigma`` is a direct
    "z-threshold". Healthy SPICE transfer curves (including sharp FET
    threshold transitions) produce baseline z-scores well under 20; genuine
    discontinuities from a broken model produce values in the hundreds or
    more. The default ``sigma=50`` reflects that gap.

    Pipeline:
        1. ``score_series`` yields the MAD-z-score.
        2. ``scipy.signal.find_peaks`` with ``height=sigma``,
           ``prominence=min_prominence``, and ``distance=min_separation``.
           Prominence rejects clustered false positives; distance prevents
           consecutive-index bursts.

    A real discontinuity must rise *and fall* in z-space, so it is always
    a peak. Plateaus are ignored.

    Parameters
    ----------
    x:
        Independent axis (e.g. gate voltage), length N >= 4.
    y:
        Dependent axis (e.g. drain current), length N >= 4.
    sigma:
        Minimum MAD-z-score height for a peak to be flagged. Default 50.0.
    min_prominence:
        Minimum peak prominence above surrounding valleys. Default 20.0.
    min_separation:
        Minimum index distance between flagged peaks. Default 3.

    Returns
    -------
    DetectionResult
        Structured result with ``x``, ``fda_2``, ``score``, ``indices``,
        ``threshold`` (= ``sigma``), and ``method="robust"``.

    Raises
    ------
    ValueError
        If ``len(x) < 4`` (propagated from ``score_series``).
    """
    x_mid3, fda_2, score = score_series(x, y)

    finite = np.isfinite(score)
    if not finite.any():
        return DetectionResult(
            x=x_mid3,
            fda_2=fda_2,
            score=score,
            indices=np.empty(0, dtype=int),
            threshold=float(sigma),
            method="robust",
        )

    safe_score = np.where(finite, score, -np.inf)
    peaks, _ = find_peaks(
        safe_score,
        height=float(sigma),
        prominence=float(min_prominence) if min_prominence > 0 else None,
        distance=max(1, int(min_separation)),
    )

    return DetectionResult(
        x=x_mid3,
        fda_2=fda_2,
        score=score,
        indices=np.asarray(peaks, dtype=int),
        threshold=float(sigma),
        method="robust",
    )


def detect(
    x: np.ndarray,
    y: np.ndarray,
    *,
    sigma: float = 50.0,
    min_prominence: float = 20.0,
    min_separation: int = 3,
) -> DetectionResult:
    """Detect discontinuities using the robust detector.

    Parameters
    ----------
    x:
        Independent axis array (e.g. gate voltage), length N >= 4.
    y:
        Dependent axis array (e.g. drain current), length N >= 4.
    sigma:
        Minimum MAD-z-score height for a peak to be flagged.
    min_prominence:
        Minimum peak prominence above surrounding valleys.
    min_separation:
        Minimum index distance between flagged peaks.
    """
    return detect_robust(
        x,
        y,
        sigma=sigma,
        min_prominence=min_prominence,
        min_separation=min_separation,
    )
