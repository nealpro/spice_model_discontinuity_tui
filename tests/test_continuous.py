"""Stress tests for the robust detector against clean and faulted continuous signals.

Clean tests: smooth mathematical signals must produce zero false positives.
Injection tests: a step discontinuity injected at the midpoint must be detected.
"""

import io
import tempfile
import unittest
from pathlib import Path

import numpy as np

from spice_discontinuity import generate
from spice_discontinuity.inject import inject_step
from spice_cli import main

_CONFIG = str(Path(__file__).parent / "generated_data_config.yaml")


def _run(csv_path: str) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main([csv_path, "-c", _CONFIG], stdout=out, stderr=err)
    return code, out.getvalue()


class TestContinuousSignalsNoFalsePositives(unittest.TestCase):
    """Clean continuous signals must produce zero detections."""

    def _assert_clean(self, x: np.ndarray, y: np.ndarray) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signal.csv"
            generate.to_csv(path, x, y)
            code, output = _run(str(path))
        self.assertEqual(code, 0, msg=output)
        self.assertIn("No discontinuities found.", output)

    def test_polynomial_linear(self):
        x, y = generate.polynomial(200, (1.0, 2.0))
        self._assert_clean(x, y)

    def test_polynomial_quadratic(self):
        x, y = generate.polynomial(200, (0.0, 0.0, 1.0))
        self._assert_clean(x, y)

    def test_polynomial_cubic(self):
        x, y = generate.polynomial(200, (0.0, -1.0, 0.0, 1.0), x_range=(-1.0, 1.0))
        self._assert_clean(x, y)

    def test_sinusoid_low_freq(self):
        x, y = generate.sinusoid(200, amplitude=1.0, frequency=1.0)
        self._assert_clean(x, y)

    def test_sinusoid_high_freq(self):
        x, y = generate.sinusoid(500, amplitude=1.0, frequency=10.0)
        self._assert_clean(x, y)

    def test_exponential_slow(self):
        x, y = generate.exponential(200, rate=1.0)
        self._assert_clean(x, y)

    def test_exponential_fast(self):
        x, y = generate.exponential(200, rate=5.0)
        self._assert_clean(x, y)


class TestInjectedDiscontinuitiesDetected(unittest.TestCase):
    """A step injected at the midpoint must always be flagged."""

    def _assert_detected(self, x: np.ndarray, y: np.ndarray) -> None:
        # Scale magnitude to 50× the signal range so detection is signal-agnostic.
        magnitude = 50.0 * (float(y.max()) - float(y.min()) + 1.0)
        y_faulted = np.array(inject_step(y.tolist(), len(y) // 2, magnitude))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signal.csv"
            generate.to_csv(path, x, y_faulted)
            code, output = _run(str(path))
        self.assertEqual(code, 0, msg=output)
        self.assertNotIn("No discontinuities found.", output)

    def test_polynomial_linear_detected(self):
        x, y = generate.polynomial(200, (1.0, 2.0))
        self._assert_detected(x, y)

    def test_polynomial_quadratic_detected(self):
        x, y = generate.polynomial(200, (0.0, 0.0, 1.0))
        self._assert_detected(x, y)

    def test_polynomial_cubic_detected(self):
        x, y = generate.polynomial(200, (0.0, -1.0, 0.0, 1.0), x_range=(-1.0, 1.0))
        self._assert_detected(x, y)

    def test_sinusoid_low_freq_detected(self):
        x, y = generate.sinusoid(200, amplitude=1.0, frequency=1.0)
        self._assert_detected(x, y)

    def test_sinusoid_high_freq_detected(self):
        x, y = generate.sinusoid(500, amplitude=1.0, frequency=10.0)
        self._assert_detected(x, y)

    def test_exponential_slow_detected(self):
        x, y = generate.exponential(200, rate=1.0)
        self._assert_detected(x, y)

    def test_exponential_fast_detected(self):
        x, y = generate.exponential(200, rate=5.0)
        self._assert_detected(x, y)


if __name__ == "__main__":
    unittest.main()
