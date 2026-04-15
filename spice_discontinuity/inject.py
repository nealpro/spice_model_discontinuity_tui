"""Discontinuity injection utilities for smooth simulation data."""

from __future__ import annotations

import random


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
