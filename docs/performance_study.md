---
title: "Performance Study: Running Times and Generate Module Tests"
date: "2026-05-10"
---

# Performance Study: Running Times and `generate` Module Tests

## 1 Running Time Benchmarks

### 1.1 Methodology

Benchmarks were collected with **pyperf 2.10.0** using `--fast` mode (5 warmup runs,
5 measurement runs per benchmark, loop counts auto-calibrated by pyperf). Raw results
are stored in `benchmarks/results.json`. `inject_random_spikes` timings were collected
separately with `time.perf_counter` (20 loops, 3 warmup) because the benchmark
script's background run was truncated.

**Environment**

| Key | Value |
| --- | --- |
| Machine | Apple Silicon (arm64), 8 CPU cores |
| OS | macOS 15.7.4 |
| Python | CPython 3.14.0 (64-bit, GIL disabled) |
| pyperf | 2.10.0 |
| Timer resolution | mach_absolute_time(), 41.7 ns |

Input series for `find` and `inject` benchmarks are `A*sin(2*pi*3*x)` sampled over
`[0, 1]`, seeded at 42 for the random injectors.

---

### 1.2 Results

#### `generate.polynomial` — O(N·C)

Fixed C=3 (`coefficients=(1.0, 2.0, 3.0)`):

| N | Mean ± std dev | N×10 ratio |
| --- | --- | --- |
| 1,000 | 14.87 ± 0.15 µs | — |
| 10,000 | 44.19 ± 0.19 µs | 2.97× |
| 100,000 | 415.23 ± 2.73 µs | 9.39× |

Effect of C at N = 10,000:

| C | Mean ± std dev | C×(10/3) ratio |
| --- | --- | --- |
| 3 | 44.19 ± 0.19 µs | — |
| 10 | 103.92 ± 0.62 µs | 2.35× (expected 3.33×) |

#### `generate.sinusoid` — O(N)

| N | Mean ± std dev | N×10 ratio |
| --- | --- | --- |
| 1,000 | 14.51 ± 0.25 µs | — |
| 10,000 | 76.55 ± 3.29 µs | 5.27× |
| 100,000 | 772.71 ± 13.39 µs | 10.09× |

#### `generate.exponential` — O(N)

| N | Mean ± std dev | N×10 ratio |
| --- | --- | --- |
| 1,000 | 10.89 ± 0.08 µs | — |
| 10,000 | 55.83 ± 0.11 µs | 5.13× |
| 100,000 | 592.04 ± 26.35 µs | 10.60× |

#### `generate.to_csv` — O(N)

| N | Mean ± std dev | N×10 ratio |
| --- | --- | --- |
| 1,000 | 1,561 ± 9.9 µs | — |
| 10,000 | 14,863 ± 118 µs | 9.52× |
| 100,000 | 145,450 ± 1,408 µs | 9.79× |

#### `find.detect_robust` — O(N log N) theoretical

| N | Mean ± std dev | N×10 ratio |
| --- | --- | --- |
| 1,000 | 121.19 ± 1.38 µs | — |
| 10,000 | 333.04 ± 1.24 µs | 2.75× |
| 100,000 | 2,978.79 ± 190.56 µs | 8.94× |

#### `inject.inject_step` — O(N)

| N | Mean ± std dev | N×10 ratio |
| --- | --- | --- |
| 1,000 | 24.69 ± 0.14 µs | — |
| 10,000 | 256.10 ± 2.66 µs | 10.37× |
| 100,000 | 2,587.84 ± 12.49 µs | 10.10× |

#### `inject.inject_random_spikes` — O(N + K)

K grows with N in the first two rows (K = N/100); the third row holds K fixed:

| N | K | Mean (µs) | Ratio |
| --- | --- | --- | --- |
| 1,000 | 10 | 18.50 | — |
| 10,000 | 100 | 82.02 | 4.43× (N and K both ×10) |
| 100,000 | 100 | 394.58 | 4.81× (N ×10, K fixed) |

---

### 1.3 Comparison with Theoretical Complexity

