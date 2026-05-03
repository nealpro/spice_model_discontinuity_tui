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

from .devices import Device, active_device
from spice_discontinuity.find import DetectionResult, detect as find_detect
from spice_discontinuity.inject import inject_random_spikes

_DEFAULT_CONFIG_PATH = Path("~/.config/spice_cli/config.yaml").expanduser()

VALID_METHODS = ("simple", "higher_order", "robust")
DEFAULT_METHOD = "robust"

_HELP_FORMAT_TOPICS: dict[str, str] = {
    "config": """\
CONFIG FILE FORMAT
==================
Default path: ~/.config/spice_cli/config.yaml
Override with: spice-cli -c /path/to/config.yaml
Format: YAML

Sections recognized:

  output:
    output_dir: "spice_cli_output"   # base directory for all output files

  detection:
    method: "robust"                 # "simple" | "higher_order" | "robust"
    sensitivity: 50.0               # threshold (simple/higher_order) or z-score sigma (robust)
    min_prominence: 20.0            # robust only: minimum peak prominence
    min_separation: 3               # robust only: minimum index gap between peaks

  inputs:
    files: ["data/nmos.csv"]         # fallback file(s) when stdin is a terminal

  analysis:
    device: "FET"                    # active device (must match a devices.<NAME> table)

  devices:
    FET:
      independent: "gate_voltage"
      gate_voltage: "V(X1.GATE,X1.SOURCE)"
      drain_current: "I(VDRAIN)"
      source_bulk_voltage: "V(X1.SOURCE,X1.BULK)"

  plots:                             # presence of this section enables plotting
    output_dir: "spice_plots"
    figsize: [16, 9]
    dpi: 200
    ids_ylabel: "$I_D$"
    ids_unit_scale: 1.0
    vgs_xlabel: "$V_{GS}$ (V)"
    vgs_xlim: [0.0, 1.8]
    vgs_tick_step: 0.2
    title_prefix: "NFET"
    grouping:
      field: "source_bulk_voltage"
      min: 0.0
      max: 1.5
      step: 0.1
      skip: []
      label_template: "$V_{{SB}} = {value:.2f}$ V"

See config_examples/config.yaml for a fully annotated example.\
""",
    "device": """\
DEVICE FORMAT
=============
A device maps semantic field names to CSV column headers.
Defined under devices.<NAME> in config.yaml.

Required key:
  independent = "<field_name>"   points to the x-axis field in this table

All other string-valued keys are dependent fields:
  <semantic_name> = "<CSV column header>"

Column name matching is case-sensitive and must be exact, including spaces
and parentheses (e.g. LTspice exports columns like "V(X1.GATE,X1.SOURCE)").

Example:
  devices:
    NFET:
      independent: "gate_voltage"
      gate_voltage: "V(X1.GATE,X1.SOURCE)"
      drain_current: "I(VDRAIN)"
      source_bulk_voltage: "V(X1.SOURCE,X1.BULK)"

Activate in config:
  analysis:
    device: "NFET"

Or per-run with the --device flag:
  spice-cli data.csv --device NFET

Adding a new device type requires only a YAML change — no code change.\
""",
    "csv": """\
CSV INPUT FORMAT
================
A standard comma-separated file with a header row.

Rules:
  - First row must be the header (column names).
  - All other rows are data. Rows with non-parseable values in a column
    are skipped for that column; other columns are unaffected.
  - A column is treated as numeric if at least 90% of non-empty cells
    parse as float.
  - Column names may contain any characters, including spaces, parentheses,
    and special symbols (LTspice-style names are fully supported).

Minimal example:
  V(GATE),I(VDRAIN),V(SB)
  0.0,1.23e-9,0.0
  0.1,5.67e-9,0.0
  0.2,2.10e-8,0.5

Reading from a file:
  spice-cli data.csv

Reading from stdin:
  cat data.csv | spice-cli -
  spice-cli -          (then paste and press Ctrl-D)\
""",
    "plots": """\
PLOTS FORMAT
============
Plotting is ONLY supported for DC sweep data.

Plots are generated when either:
  - The -p/--plot flag is passed, OR
  - The plots section is present in the config file.

When -p is used without a plots config section, default formatting is applied.

Output files (four per analyzed field):
  iv_full.jpg     I_D vs V_GS (full sweep)
  iv_zoom.jpg     I_D vs V_GS (zoomed to discontinuity regions)
  fda2_full.jpg   d2I_D/dV_GS2 (full sweep)
  fda2_zoom.jpg   d2I_D/dV_GS2 (zoomed)

plots keys and types:
  output_dir        string          Output directory. Default: <output_dir>/plots/
  figsize           [float, float]  Figure size in inches. Default: [16.0, 9.0]
  dpi               int             Resolution. Default: 200
  ids_ylabel        string          Y-axis label. Default: "$I_D$"
  ids_unit_scale    float           Scale factor on current values. Default: 1.0
  vgs_xlabel        string          X-axis label. Default: "$V_{GS}$ (V)"
  vgs_xlim          [float, float]  X-axis limits. Default: auto
  vgs_tick_step     float           X-axis tick spacing. Default: auto
  zoom_padding      float           Fractional padding around zoom windows. Default: 0.05
  zoom_merge_within float           Merge zoom windows within this x-distance. Default: 0.02
  title_prefix      string          Prefix for all plot titles. Default: ""

plots.grouping keys (family-of-curves):
  field           string  Semantic field from devices.<NAME> used to group curves.
  min             float   Exclude groups below this value.
  max             float   Exclude groups above this value.
  step            float   Only include groups at multiples of this interval from min.
  skip            array   Specific group values to exclude.
  label_template  string  Python format: {field} and {value:.Ng} placeholders available.
                          Use {{ }} to escape literal braces in LaTeX strings.\
""",
}


