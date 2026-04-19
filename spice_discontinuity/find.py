"""Discontinuity-finding utilities for SPICE simulation data."""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Discontinuity:
    """Represents a detected discontinuity in a single numeric series."""

    index: int
    delta: float


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
                    # Ignore non-numeric values in this initial scaffold.
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

    rpd = np.abs(np.diff(fda_2)) / (np.abs(fda_2[:-1]) + 1e-12)
    final_score = rpd / np.diff(vgs_mid2)
    vgs_mid3 = vgs_mid2[1:]

    return vgs_mid3, fda_2, final_score


def get_discontinuity_indices(final_score: np.ndarray, threshold: float) -> np.ndarray:
    """Return indices of ``final_score`` that exceed ``threshold``."""
    return np.where(final_score > threshold)[0]
