"""Robust discontinuity detection for SPICE simulation CSV data."""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

_EPS = 1e-12
_MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class DetectionResult:
    x: np.ndarray
    fda_2: np.ndarray
    score: np.ndarray
    indices: np.ndarray
    threshold: float
    method: str


def load_csv_numeric_columns(
    path: str | Path,
    ignore_columns: list[str] | None = None,
) -> dict[str, list[float]]:
    """Load numeric columns from a CSV file, skipping any in ignore_columns."""
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

    if ignore_columns:
        numeric_columns = {
            name: vals
            for name, vals in numeric_columns.items()
            if name not in ignore_columns
        }

    return numeric_columns


def _mad(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    return float(np.median(np.abs(finite - np.median(finite))))


def _find_anomalous_row(y: np.ndarray, center: int, half_window: int = 2) -> int:
    """Find the most deviant row in a window around center."""
    start = max(1, center - half_window)
    end = min(len(y) - 2, center + half_window)
    best, best_dev = start, -1.0
    for j in range(start, end + 1):
        dev = abs(y[j] - y[j - 1]) + abs(y[j] - y[j + 1])
        if dev > best_dev:
            best_dev = dev
            best = j
    return best


def _local_mad(values: np.ndarray, half_window: int) -> np.ndarray:
    """Per-point MAD using a leave-one-out sliding window.

    For each point i, MAD is computed from the surrounding window
    excluding point i itself. This prevents a real discontinuity from
    inflating its own local baseline and suppressing its z-score.
    """
    n = len(values)
    result = np.empty(n)
    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        window = np.concatenate([values[start:i], values[i + 1:end]])
        finite = window[np.isfinite(window)]
        if finite.size == 0:
            result[i] = _EPS
        else:
            mad = float(np.median(np.abs(finite - np.median(finite))))
            result[i] = mad if mad > 0 else _EPS
    return result


def score_series(
    x: np.ndarray, y: np.ndarray, half_window: int = 10
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Local MAD-z-score of the step in the second derivative, normalized by Δx.

    Uses a per-point leave-one-out sliding window MAD so the baseline
    adapts to local signal behavior rather than being dominated by any
    single region of the curve.
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

    local_sigma = _MAD_TO_SIGMA * _local_mad(normalized_jump, half_window)
    score = np.abs(normalized_jump) / local_sigma
    x_mid3 = x_mid2[1:]
    return x_mid3, fda_2, score


def detect_robust(
    x: np.ndarray,
    y: np.ndarray,
    *,
    sigma: float = 50.0,
    min_prominence: float = 20.0,
    min_separation: int = 3,
) -> DetectionResult:
    """Prominence-filtered outlier detection in the MAD-z-score space."""
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
