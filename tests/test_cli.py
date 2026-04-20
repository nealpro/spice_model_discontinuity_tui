import io
import tempfile
import unittest
from pathlib import Path

from spice_cli import main


class TestSpiceFindCli(unittest.TestCase):
    def test_file_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.csv"
            path.write_text("vout\n1.0\n1.1\n2.5\n", encoding="utf-8")

            out = io.StringIO()
            err = io.StringIO()
            code = main(
                ["--method", "simple", "-s", "1.0", str(path)],
                stdout=out,
                stderr=err,
            )

            self.assertEqual(code, 0)
            self.assertIn("Analyzed 1 numeric column(s).", out.getvalue())
            self.assertIn("vout: 1", out.getvalue())
            self.assertEqual("", err.getvalue())

    def test_stdin_input(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        stdin = io.StringIO("idrain\n0\n0.1\n2.3\n")

        code = main(
            ["--method", "simple", "-s", "2.0"],
            stdin=stdin,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 0)
        self.assertIn("idrain: 1", out.getvalue())
        self.assertEqual("", err.getvalue())

    def test_invalid_threshold(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        stdin = io.StringIO("v\n1\n2\n")

        code = main(
            ["--method", "simple", "-s", "0"],
            stdin=stdin,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 2)
        self.assertIn("must be greater than 0", err.getvalue())

    def test_empty_input_errors(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        stdin = io.StringIO("")

        code = main(
            ["--method", "simple", "-s", "1.0"],
            stdin=stdin,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 2)
        self.assertIn("no header row", err.getvalue())

    def test_robust_on_clean_data_reports_zero(self) -> None:
        """Clean quadratic data should produce no flags under the robust method."""
        out = io.StringIO()
        err = io.StringIO()
        lines = ["y"]
        for i in range(200):
            x = i / 200.0
            lines.append(f"{x * x:.6f}")
        stdin = io.StringIO("\n".join(lines) + "\n")

        code = main(
            ["--method", "robust"],
            stdin=stdin,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 0, msg=err.getvalue())
        self.assertIn("No discontinuities found.", out.getvalue())


if __name__ == "__main__":
    unittest.main()
