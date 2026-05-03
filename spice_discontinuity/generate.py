"""Generate continuous signal data for stress-testing discontinuity detection."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def polynomial(
    n: int,
    coefficients: tuple[float, ...],
    x_range: tuple[float, float] = (0.0, 1.0),
) -> tuple[np.ndarray, np.ndarray]:
    """Return n samples of c0 + c1·x + c2·x² + … over x_range."""
    x = np.linspace(x_range[0], x_range[1], n)
    y = np.polyval(list(reversed(coefficients)), x)
    return x, y


def sinusoid(
    n: int,
    amplitude: float = 1.0,
    frequency: float = 1.0,
    phase: float = 0.0,
    x_range: tuple[float, float] = (0.0, 1.0),
) -> tuple[np.ndarray, np.ndarray]:
    """Return n samples of A·sin(2π·f·x + φ) over x_range."""
    x = np.linspace(x_range[0], x_range[1], n)
    y = amplitude * np.sin(2.0 * np.pi * frequency * x + phase)
    return x, y


def exponential(
    n: int,
    rate: float = 1.0,
    x_range: tuple[float, float] = (0.0, 1.0),
) -> tuple[np.ndarray, np.ndarray]:
    """Return n samples of e^(rate·x) over x_range."""
    x = np.linspace(x_range[0], x_range[1], n)
    y = np.exp(rate * x)
    return x, y


def to_csv(
    path: str | Path,
    x: np.ndarray,
    y: np.ndarray,
    x_col: str = "x",
    y_col: str = "y",
) -> None:
    """Write (x, y) arrays to a two-column CSV."""
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([x_col, y_col])
        for xi, yi in zip(x, y):
            writer.writerow([f"{xi:.10g}", f"{yi:.10g}"])
