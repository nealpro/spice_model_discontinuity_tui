"""Command-line interface for SPICE discontinuity tools."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence, TextIO

from spice_discontinuity.find import Discontinuity, find_discontinuities


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spice-find",
        description="Find discontinuities in CSV numeric columns.",
    )
    parser.add_argument(
        "-s",
        "--sensitivity",
        type=float,
        required=True,
        help="Threshold for adjacent-point delta magnitude (must be > 0).",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="CSV input file path. Omit or use '-' to read from stdin.",
    )
    return parser


def _load_numeric_columns_from_stream(stream: TextIO) -> dict[str, list[float]]:
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise ValueError("CSV input has no header row.")

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
        raise ValueError("CSV input contains no numeric data.")
    return numeric_columns


def _analyze_columns(
    columns: dict[str, list[float]],
    threshold: float,
) -> dict[str, list[Discontinuity]]:
    return {
        column_name: find_discontinuities(values, threshold)
        for column_name, values in columns.items()
    }


def _write_summary(results: dict[str, list[Discontinuity]], output: TextIO) -> None:
    print(f"Analyzed {len(results)} numeric column(s).", file=output)

    total = sum(len(items) for items in results.values())
    if total == 0:
        print("No discontinuities found.", file=output)
        return

    print(f"Found {total} discontinuity/discontinuities.", file=output)
    for column_name, discontinuities in results.items():
        print(f"{column_name}: {len(discontinuities)}", file=output)
        for item in discontinuities:
            print(f"  index={item.index} delta={item.delta:.6g}", file=output)


def main(
    argv: Sequence[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    error_stream = stderr if stderr is not None else sys.stderr

    if args.sensitivity <= 0:
        print("error: -s/--sensitivity must be greater than 0.", file=error_stream)
        return 2

    try:
        if args.input and args.input != "-":
            with Path(args.input).open(encoding="utf-8", newline="") as handle:
                columns = _load_numeric_columns_from_stream(handle)
        else:
            is_tty = getattr(input_stream, "isatty", lambda: False)
            if is_tty():
                print(
                    "error: no input provided. Pass a file path or pipe CSV data on stdin.",
                    file=error_stream,
                )
                return 2
            columns = _load_numeric_columns_from_stream(input_stream)

        results = _analyze_columns(columns, args.sensitivity)
        _write_summary(results, output_stream)
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=error_stream)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
