"""Command-line interface for SPICE discontinuity tools."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import yaml
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence, TextIO

import numpy as np

from spice_discontinuity.find import DetectionResult, detect as find_detect
from spice_discontinuity.inject import inject_random_spikes

_DEFAULT_CONFIG_PATH = Path("~/.config/discontinuity_finder/config.yaml").expanduser()

_HELP_FORMAT_TOPICS: dict[str, str] = {
    "config": """\
CONFIG FILE FORMAT
==================
Default path: ~/.config/discontinuity_finder/config.yaml
Override with: discont-finder -c /path/to/config.yaml
Format: YAML

Sections recognized:

  io:
    output_dir: "spice_cli_output"   # base directory for results.csv and plots
    files: ["data/signal.csv"]       # fallback file(s) when stdin is a terminal

  detection:
    sensitivity: 50.0               # robust z-score sigma threshold
    min_prominence: 20.0            # robust only: minimum peak prominence
    min_separation: 3               # robust only: minimum index gap between peaks

  analysis:
    independent_col: "gate_v"       # CSV column to use as the x-axis
    group_by: "vsb"                 # CSV column to partition rows before detection

  plots:                             # presence of this section enables plotting
    output_dir: "my_output"         # plots land in <output_dir>/PLOTS/
    figsize: [16, 9]
    dpi: 200
    ylabel: "Current (A)"           # default: y column name
    unit_scale: 1.0
    xlabel: "Voltage (V)"           # default: x column name
    xlim: [0.0, 1.8]
    tick_step: 0.2
    title_prefix: "My Signal"
    grouping:
      column: "vsb"                 # CSV column used to label curves
      min: 0.0
      max: 1.5
      step: 0.1
      skip: []
      label_template: "vsb = {value:.2f} V"

See config_examples/config.yaml for a fully annotated example.\
""",
    "csv": """\
CSV INPUT FORMAT
================
A standard comma-separated file with a header row.

Rules:
  - First row must be the header (column names).
  - All other rows are data. Rows with non-parseable values in a column
    are skipped for that column; other columns are unaffected.
  - A column is treated as numeric if at least one non-empty cell
    parses as float.
  - Column names may contain any characters, including spaces, parentheses,
    and special symbols (LTspice-style names are fully supported).

Minimal example:
  gate_v,drain_i,vsb
  0.0,1.23e-9,0.0
  0.1,5.67e-9,0.0
  0.2,2.10e-8,0.5

Reading from a file:
  discont-finder data.csv

Reading from stdin:
  cat data.csv | discont-finder -
  discont-finder -          (then paste and press Ctrl-D)\
""",
    "plots": """\
PLOTS FORMAT
============
Plots are generated when either:
  - The -p/--plot flag is passed, OR
  - The plots section is present in the config file.

All plots land in <output_dir>/PLOTS/.

Output files (up to four per analyzed column):
  <col>_full.jpg      y vs x (full sweep)
  <col>_zoom.jpg      y vs x (zoomed to discontinuity regions)
  <col>_fda2_full.jpg d²y/dx² (full sweep)
  <col>_fda2_zoom.jpg d²y/dx² (zoomed)

plots keys and types:
  output_dir        string          Output directory. Default: <io.output_dir>/PLOTS/
  figsize           [float, float]  Figure size in inches. Default: [16.0, 9.0]
  dpi               int             Resolution. Default: 200
  ylabel            string          Y-axis label. Default: column name
  unit_scale        float           Scale factor on y values. Default: 1.0
  xlabel            string          X-axis label. Default: independent column name
  xlim              [float, float]  X-axis limits. Default: auto
  tick_step         float           X-axis tick spacing. Default: auto
  zoom_padding      float           Fractional padding around zoom windows. Default: 0.05
  zoom_merge_within float           Merge zoom windows within this x-distance. Default: 0.02
  title_prefix      string          Prefix for all plot titles. Default: ""

plots.grouping keys (family-of-curves):
  column          string  CSV column name used to group curves.
  min             float   Exclude groups below this value.
  max             float   Exclude groups above this value.
  step            float   Only include groups at multiples of this interval from min.
  skip            array   Specific group values to exclude.
  label_template  string  Python format: {field} and {value:.Ng} placeholders available.
                          Use {{ }} to escape literal braces in LaTeX strings.\
