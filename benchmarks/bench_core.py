"""pyperf benchmarks for the core spice_discontinuity functions.

Run with:
    python benchmarks/bench_core.py --fast -o benchmarks/results.json
"""

import tempfile
from pathlib import Path

import numpy as np
import pyperf

from spice_discontinuity import find, generate
from spice_discontinuity.inject import inject_random_spikes, inject_step

# ---------------------------------------------------------------------------
# Shared fixtures (built once, reused across benchmarks)
# ---------------------------------------------------------------------------

def _make(n: int):
    x = np.linspace(0.0, 1.0, n)
    y = np.sin(2.0 * np.pi * 3.0 * x)
    return x, y, y.tolist()


_x1k,   _y1k,   _v1k   = _make(1_000)
_x10k,  _y10k,  _v10k  = _make(10_000)
_x100k, _y100k, _v100k = _make(100_000)

_coeffs3  = (1.0, 2.0, 3.0)
_coeffs10 = tuple(float(i) for i in range(10))

# ---------------------------------------------------------------------------
# Benchmark functions
# ---------------------------------------------------------------------------

def bench_poly_N1k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.polynomial(1_000, _coeffs3)
    return pyperf.perf_counter() - t0


def bench_poly_N10k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.polynomial(10_000, _coeffs3)
    return pyperf.perf_counter() - t0


def bench_poly_N100k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.polynomial(100_000, _coeffs3)
    return pyperf.perf_counter() - t0


def bench_poly_coeff10_N10k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.polynomial(10_000, _coeffs10)
    return pyperf.perf_counter() - t0


def bench_sinusoid_N1k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.sinusoid(1_000)
    return pyperf.perf_counter() - t0


def bench_sinusoid_N10k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.sinusoid(10_000)
    return pyperf.perf_counter() - t0


def bench_sinusoid_N100k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.sinusoid(100_000)
    return pyperf.perf_counter() - t0


def bench_exponential_N1k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.exponential(1_000)
    return pyperf.perf_counter() - t0


def bench_exponential_N10k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.exponential(10_000)
    return pyperf.perf_counter() - t0


def bench_exponential_N100k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        generate.exponential(100_000)
    return pyperf.perf_counter() - t0


def bench_to_csv_N1k(loops):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "out.csv"
        t0 = pyperf.perf_counter()
        for _ in range(loops):
            generate.to_csv(p, _x1k, _y1k)
        return pyperf.perf_counter() - t0


def bench_to_csv_N10k(loops):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "out.csv"
        t0 = pyperf.perf_counter()
        for _ in range(loops):
            generate.to_csv(p, _x10k, _y10k)
        return pyperf.perf_counter() - t0


def bench_to_csv_N100k(loops):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "out.csv"
        t0 = pyperf.perf_counter()
        for _ in range(loops):
            generate.to_csv(p, _x100k, _y100k)
        return pyperf.perf_counter() - t0


def bench_detect_robust_N1k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        find.detect_robust(_x1k, _y1k)
    return pyperf.perf_counter() - t0


def bench_detect_robust_N10k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        find.detect_robust(_x10k, _y10k)
    return pyperf.perf_counter() - t0


def bench_detect_robust_N100k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        find.detect_robust(_x100k, _y100k)
    return pyperf.perf_counter() - t0


def bench_inject_step_N1k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        inject_step(_v1k, 500, 1.0)
    return pyperf.perf_counter() - t0


def bench_inject_step_N10k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        inject_step(_v10k, 5_000, 1.0)
    return pyperf.perf_counter() - t0


def bench_inject_step_N100k(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        inject_step(_v100k, 50_000, 1.0)
    return pyperf.perf_counter() - t0


def bench_inject_random_spikes_N1k_K10(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        inject_random_spikes(_v1k, 10, 1.0, seed=42)
    return pyperf.perf_counter() - t0


def bench_inject_random_spikes_N10k_K100(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        inject_random_spikes(_v10k, 100, 1.0, seed=42)
    return pyperf.perf_counter() - t0


def bench_inject_random_spikes_N100k_K100(loops):
    t0 = pyperf.perf_counter()
    for _ in range(loops):
        inject_random_spikes(_v100k, 100, 1.0, seed=42)
    return pyperf.perf_counter() - t0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

BENCHMARKS = [
    ("generate_polynomial_N1k",            bench_poly_N1k),
    ("generate_polynomial_N10k",           bench_poly_N10k),
    ("generate_polynomial_N100k",          bench_poly_N100k),
    ("generate_polynomial_coeff10_N10k",   bench_poly_coeff10_N10k),
    ("generate_sinusoid_N1k",              bench_sinusoid_N1k),
    ("generate_sinusoid_N10k",             bench_sinusoid_N10k),
    ("generate_sinusoid_N100k",            bench_sinusoid_N100k),
    ("generate_exponential_N1k",           bench_exponential_N1k),
    ("generate_exponential_N10k",          bench_exponential_N10k),
    ("generate_exponential_N100k",         bench_exponential_N100k),
    ("generate_to_csv_N1k",               bench_to_csv_N1k),
    ("generate_to_csv_N10k",              bench_to_csv_N10k),
    ("generate_to_csv_N100k",             bench_to_csv_N100k),
    ("find_detect_robust_N1k",            bench_detect_robust_N1k),
    ("find_detect_robust_N10k",           bench_detect_robust_N10k),
    ("find_detect_robust_N100k",          bench_detect_robust_N100k),
    ("inject_step_N1k",                   bench_inject_step_N1k),
    ("inject_step_N10k",                  bench_inject_step_N10k),
    ("inject_step_N100k",                 bench_inject_step_N100k),
    ("inject_random_spikes_N1k_K10",      bench_inject_random_spikes_N1k_K10),
    ("inject_random_spikes_N10k_K100",    bench_inject_random_spikes_N10k_K100),
    ("inject_random_spikes_N100k_K100",   bench_inject_random_spikes_N100k_K100),
]

if __name__ == "__main__":
    runner = pyperf.Runner()
    for name, func in BENCHMARKS:
        runner.bench_time_func(name, func)
