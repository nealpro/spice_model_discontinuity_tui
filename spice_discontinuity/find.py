"""Discontinuity-finding utilities for SPICE simulation data.

Three detection methods are available:

- ``"simple"`` — absolute delta exceeds a raw threshold (``find_discontinuities``).
- ``"higher_order"`` — legacy second-derivative ratio score + raw threshold
  (``detect_discontinuities_higher_order`` + ``get_discontinuity_indices``).
- ``"robust"`` — scale-aware score with MAD-based threshold and peak
  prominence filtering (``detect_robust``). Recommended default; treats
  discontinuities as rare outliers and resists both flat-region score
  blow-up and clustered false positives.

Use ``detect(method, x, y, **params)`` to dispatch uniformly.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

_EPS = 1e-12
_MAD_TO_SIGMA = 1.4826  # scale factor that makes MAD a consistent estimator of σ for Gaussian data


@dataclass(frozen=True)
class Discontinuity:
    """Represents a detected discontinuity in a single numeric series."""

    index: int
    delta: float


@dataclass(frozen=True)
class DetectionResult:
    """Structured output of the method-dispatching ``detect`` entry point.

    Attributes:
        x: Independent axis aligned with ``score`` (length N-3 for the
            higher-order family; same grid for ``simple``).
        fda_2: Second derivative on the ``vgs_mid2`` grid (length N-2) for the
            higher-order family; empty for ``simple``.
        score: Per-point sensitivity score on the ``x`` grid.
        indices: Indices into ``score`` / ``x`` that were flagged.
        threshold: Final numeric cutoff applied to the score.
        method: ``"simple" | "higher_order" | "robust"``.
    """

    x: np.ndarray
    fda_2: np.ndarray
    score: np.ndarray
    indices: np.ndarray
    threshold: float
    method: str


def load_csv_numeric_columns(path: str | Path) -> dict[str, list[float]]:
    """Load numeric columns from a CSV file."""
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


def find_discontinuities(values: list[float], threshold: float) -> list[Discontinuity]:
    """Detect step discontinuities where adjacent delta exceeds threshold."""
    if threshold <= 0:
        raise ValueError("threshold must be positive.")
    if len(values) < 2:
        return []

    discontinuities: list[Discontinuity] = []
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        if abs(delta) >= threshold:
            discontinuities.append(Discontinuity(index=index, delta=delta))
    return discontinuities


def analyze_csv_discontinuities(
    path: str | Path, threshold: float = 1.0
) -> dict[str, list[Discontinuity]]:
    """Analyze all numeric CSV columns for discontinuities."""
    columns = load_csv_numeric_columns(path)
    return {
        column_name: find_discontinuities(values, threshold)
        for column_name, values in columns.items()
    }


def detect_discontinuities_higher_order(
    vgs: np.ndarray,
    ids: np.ndarray,
    threshold: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute a higher-order discontinuity score from SPICE V/I data.

    Returns (vgs_mid3, fda_2, final_score). The optional threshold argument is
    accepted for API symmetry but not applied here; use
    ``get_discontinuity_indices`` to threshold the score.
    """
    vgs = np.asarray(vgs, dtype=float)
    ids = np.asarray(ids, dtype=float)

    fda_1 = np.diff(ids) / np.diff(vgs)
    vgs_mid1 = (vgs[:-1] + vgs[1:]) / 2.0

    fda_2 = np.diff(fda_1) / np.diff(vgs_mid1)
    vgs_mid2 = (vgs_mid1[:-1] + vgs_mid1[1:]) / 2.0

    rpd = np.abs(np.diff(fda_2)) / (np.abs(fda_2[:-1]) + _EPS)
    final_score = rpd / np.diff(vgs_mid2)
    vgs_mid3 = vgs_mid2[1:]

    return vgs_mid3, fda_2, final_score


def get_discontinuity_indices(final_score: np.ndarray, threshold: float) -> np.ndarray:
    """Return indices of ``final_score`` that exceed ``threshold``."""
    return np.where(final_score > threshold)[0]


# ---------------------------------------------------------------------------
# Robust detector
# ---------------------------------------------------------------------------


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
    fda_1 = np.diff(y) / dx
    x_mid1 = (x[:-1] + x[1:]) / 2.0

    dx_mid1 = np.diff(x_mid1)
    fda_2 = np.diff(fda_1) / dx_mid1
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


# ---------------------------------------------------------------------------
# Method dispatch
# ---------------------------------------------------------------------------


def _detect_simple(x: np.ndarray, y: np.ndarray, *, threshold: float) -> DetectionResult:
    if threshold <= 0:
        raise ValueError("threshold must be positive for the 'simple' method.")
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    if y.size < 2:
        empty = np.empty(0)
        return DetectionResult(
            x=x, fda_2=empty, score=empty, indices=np.empty(0, dtype=int),
            threshold=threshold, method="simple",
        )
    deltas = np.abs(np.diff(y))
    # Align score with y[1:] so indices map back to the original sample index.
    indices = np.where(deltas >= threshold)[0] + 1
    return DetectionResult(
        x=x,
        fda_2=np.empty(0),
        score=np.concatenate(([0.0], deltas)),
        indices=indices,
        threshold=float(threshold),
        method="simple",
    )


def _detect_higher_order(
    x: np.ndarray, y: np.ndarray, *, threshold: float
) -> DetectionResult:
    x_mid3, fda_2, score = detect_discontinuities_higher_order(x, y)
    if threshold <= 0:
        raise ValueError("threshold must be positive for the 'higher_order' method.")
    indices = get_discontinuity_indices(score, threshold)
    return DetectionResult(
        x=x_mid3,
        fda_2=fda_2,
        score=score,
        indices=indices,
        threshold=float(threshold),
        method="higher_order",
    )


def detect(method: str, x: np.ndarray, y: np.ndarray, **params) -> DetectionResult:
    """Dispatch to the named detection method.

    Accepted methods and parameters:
        - ``"simple"``: ``threshold`` (required, > 0)
        - ``"higher_order"``: ``threshold`` (required, > 0)
        - ``"robust"``: ``sigma`` (default 8.0), ``min_prominence_sigma``
          (default 3.0), ``min_separation`` (default 3)
    """
    if method == "simple":
        return _detect_simple(x, y, **params)
    if method == "higher_order":
        return _detect_higher_order(x, y, **params)
    if method == "robust":
        return detect_robust(x, y, **params)
    raise ValueError(
        f"unknown method '{method}' (expected 'simple', 'higher_order', or 'robust')"
    )
