"""Discontinuity injection utilities for smooth simulation data."""

import random

import numpy as np
import pandas as pd


def inject_step(values: list[float], index: int, magnitude: float) -> list[float]:
    """Inject a persistent step change starting at index."""
    if not 0 <= index < len(values):
        raise IndexError("index out of range.")
    output = list(values)
    for position in range(index, len(output)):
        output[position] += magnitude
    return output


def inject_spike(values: list[float], index: int, magnitude: float) -> list[float]:
    """Inject a single-point spike at index."""
    if not 0 <= index < len(values):
        raise IndexError("index out of range.")
    output = list(values)
    output[index] += magnitude
    return output


def inject_random_spikes(
    values: list[float],
    count: int,
    magnitude: float,
    seed: int | None = None,
) -> list[float]:
    """Inject random spikes for synthetic discontinuity testing."""
    if count < 0:
        raise ValueError("count must be non-negative.")
    if count > len(values):
        raise ValueError("count cannot exceed number of values.")

    rng = random.Random(seed)
    output = list(values)
    for index in rng.sample(range(len(values)), count):
        output[index] += magnitude
    return output


def inject_faults(df: pd.DataFrame, fault_percentage: float = 0.01) -> pd.DataFrame:
    """Inject synthetic faults into the ``Id`` column of a DataFrame.

    Cycles three fault types across evenly spaced sample indices:
    abrupt jump (×5.0), additive noise (+1e-3), and clipping (floor at 0.0001).
    Returns a modified copy; the input DataFrame is not mutated.
    """
    if "Id" not in df.columns:
        raise KeyError("DataFrame must contain an 'Id' column.")
    if not 0.0 <= fault_percentage <= 1.0:
        raise ValueError("fault_percentage must be between 0 and 1.")

    result = df.copy()
    n = len(result)
    if n == 0:
        return result

    n_faults = max(1, int(n * fault_percentage))
    indices = np.linspace(0, n - 1, num=n_faults, dtype=int)

    id_values = result["Id"].to_numpy(copy=True)
    for position, idx in enumerate(indices):
        fault_type = position % 3
        if fault_type == 0:
            id_values[idx] *= 5.0
        elif fault_type == 1:
            id_values[idx] += 1e-3
        else:
            id_values[idx] = max(id_values[idx], 0.0001)

    result["Id"] = id_values
    return result