def _load_config(path: Path | None = None) -> dict[str, Any]:
    """Load YAML config from *path*, or the default user config path if None.

    Parameters
    ----------
    path:
        Explicit config file path. If None, defaults to
        ``~/.config/spice_cli/config.yaml``.

    Returns
    -------
    dict
        Parsed YAML content, or ``{}`` if the default path does not exist.

    Raises
    ------
    FileNotFoundError
        If *path* was explicitly given but does not exist.
    """
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
    """Build the argument parser for spice-cli."""
    parser = argparse.ArgumentParser(
        prog="spice-cli",
        description=(
            "Find discontinuities in numeric columns of a SPICE CSV output file.\n\n"
            "INPUT FORMAT:\n"
            "  A standard CSV with a header row. All columns where 90%+ of cells\n"
            "  parse as float are analyzed. Column names are matched exactly,\n"
            "  including spaces and parentheses (LTspice-style names are supported).\n\n"
            "DETECTION METHODS:\n"
            "  simple        Flag |y_i - y_{i-1}| >= T  (requires -s)\n"
            "  higher_order  Flag derivative-ratio score >= T  (requires -s)\n"
            "  robust        MAD-normalized curvature-jump, peak-filtered  (default)\n"
        ),
        epilog=(
            "EXAMPLES:\n"
            "  spice-cli data.csv\n"
            "  spice-cli data.csv --method simple -s 1e-4\n"
            "  spice-cli data.csv --method robust -s 30 --min-prominence 10\n"
            "  spice-cli data.csv -p\n"
            "  spice-cli data.csv --device FET -p\n"
            "  spice-cli data.csv -c ~/myproject/config.yaml\n"
            "  cat data.csv | spice-cli -\n"
            "  spice-cli data.csv --inject -o faulted.csv --count 5 --seed 42\n\n"
            "Use --help-format <topic> for detailed format documentation.\n"
            "Topics: config, device, csv, plots\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        metavar="PATH",
        help="Path to YAML config file (default: ~/.config/spice_cli/config.yaml).",
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
            "For simple/higher_order: raw score threshold (> 0). "
            "For robust: sigma multiplier on MAD (default 50). "
            "Falls back to [detection].sensitivity in config."
        ),
    )
    parser.add_argument(
        "--method",
        choices=VALID_METHODS,
        default=None,
        help=f"Detection method. Falls back to [detection].method (default: {DEFAULT_METHOD}).",
    )
    parser.add_argument(
        "--min-prominence",
        type=float,
        default=None,
        help=(
            "Robust method only: minimum z-score prominence for a flagged peak "
            "(default 20.0; also from [detection].min_prominence)."
        ),
    )
    parser.add_argument(
        "--min-separation",
        type=int,
        default=None,
        help=(
            "Robust method only: minimum index gap between flagged peaks "
            "(default 3; also from [detection].min_separation)."
        ),
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override the active device name (otherwise uses [analysis].device from config).",
    )
    parser.add_argument(
        "-p",
        "--plot",
        action="store_true",
        help=(
            "Render IV-curve plots. Only valid for DC sweep data with an active device. "
            "Uses [plots] config if present; otherwise uses default formatting."
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
    """Parse numeric columns from a CSV stream.

    Parameters
    ----------
    stream:
        Readable text stream positioned at the start of a CSV file.

    Returns
    -------
    dict
        Mapping of column name to list of float values for all numeric columns.

    Raises
    ------
    ValueError
        If the stream has no header row or contains no numeric data.
    """
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
    """Return the base output directory from config, or the default.

    Fallback chain: ``[output].output_dir`` → ``[output].plots_dir`` →
    ``./spice_cli_output``.

    Parameters
    ----------
    config:
        Parsed YAML config dict.

    Returns
    -------
    Path
        Resolved output directory (not yet created).
    """
    output_cfg = config.get("output") or {}
    raw = output_cfg.get("output_dir") or output_cfg.get("plots_dir")
    if raw:
        return Path(raw).expanduser()
    return Path.cwd() / "spice_cli_output"


def _write_results_csv(
    detections: dict[str, Any],
    output_dir: Path,
    filename: str = "results.csv",
) -> Path:
    """Write detection results to a CSV file.

    Handles both device-mode results ``{semantic: {group: DetectionResult}}``
    and generic-mode results ``{column_name: DetectionResult}``.

    Parameters
    ----------
    detections:
        Device-mode: ``{semantic_field: {group_value: DetectionResult}}``.
        Generic-mode: ``{column_name: DetectionResult}``.
    output_dir:
        Directory to write the results file into (created if needed).
    filename:
        Output file name. Default ``"results.csv"``.

    Returns
    -------
    Path
        Absolute path of the written CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["field", "group", "index", "x_value", "score", "threshold", "method"]
        )

        for field_name, field_data in detections.items():
            if isinstance(field_data, DetectionResult):
                per_group: dict[float | None, DetectionResult] = {None: field_data}
            else:
                per_group = field_data

            for group_value, result in sorted(
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
                    writer.writerow(
                        [
                            field_name,
                            group_str,
                            int(idx),
                            f"{x_val:.6g}",
                            f"{score_val:.6g}",
                            f"{result.threshold:.6g}",
                            result.method,
                        ]
                    )

    return out_path


def _resolve_method_params(
    method: str,
    sensitivity: float | None,
    min_prominence: float | None,
    min_separation: int | None,
    detection_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Translate CLI/config values into kwargs for ``find.detect``.

    Parameters
    ----------
    method:
        One of ``"simple"``, ``"higher_order"``, or ``"robust"``.
    sensitivity:
        Raw threshold (simple/higher_order) or sigma multiplier (robust).
    min_prominence:
        Robust only: minimum peak prominence.
    min_separation:
        Robust only: minimum index gap between flagged peaks.
    detection_cfg:
        ``config["detection"]`` dict for config-level fallbacks.

    Returns
    -------
    dict
        Keyword arguments to pass to ``find.detect``.

    Raises
    ------
    ValueError
        If ``method`` is simple/higher_order and no sensitivity is provided,
        or if sensitivity is not positive.
    """
    if method in {"simple", "higher_order"}:
        if sensitivity is None:
            raise ValueError(
                f"method '{method}' requires -s/--sensitivity or [detection].sensitivity."
            )
        if sensitivity <= 0:
            raise ValueError("-s/--sensitivity must be greater than 0.")
        return {"threshold": float(sensitivity)}

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
) -> dict[float | None, tuple[np.ndarray, np.ndarray]]:
    """Return ``{group_value_or_None: (x_sorted, y_sorted)}``.

    When ``grouping_col`` is None, the whole column is a single group keyed
    by ``None``.
    """
    x_all = columns[independent_col]
    y_all = columns[dependent_col]
    n = min(len(x_all), len(y_all))
    if grouping_col and grouping_col in columns:
        g_all = columns[grouping_col]
        n = min(n, len(g_all))
    else:
        g_all = None

    buckets: dict[float | None, tuple[list[float], list[float]]] = defaultdict(
        lambda: ([], [])
    )
    for i in range(n):
        key: float | None = None
        if g_all is not None:
            key = round(float(g_all[i]), 9)
        xs, ys = buckets[key]
        xs.append(float(x_all[i]))
        ys.append(float(y_all[i]))

    out: dict[float | None, tuple[np.ndarray, np.ndarray]] = {}
    for key, (xs, ys) in buckets.items():
        x_arr = np.asarray(xs, dtype=float)
        y_arr = np.asarray(ys, dtype=float)
        order = np.argsort(x_arr, kind="mergesort")
        out[key] = (x_arr[order], y_arr[order])
    return out


def _analyze_device(
    columns: dict[str, list[float]],
    device: Device,
    method: str,
    method_params: dict[str, Any],
    plot_config,
    error_stream: TextIO,
) -> dict[str, dict[float | None, DetectionResult]]:
    """Run method-dispatched detection per dependent field and per group.

    Parameters
    ----------
    columns:
        All numeric columns loaded from CSV.
    device:
        Active device providing field → column mappings.
    method:
        Detection method name.
    method_params:
        Keyword arguments for ``find.detect``.
    plot_config:
        ``PlotConfig`` providing the grouping column, or ``None`` for no grouping.
    error_stream:
        Stream for warning messages.

    Returns
    -------
    dict
        ``{semantic_field: {group_value: DetectionResult}}``.
    """
    if device.independent_column not in columns:
        return {}

    grouping_col = plot_config.grouping_column if plot_config else None

    results: dict[str, dict[float | None, DetectionResult]] = {}
    for semantic, csv_name in device.dependent_items():
        if csv_name == grouping_col or semantic == device.independent:
            continue
        if csv_name not in columns:
            continue
        try:
            groups = _group_rows(
                columns, device.independent_column, csv_name, grouping_col
            )
        except (KeyError, ValueError) as exc:
            print(
                f"warning: could not group {device.name}.{semantic}: {exc}",
                file=error_stream,
            )
            continue

        per_group: dict[float | None, DetectionResult] = {}
        has_variation = False
        mirrors_independent = True
        for group_value, (x_arr, y_arr) in groups.items():
            if x_arr.size < 4 and method == "robust":
                continue
            if x_arr.size < 2:
                continue
            y_range = float(np.ptp(y_arr))
            y_scale = max(abs(float(np.mean(y_arr))), 1.0)
            if y_range / y_scale > 1e-9:
                has_variation = True
            if mirrors_independent and not np.allclose(x_arr, y_arr, rtol=1e-9, atol=1e-12):
                mirrors_independent = False
            try:
                per_group[group_value] = find_detect(method, x_arr, y_arr, **method_params)
            except ValueError as exc:
                print(
                    f"warning: {device.name}.{semantic} "
                    f"group={group_value}: {exc}",
                    file=error_stream,
                )
        if per_group and has_variation and not mirrors_independent:
            results[semantic] = per_group
    return results


def _generic_column_summary(
    columns: dict[str, list[float]],
    method: str,
    method_params: dict[str, Any],
    error_stream: TextIO,
) -> dict[str, DetectionResult]:
    """Run detection on every numeric column vs row index (no device config).

    Parameters
    ----------
    columns:
        Numeric columns from CSV.
    method:
        Detection method name.
    method_params:
        Keyword arguments for ``find.detect``.
    error_stream:
        Stream for warning messages.

    Returns
    -------
    dict
        ``{column_name: DetectionResult}``.
    """
    results: dict[str, DetectionResult] = {}
    for name, values in columns.items():
        if len(values) < 2:
            continue
        y = np.asarray(values, dtype=float)
        x = np.arange(y.size, dtype=float)
        if method == "robust" and y.size < 4:
            continue
        try:
            results[name] = find_detect(method, x, y, **method_params)
        except ValueError as exc:
            print(f"warning: column {name!r}: {exc}", file=error_stream)
    return results


def _write_device_summary(
    device: Device,
    results: dict[str, dict[float | None, DetectionResult]],
    output: TextIO,
) -> int:
    """Print a per-field, per-group discontinuity summary for a device.

    Parameters
    ----------
    device:
        Active device.
    results:
        ``{semantic_field: {group_value: DetectionResult}}``.
    output:
        Stream to write the summary to.

    Returns
    -------
    int
        Total number of discontinuities found across all fields and groups.
    """
    total = 0
    field_count = len(results)
    print(
        f"Analyzed device {device.name!r} over {field_count} dependent field(s).",
        file=output,
    )
    for semantic, per_group in results.items():
        field_total = sum(r.indices.size for r in per_group.values())
        total += field_total
        print(f"{device.name}.{semantic}: {field_total}", file=output)
        for group_value, result in sorted(
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
    if total == 0:
        print("No discontinuities found.", file=output)
    else:
        print(f"Found {total} discontinuity/discontinuities total.", file=output)
    return total


def _write_generic_summary(
    results: dict[str, DetectionResult], output: TextIO
) -> int:
    """Print a per-column discontinuity summary (no device).

    Parameters
    ----------
    results:
        ``{column_name: DetectionResult}``.
    output:
        Stream to write the summary to.

    Returns
    -------
    int
        Total number of discontinuities found.
    """
    print(f"Analyzed {len(results)} numeric column(s).", file=output)
    total = sum(r.indices.size for r in results.values())
    if total == 0:
        print("No discontinuities found.", file=output)
        return 0
    print(f"Found {total} discontinuity/discontinuities.", file=output)
    for name, result in results.items():
        print(f"{name}: {result.indices.size}", file=output)
        for idx in result.indices:
            if idx < result.x.size:
                x_val = result.x[idx]
            else:
                x_val = float(idx)
            score_val = result.score[idx] if idx < result.score.size else float("nan")
            print(
                f"  index={int(idx)} x={x_val:.6g} score={score_val:.6g}",
                file=output,
            )
    return total


def _render_plots(
    columns: dict[str, list[float]],
    device: Device,
    detections_by_field: dict[str, dict[float | None, DetectionResult]],
    plot_config,
    output_stream: TextIO,
    error_stream: TextIO,
) -> None:
    """Render the four focused plots for each analyzed dependent field.

    Parameters
    ----------
    columns:
        All numeric columns loaded from CSV.
    device:
        Active device providing field → column mappings.
    detections_by_field:
        ``{semantic_field: {group_value: DetectionResult}}``.
    plot_config:
        Populated ``PlotConfig`` instance.
    output_stream:
        Stream for progress messages.
    error_stream:
        Stream for warning messages.
    """
    from .plot import render_iv_plots

    if not detections_by_field:
        return

    grouping_col = plot_config.grouping_column
    independent_col = device.independent_column
    base_output = plot_config.output_dir

    total_written = 0
    for semantic, per_group in detections_by_field.items():
        csv_name = device.fields.get(semantic)
        if csv_name is None or csv_name not in columns:
            continue
        groups = _group_rows(columns, independent_col, csv_name, grouping_col)

        selected: list[float] = []
        if grouping_col:
            numeric_keys = [k for k in groups if k is not None]
            selected = _filter_group_values(numeric_keys, plot_config)
        else:
            selected = [None] if None in groups else []  # type: ignore[list-item]

        groups_to_plot = {k: groups[k] for k in selected if k in groups}
        dets_to_plot = {k: per_group[k] for k in selected if k in per_group}
        if not groups_to_plot:
            continue

        field_config = _with_output_dir(
            plot_config, base_output / _safe_filename(f"{device.name}_{semantic}")
        )
        written = render_iv_plots(groups_to_plot, dets_to_plot, config=field_config)
        total_written += len(written)

    if total_written:
        print(
            f"Saved {total_written} plot(s) under {base_output}/",
            file=output_stream,
        )


def _filter_group_values(values: list[float], plot_config) -> list[float]:
    from .plot import filter_groups

    return filter_groups(values, plot_config)


def _with_output_dir(plot_config, new_dir: Path):
    from dataclasses import replace

    return replace(plot_config, output_dir=new_dir)


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
    """Run the spice-cli workflow.

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

    Side effects:
        Always writes a ``results.csv`` to the output directory.
        Writes four JPEG plots per field when ``-p`` is given or ``[plots]``
        is present in config.
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

    method = args.method or detection_cfg.get("method") or DEFAULT_METHOD
    if method not in VALID_METHODS:
        print(
            f"error: unknown method {method!r} (expected {', '.join(VALID_METHODS)}).",
            file=error_stream,
        )
        return 2

    sensitivity = args.sensitivity
    if sensitivity is None:
        sensitivity = detection_cfg.get("sensitivity")

    try:
        method_params = _resolve_method_params(
            method,
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
                configured = config.get("inputs", {}).get("files") or []
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

    try:
        device = active_device(config, override=args.device)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    use_device = (
        device is not None
        and device.independent_column in columns
        and any(v in columns for _, v in device.dependent_items())
    )

    base_output_dir = _resolve_output_dir(config)

    try:
        if use_device:
            from .plot import load_plot_config

            want_plots = args.plot or ("plots" in config)
            plot_config = None
            if want_plots:
                try:
                    plot_config = load_plot_config(
                        config, device, fallback_output_dir=base_output_dir
                    )
                except ValueError as exc:
                    print(f"warning: plotting disabled: {exc}", file=error_stream)

            detections = _analyze_device(
                columns, device, method, method_params, plot_config, error_stream
            )
            _write_device_summary(device, detections, output_stream)

            csv_path = _write_results_csv(detections, base_output_dir)
            print(f"Results written to {csv_path}", file=output_stream)

            if plot_config is not None and detections:
                _render_plots(
                    columns, device, detections, plot_config, output_stream, error_stream
                )
        else:
            results = _generic_column_summary(
                columns, method, method_params, error_stream
            )
            _write_generic_summary(results, output_stream)

            csv_path = _write_results_csv(results, base_output_dir)
            print(f"Results written to {csv_path}", file=output_stream)
    except ValueError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