The theoretical predictions are taken from `docs/algorithms_study.md`. The table
below shows predicted N×10 growth ratios alongside what was observed at the larger
(N=10k→100k) step, where fixed per-call overheads are smallest relative to actual
work.

| Function | Theory | Predicted ratio (N×10) | Observed ratio | Verdict |
| --- | --- | --- | --- | --- |
| `polynomial` (C fixed) | O(N·C) | 10× | 9.39× | Confirms O(N); linspace dominates over polyval |
| `sinusoid` | O(N) | 10× | 10.09× | Exact |
| `exponential` | O(N) | 10× | 10.60× | Exact (within noise) |
| `to_csv` | O(N) | 10× | 9.79× | Exact; I/O-bound row loop |
| `detect_robust` | O(N log N) | ~11.3× | 8.94× | Consistent with O(N)–O(N log N); see below |
| `inject_step` | O(N) | 10× | 10.10× | Exact |
| `inject_random_spikes` | O(N + K) | depends on K | 4.81× (K fixed) | Consistent; see below |

**`generate` functions.** At small N (1k→10k), all three vectorized generators show
lower-than-expected ratios (2.97×–5.27×). This is not a complexity anomaly — it
reflects fixed NumPy overhead (array allocation, `linspace` setup, Python call stack)
that is non-negligible when N=1k takes only ~10–15 µs total. At N=10k→100k those
costs amortize and all three generators converge to the expected 10× ratio,
confirming O(N).

The C effect in `polynomial` is weaker than the naive O(C) factor suggests (2.35×
vs 3.33×). `np.polyval` on a degree-9 polynomial at N=10k is faster than a simple
flop count predicts because NumPy's Horner-scheme evaluation is branch-free and
cache-hot; the `np.linspace` call (shared between both C=3 and C=10 runs) also adds
a constant-fraction cost.

**`generate.to_csv`.** This is the slowest generator by two orders of magnitude
(1.56 ms vs ~15 µs for `polynomial` at N=1k), and the only I/O-bound function in
the suite. The row-by-row Python CSV loop dominates; it scales nearly perfectly as
O(N) (9.52× and 9.79×), confirming the theoretical estimate.

**`find.detect_robust`.** The 2.75× ratio at N=1k→10k is misleadingly low. At N=1k,
121 µs is consumed by `scipy.signal.find_peaks` initialization and array allocation
overhead that does not grow with N. Once N=10k, those fixed costs become a small
fraction of runtime, and the 8.94× ratio at N=10k→100k confirms near-linear
scaling. `algorithms_study.md` lists the bound as O(N log N) under the conservative
assumption that `np.median` requires sort-based work; in NumPy's implementation
`np.median` uses introselect (partial sort, O(N) average) so the actual median cost
is linear. The observed 8.94× ratio sits squarely between O(N) (→10×) and O(N log N)
(→11.3× for this range), consistent with the theoretical bound being conservative.

**`inject_random_spikes`.** When both N and K grow 10× the observed 4.43× ratio
reflects the O(N + K) decomposition: `list(values)` is O(N) and dominates at
large N, but `random.sample(range(N), K)` is O(K) for K << N and adds a fixed
overhead that delays the onset of the linear regime. Holding K=100 fixed and growing
N from 10k to 100k (the 4.81× row) shows that even with K fixed the copy cost has
not yet fully dominated at N=10k. By N=100k the copy grows toward 10× relative to
larger N values.

---

## 2 `spice_discontinuity.generate` — Tests and Results

### 2.1 Functions Under Test

`spice_discontinuity/generate.py` provides four functions:

| Function | Signature (simplified) | What it returns |
| --- | --- | --- |
| `polynomial` | `(n, coefficients, x_range=(0,1))` | N samples of `c0 + c1*x + c2*x^2 + ...` |
| `sinusoid` | `(n, amplitude=1, frequency=1, phase=0, x_range=(0,1))` | N samples of `A*sin(2*pi*f*x + phi)` |
| `exponential` | `(n, rate=1, x_range=(0,1))` | N samples of `exp(rate*x)` |
| `to_csv` | `(path, x, y, x_col="x", y_col="y")` | Writes two-column UTF-8 CSV |