""",
}


def _load_config(path: Path | None = None) -> dict[str, Any]:
    """Load YAML config from *path*, or the default user config path if None."""
    target = path if path is not None else _DEFAULT_CONFIG_PATH
    try:
        with target.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError:
        if path is not None:
            raise
        return {}
    except (OSError, yaml.YAMLError):
        return {}


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for discont-finder."""
    parser = argparse.ArgumentParser(
        prog="discont-finder",
        description=(
            "Find discontinuities in numeric columns of a CSV file.\n\n"
            "INPUT FORMAT:\n"
            "  A standard CSV with a header row. Columns with float-parsable values\n"
            "  are analyzed. Column names are matched exactly.\n\n"
            "DETECTION:\n"
            "  Robust MAD-normalized curvature-jump with peak filtering.\n"
        ),
        epilog=(
            "EXAMPLES:\n"
            "  discont-finder data.csv\n"
            "  discont-finder data.csv -s 30 --min-prominence 10\n"
            "  discont-finder data.csv -p\n"
            "  discont-finder data.csv -c ~/myproject/config.yaml\n"
            "  cat data.csv | discont-finder -\n"
            "  discont-finder data.csv --inject -o faulted.csv --count 5 --seed 42\n\n"
            "Use --help-format <topic> for detailed format documentation.\n"
            "Topics: config, csv, plots\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        metavar="PATH",
        help="Path to YAML config file (default: ~/.config/discontinuity_finder/config.yaml).",
    )
    parser.add_argument(
        "--help-format",
        metavar="TOPIC",
        choices=list(_HELP_FORMAT_TOPICS),
        help=(
            "Show detailed format documentation for TOPIC and exit. "
            "Topics: " + ", ".join(_HELP_FORMAT_TOPICS) + "."
        ),
    )
    parser.add_argument(
        "-s",
        "--sensitivity",
        type=float,
        default=None,
        help=(
            "Robust detector sigma multiplier on MAD (default 50). "
            "Falls back to [detection].sensitivity in config."
        ),
    )
    parser.add_argument(
        "--min-prominence",
        type=float,
        default=None,
        help=(
            "Minimum z-score prominence for a flagged peak "
            "(default 20.0; also from [detection].min_prominence)."
        ),
    )
    parser.add_argument(
        "--min-separation",
        type=int,
        default=None,
        help=(
            "Minimum index gap between flagged peaks "
            "(default 3; also from [detection].min_separation)."
        ),
    )
    parser.add_argument(
        "-p",
        "--plot",
        action="store_true",
        help=(
            "Render plots. Uses [plots] config if present; otherwise uses default formatting."
        ),
    )
    parser.add_argument(
        "--inject",
        action="store_true",
        help=(
            "Inject mode: write a new CSV with random spikes added to a "
            "numeric column. Bypasses config and detection entirely. Requires -o."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Inject mode: destination CSV path.",
    )
    parser.add_argument(
        "--column",
        default=None,
        help="Inject mode: column to corrupt (default: last numeric column).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Inject mode: number of spikes (default: 1%% of samples, min 1).",
    )
    parser.add_argument(
        "--magnitude",
        type=float,
        default=None,
        help="Inject mode: spike magnitude (default: 10%% of signal peak-to-peak).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Inject mode: RNG seed for reproducible spike placement.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="CSV input file path. Omit or use '-' to read from stdin.",
    )
    return parser


def _load_numeric_columns_from_stream(stream: TextIO) -> dict[str, list[float]]:
    """Parse numeric columns from a CSV stream."""
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


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("_")
    return cleaned or "column"


def _resolve_output_dir(config: dict[str, Any]) -> Path:
    """Return the base output directory from config, or the default."""
    raw = (config.get("io") or {}).get("output_dir")
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / "spice_cli_output"


def _write_results_csv(
    detections: dict[str, dict[float | None, tuple[DetectionResult, np.ndarray, np.ndarray, np.ndarray]]],
    output_dir: Path,
    filename: str = "results.csv",
    group_field: str | None = None,
) -> Path:
    """Write detection results to a CSV file.

    Parameters
    ----------
    detections:
        ``{column_name: {group_value_or_None: (DetectionResult, x_arr, y_arr, row_idxs)}}``.
    output_dir:
        Directory to write into (created if needed).
    filename:
        Output file name. Default ``"results.csv"``.
    group_field:
        CSV column name used for grouping, or ``None`` for ungrouped.

    Returns
    -------
    Path
        Absolute path of the written CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if group_field:
            writer.writerow(
                ["field", "group_field", "group", "input_row", "x_value", "y_value", "score", "threshold", "method"]
            )
        else:
            writer.writerow(
                ["field", "input_row", "x_value", "y_value", "score", "threshold", "method"]
            )

        for field_name, per_group in detections.items():
            for group_value, (result, x_arr, y_arr, row_idxs) in sorted(
                per_group.items(), key=lambda kv: (kv[0] is None, kv[0] or 0.0)
            ):
                group_str = "" if group_value is None else f"{group_value:.6g}"
                for idx in result.indices:
                    x_val = (
                        result.x[idx] if idx < result.x.size else float("nan")
                    )
                    score_val = (
                        result.score[idx]
                        if idx < result.score.size
                        else float("nan")
                    )
                    closest = int(np.argmin(np.abs(x_arr - x_val)))
                    y_val = float(y_arr[closest])
                    input_row_val = int(row_idxs[closest]) + 1
                    if group_field:
                        writer.writerow(
                            [
                                field_name,
                                group_field,
                                group_str,
                                input_row_val,
                                f"{x_val:.6g}",
                                f"{y_val:.6g}",
                                f"{score_val:.6g}",
                                f"{result.threshold:.6g}",
                                result.method,
                            ]
                        )
                    else:
                        writer.writerow(
                            [
                                field_name,
                                input_row_val,
                                f"{x_val:.6g}",
                                f"{y_val:.6g}",
                                f"{score_val:.6g}",
                                f"{result.threshold:.6g}",
                                result.method,
                            ]
                        )

    return out_path


def _resolve_detection_params(
    sensitivity: float | None,
    min_prominence: float | None,
    min_separation: int | None,
    detection_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Translate CLI/config values into kwargs for ``find.detect``."""
    sigma = sensitivity if sensitivity is not None else detection_cfg.get("sigma")
    if sigma is None:
        sigma = 50.0
    sigma = float(sigma)
    if sigma <= 0:
        raise ValueError("-s/--sensitivity must be greater than 0.")

    prom = min_prominence
    if prom is None:
        prom = detection_cfg.get("min_prominence", 20.0)
    prom = float(prom)

    sep = min_separation
    if sep is None:
        sep = int(detection_cfg.get("min_separation", 3))

    return {
        "sigma": sigma,
        "min_prominence": prom,
        "min_separation": sep,
    }


def _group_rows(
    columns: dict[str, list[float]],
    independent_col: str,
    dependent_col: str,
    grouping_col: str | None,
) -> dict[float | None, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return ``{group_value_or_None: (x_sorted, y_sorted, row_idxs_sorted)}``.

    When ``grouping_col`` is None, the whole column is a single group keyed
    by ``None``. ``row_idxs`` are 0-based indices into the original CSV data
    rows (add 1 for 1-based spreadsheet row numbers).
    """
    x_all = columns[independent_col]
    y_all = columns[dependent_col]
    n = min(len(x_all), len(y_all))
    if grouping_col and grouping_col in columns:
        g_all = columns[grouping_col]
        n = min(n, len(g_all))
    else:
        g_all = None

    buckets: dict[float | None, tuple[list[float], list[float], list[int]]] = defaultdict(
        lambda: ([], [], [])
    )
    for i in range(n):
        key: float | None = None
        if g_all is not None:
            key = round(float(g_all[i]), 9)
        xs, ys, idxs = buckets[key]
        xs.append(float(x_all[i]))
        ys.append(float(y_all[i]))
        idxs.append(i)

    out: dict[float | None, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for key, (xs, ys, idxs) in buckets.items():
        x_arr = np.asarray(xs, dtype=float)
        y_arr = np.asarray(ys, dtype=float)
        idx_arr = np.asarray(idxs, dtype=int)
        order = np.argsort(x_arr, kind="mergesort")
        out[key] = (x_arr[order], y_arr[order], idx_arr[order])
    return out


def _generic_column_summary(
    columns: dict[str, list[float]],
    method_params: dict[str, Any],
    error_stream: TextIO,
    independent_col: str | None = None,
    group_by_col: str | None = None,
) -> dict[str, dict[float | None, tuple[DetectionResult, np.ndarray, np.ndarray, np.ndarray]]]:
    """Run detection on every numeric column, with optional x-axis and grouping.

    Parameters
    ----------
    columns:
        Numeric columns from CSV.
    method_params:
        Keyword arguments for ``find.detect``.
    error_stream:
        Stream for warning messages.
    independent_col:
        CSV column to use as x-axis. When set, that column is skipped as a
        y-series and used as x for all others.  When absent, row index is used.
    group_by_col:
        CSV column to partition rows by before running detection. Requires
        ``independent_col`` to be set and present in the data.

    Returns
    -------
    dict
        ``{column_name: {group_value_or_None: (DetectionResult, x_arr, y_arr, row_idxs)}}``.
    """
    x_override: np.ndarray | None = None
    if independent_col and independent_col in columns:
        x_override = np.asarray(columns[independent_col], dtype=float)

    use_grouping = (
        group_by_col is not None
        and group_by_col in columns
        and independent_col is not None
        and independent_col in columns
    )

    results: dict[str, dict[float | None, tuple[DetectionResult, np.ndarray, np.ndarray, np.ndarray]]] = {}

    for name, values in columns.items():
        if name == independent_col or name == group_by_col:
            continue
        if len(values) < 4:
            continue

        if use_grouping:
            assert independent_col is not None
            try:
                groups = _group_rows(columns, independent_col, name, group_by_col)
            except (KeyError, ValueError) as exc:
                print(f"warning: could not group column {name!r}: {exc}", file=error_stream)
                continue
        else:
            y = np.asarray(values, dtype=float)
            x = x_override if x_override is not None else np.arange(y.size, dtype=float)
            row_idxs = np.arange(len(y), dtype=int)
            groups = {None: (x, y, row_idxs)}

        per_group: dict[float | None, tuple[DetectionResult, np.ndarray, np.ndarray, np.ndarray]] = {}
        has_variation = False
        mirrors_independent = True

        for group_value, (x_arr, y_arr, row_idxs) in groups.items():
            if x_arr.size < 4:
                continue
            y_range = float(np.ptp(y_arr))
            y_scale = max(abs(float(np.mean(y_arr))), 1.0)
            if y_range / y_scale > 1e-9:
                has_variation = True
            if mirrors_independent and not np.allclose(x_arr, y_arr, rtol=1e-9, atol=1e-12):
                mirrors_independent = False
            try:
                per_group[group_value] = (
                    find_detect(x_arr, y_arr, **method_params),
                    x_arr,
                    y_arr,
                    row_idxs,
                )
            except ValueError as exc:
                print(f"warning: column {name!r} group={group_value}: {exc}", file=error_stream)

        if per_group and has_variation and not mirrors_independent:
            results[name] = per_group

    return results


def _write_generic_summary(
    results: dict[str, dict[float | None, tuple[DetectionResult, np.ndarray, np.ndarray, np.ndarray]]],
    output: TextIO,
) -> int:
    """Print a per-column, per-group discontinuity summary."""
    print(f"Analyzed {len(results)} numeric column(s).", file=output)
    total = sum(
        tup[0].indices.size
        for per_group in results.values()
        for tup in per_group.values()
    )
    if total == 0:
        print("No discontinuities found.", file=output)
        return 0
    print(f"Found {total} discontinuity/discontinuities.", file=output)
    for name, per_group in results.items():
        field_total = sum(tup[0].indices.size for tup in per_group.values())
        print(f"{name}: {field_total}", file=output)
        for group_value, (result, _, _, _) in sorted(
            per_group.items(), key=lambda kv: (kv[0] is None, kv[0] or 0.0)
        ):
            if result.indices.size == 0:
                continue
            xs = result.x[result.indices[result.indices < result.x.size]]
            x_str = ", ".join(f"{v:.6g}" for v in xs)
            gtag = "all" if group_value is None else f"{group_value:.6g}"
            print(
                f"  group={gtag}: {result.indices.size} at x=[{x_str}] "
                f"(method={result.method}, thr={result.threshold:.3g})",
                file=output,
            )
    return total


def _render_generic_plots(
    results: dict[str, dict[float | None, tuple[DetectionResult, np.ndarray, np.ndarray, np.ndarray]]],
    independent_col: str | None,
    plot_config,
    output_stream: TextIO,
    error_stream: TextIO,
) -> None:
    """Render plots for each analyzed column into ``<output_dir>/PLOTS/``."""
    from .plot import render_plots, filter_groups
    from dataclasses import replace

    if not results:
        return

    total_written = 0
    for col_name, per_group in results.items():
        groups_xy: dict[float | None, tuple[np.ndarray, np.ndarray]] = {}
        dets: dict[float | None, DetectionResult] = {}
        for gv, (result, x, y, _) in per_group.items():
            groups_xy[gv] = (x, y)
            dets[gv] = result

        if plot_config.grouping_column:
            numeric_keys = [k for k in groups_xy if k is not None]
            selected: list[float | None] = filter_groups(numeric_keys, plot_config)  # type: ignore[assignment]
            if None in groups_xy and not numeric_keys:
                selected = [None]
        else:
            selected = list(groups_xy)

        groups_to_plot = {k: groups_xy[k] for k in selected if k in groups_xy}
        dets_to_plot = {k: dets[k] for k in selected if k in dets}
        if not groups_to_plot:
            continue

        field_config = replace(
            plot_config,
            xlabel=plot_config.xlabel or (independent_col or "index"),
            ylabel=plot_config.ylabel or col_name,
        )
        try:
            written = render_plots(
                groups_to_plot,
                dets_to_plot,
                col_name=col_name,
                config=field_config,
                x_col_name=independent_col or "",
            )
            total_written += len(written)
        except Exception as exc:
            print(f"warning: plotting {col_name!r} failed: {exc}", file=error_stream)

    if total_written:
        print(
            f"Saved {total_written} plot(s) under {plot_config.output_dir}/",
            file=output_stream,
        )


def _open_input(
    input_path: str | None, input_stream: TextIO, error_stream: TextIO
) -> tuple[TextIO, bool] | None:
    """Return (stream, should_close) or None on error (message already printed)."""
    if input_path and input_path != "-":
        try:
            handle = Path(input_path).open(encoding="utf-8", newline="")
        except OSError as exc:
            print(f"error: {exc}", file=error_stream)
            return None
        return handle, True
    is_tty = getattr(input_stream, "isatty", lambda: False)
    if is_tty():
        print(
            "error: no input provided. Pass a file path or pipe CSV data on stdin.",
            file=error_stream,
        )
        return None
    return input_stream, False


def _pick_target_column(
    fieldnames: Sequence[str], rows: list[dict[str, str]]
) -> str | None:
    """Return the rightmost column whose cells are mostly float-parseable."""
    for name in reversed(list(fieldnames)):
        non_empty = 0
        numeric = 0
        for row in rows:
            raw = (row.get(name) or "").strip()
            if not raw:
                continue
            non_empty += 1
            try:
                float(raw)
                numeric += 1
            except ValueError:
                pass
        if non_empty and numeric / non_empty >= 0.9:
            return name
    return None


def _run_inject(
    args: argparse.Namespace,
    input_stream: TextIO,
    output_stream: TextIO,
    error_stream: TextIO,
) -> int:
    if not args.output:
        print("error: --inject requires -o/--output.", file=error_stream)
        return 2

    opened = _open_input(args.input, input_stream, error_stream)
    if opened is None:
        return 2
    handle, should_close = opened
    try:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames:
            print("error: CSV input has no header row.", file=error_stream)
            return 2
        rows = list(reader)
    except OSError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2
    finally:
        if should_close:
            handle.close()

    if args.column is not None:
        if args.column not in fieldnames:
            print(
                f"error: column {args.column!r} not found in CSV header.",
                file=error_stream,
            )
            return 2
        target = args.column
    else:
        target = _pick_target_column(fieldnames, rows)
        if target is None:
            print("error: no numeric column found to inject into.", file=error_stream)
            return 2

    indexed: list[tuple[int, float]] = []
    for i, row in enumerate(rows):
        raw = (row.get(target) or "").strip()
        if not raw:
            continue
        try:
            indexed.append((i, float(raw)))
        except ValueError:
            continue

    if not indexed:
        print(
            f"error: column {target!r} has no numeric values.", file=error_stream
        )
        return 2

    values = [v for _, v in indexed]
    count = args.count if args.count is not None else max(1, int(0.01 * len(values)))
    if args.magnitude is not None:
        magnitude = args.magnitude
    else:
        span = max(values) - min(values)
        magnitude = 0.1 * span if span > 0 else 1.0

    try:
        perturbed = inject_random_spikes(values, count, magnitude, args.seed)
    except (ValueError, IndexError) as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    overrides: dict[int, str] = {}
    for (row_idx, _), new_val in zip(indexed, perturbed):
        overrides[row_idx] = f"{new_val:.5e}"

    try:
        with Path(args.output).open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=list(fieldnames))
            writer.writeheader()
            for i, row in enumerate(rows):
                if i in overrides:
                    row = {**row, target: overrides[i]}
                writer.writerow(row)
    except OSError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    print(
        f'injected {count} spikes (mag={magnitude:g}) into "{target}" -> {args.output}',
        file=output_stream,
    )
    return 0


def main(
    argv: Sequence[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the discont-finder workflow.

    Parameters
    ----------
    argv:
        Argument list. If None, reads from ``sys.argv``.
    stdin:
        Input stream. Defaults to ``sys.stdin``.
    stdout:
        Output stream. Defaults to ``sys.stdout``.
    stderr:
        Error stream. Defaults to ``sys.stderr``.

    Returns
    -------
    int
        Exit code: 0 on success, 2 on usage or configuration error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    error_stream = stderr if stderr is not None else sys.stderr

    if args.help_format:
        print(_HELP_FORMAT_TOPICS[args.help_format], file=output_stream)
        return 0

    if args.inject:
        return _run_inject(args, input_stream, output_stream, error_stream)

    config_path = Path(args.config).expanduser() if args.config else None
    try:
        config = _load_config(config_path)
    except FileNotFoundError:
        print(f"error: config file not found: {args.config}", file=error_stream)
        return 2

    detection_cfg = config.get("detection") or {}

    sensitivity = args.sensitivity
    if sensitivity is None:
        sensitivity = detection_cfg.get("sensitivity")

    try:
        method_params = _resolve_detection_params(
            sensitivity,
            args.min_prominence,
            args.min_separation,
            detection_cfg,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    input_path = args.input
    try:
        if input_path and input_path != "-":
            with Path(input_path).open(encoding="utf-8", newline="") as handle:
                columns = _load_numeric_columns_from_stream(handle)
        else:
            is_tty = getattr(input_stream, "isatty", lambda: False)
            if is_tty():
                configured = (config.get("io") or {}).get("files") or []
                if configured:
                    with Path(configured[0]).open(encoding="utf-8", newline="") as handle:
                        columns = _load_numeric_columns_from_stream(handle)
                else:
                    print(
                        "error: no input provided. Pass a file path or pipe CSV data on stdin.",
                        file=error_stream,
                    )
                    return 2
            else:
                columns = _load_numeric_columns_from_stream(input_stream)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    base_output_dir = _resolve_output_dir(config)
    analysis_cfg = config.get("analysis") or {}
    independent_col = analysis_cfg.get("independent_col")
    group_by_col = analysis_cfg.get("group_by")

    try:
        results = _generic_column_summary(
            columns, method_params, error_stream,
            independent_col=independent_col,
            group_by_col=group_by_col,
        )
        _write_generic_summary(results, output_stream)

        csv_path = _write_results_csv(results, base_output_dir, group_field=group_by_col)
        print(f"Results written to {csv_path}", file=output_stream)

        want_plots = args.plot or ("plots" in config)
        if want_plots:
            from .plot import load_plot_config
            try:
                plot_config = load_plot_config(
                    config, fallback_output_dir=base_output_dir
                )
            except ValueError as exc:
                print(f"warning: plotting disabled: {exc}", file=error_stream)
                plot_config = None

            if plot_config is not None and results:
                _render_generic_plots(
                    results, independent_col, plot_config, output_stream, error_stream
                )

    except ValueError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