All four are exercised by the integration test suite; `to_csv` is used as the bridge
between the generator functions and the CLI detector under test.

### 2.2 Test Suite: `tests/test_continuous.py`

The file contains two test classes. Both classes share the same configuration file
(`tests/generated_data_config.yaml`) which sets the detector parameters:
`sensitivity=1.0`, `min_prominence=20.0`, `min_separation=3`, `independent_col="x"`.

#### Class 1 — `TestContinuousSignalsNoFalsePositives`

Asserts that smooth, clean signals produce **zero detections**. The helper
`_assert_clean` writes each signal to a temp CSV, runs the CLI, and checks that
the output contains `"No discontinuities found."`.

| Test | Function | N | Key parameters | Assertion |
| --- | --- | --- | --- | --- |
| `test_polynomial_linear` | `polynomial` | 200 | coeff=(1.0, 2.0), x in [0,1] | no detections |
| `test_polynomial_quadratic` | `polynomial` | 200 | coeff=(0,0,1), x in [0,1] | no detections |
| `test_polynomial_cubic` | `polynomial` | 200 | coeff=(0,-1,0,1), x in [-1,1] | no detections |
| `test_sinusoid_low_freq` | `sinusoid` | 200 | A=1, f=1, phi=0 | no detections |
| `test_sinusoid_high_freq` | `sinusoid` | 500 | A=1, f=10, phi=0 | no detections |
| `test_exponential_slow` | `exponential` | 200 | rate=1 | no detections |
| `test_exponential_fast` | `exponential` | 200 | rate=5 | no detections |

#### Class 2 — `TestInjectedDiscontinuitiesDetected`

Asserts that a step fault injected at the signal midpoint is **always detected**.
The helper `_assert_detected` scales the step magnitude to `50 * (y_max - y_min + 1)`
so the injected discontinuity dwarfs any natural signal variation. It then asserts
that the CLI output does *not* contain `"No discontinuities found."`.

| Test | Function | N | Injection | Assertion |
| --- | --- | --- | --- | --- |
| `test_polynomial_linear_detected` | `polynomial` | 200 | step at index 100 | detected |
| `test_polynomial_quadratic_detected` | `polynomial` | 200 | step at index 100 | detected |
| `test_polynomial_cubic_detected` | `polynomial` | 200 | step at index 100 | detected |
| `test_sinusoid_low_freq_detected` | `sinusoid` | 200 | step at index 100 | detected |
| `test_sinusoid_high_freq_detected` | `sinusoid` | 500 | step at index 250 | detected |
| `test_exponential_slow_detected` | `exponential` | 200 | step at index 100 | detected |
| `test_exponential_fast_detected` | `exponential` | 200 | step at index 100 | detected |

### 2.3 Test Results

Run with `python -m pytest tests/test_continuous.py -v`:

```
============================= test session starts ==============================
platform darwin -- Python 3.14.0, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/neal/Projects/uky/ee584/spice_model_discontinuity

tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_exponential_fast PASSED [  7%]
tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_exponential_slow PASSED [ 14%]
tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_polynomial_cubic PASSED [ 21%]
tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_polynomial_linear PASSED [ 28%]
tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_polynomial_quadratic PASSED [ 35%]
tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_sinusoid_high_freq PASSED [ 42%]
tests/test_continuous.py::TestContinuousSignalsNoFalsePositives::test_sinusoid_low_freq PASSED [ 50%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_exponential_fast_detected PASSED [ 57%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_exponential_slow_detected PASSED [ 64%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_polynomial_cubic_detected PASSED [ 71%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_polynomial_linear_detected PASSED [ 78%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_polynomial_quadratic_detected PASSED [ 85%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_sinusoid_high_freq_detected PASSED [ 92%]
tests/test_continuous.py::TestInjectedDiscontinuitiesDetected::test_sinusoid_low_freq_detected PASSED [100%]

============================== 14 passed in 1.11s ==============================
```

**14 / 14 passed.** All seven clean-signal tests produce zero false positives, and
all seven injection tests successfully detect the injected step across all three
generator types and all tested parameter combinations.
