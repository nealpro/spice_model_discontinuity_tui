"""Command-line interface for SPICE discontinuity tools."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence, TextIO

import numpy as np

from devices import Device, active_device
from spice_discontinuity.find import (
    DetectionResult,
    detect as find_detect,
)

CONFIG_PATH = Path("~/.config/spice_cli/config.toml").expanduser()

VALID_METHODS = ("simple", "higher_order", "robust")
DEFAULT_METHOD = "robust"


def _load_config() -> dict[str, Any]:
    """Load TOML config from the user config path, or return empty dict."""
    try:
        with CONFIG_PATH.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spice-find",
        description="Find discontinuities in CSV numeric columns.",
    )
    parser.add_argument(
        "-s",
        "--sensitivity",
        type=float,
        default=None,
        help="For simple/higher_order: raw score threshold (> 0). "
        "For robust: σ multiplier on MAD (default 8). "
        "Falls back to [detection].sensitivity in ~/.config/spice_cli/config.toml.",
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
        help="Robust method only: minimum z-score prominence for a flagged peak "
        "(default 20.0; also from [detection].min_prominence).",
    )
    parser.add_argument(
        "--min-separation",
        type=int,
        default=None,
        help="Robust method only: minimum index gap between flagged peaks "
        "(default 3; also from [detection].min_separation).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Override the active device name (otherwise uses [analysis].device from config).",
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


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("_")
    return cleaned or "column"


def _resolve_method_params(
    method: str,
    sensitivity: float | None,
    min_prominence: float | None,
    min_separation: int | None,
    detection_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Translate CLI/config values into kwargs for ``find.detect``."""
    if method in {"simple", "higher_order"}:
        if sensitivity is None:
            raise ValueError(
                f"method '{method}' requires -s/--sensitivity or [detection].sensitivity."
            )
        if sensitivity <= 0:
            raise ValueError("-s/--sensitivity must be greater than 0.")
        return {"threshold": float(sensitivity)}

    # robust
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

    Returns ``{semantic_field: {group_value: DetectionResult}}``.
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
            # y === x (to float tolerance) means this field is a redundant
            # alias of the independent axis — skip.
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
    """Run detection on every numeric column vs row index (no device config)."""
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
                f"  group={gtag}: {result.indices.size} at x=[{x_str}] (method={result.method}, thr={result.threshold:.3g})",
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
    config: dict[str, Any],
    output_stream: TextIO,
    error_stream: TextIO,
) -> None:
    """Render the four focused plots for each analyzed dependent field."""
    from plot import load_plot_config, render_iv_plots

    try:
        plot_config = load_plot_config(config, device)
    except ValueError as exc:
        print(f"warning: plotting disabled: {exc}", file=error_stream)
        return

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

        groups_to_plot = {
            k: groups[k] for k in selected if k in groups
        }
        dets_to_plot = {
            k: per_group[k] for k in selected if k in per_group
        }
        if not groups_to_plot:
            continue

        # One subfolder per analyzed field to avoid overwrites.
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
    # Imported lazily to keep matplotlib off the critical path for tests.
    from plot import filter_groups

    return filter_groups(values, plot_config)


def _with_output_dir(plot_config, new_dir: Path):
    from dataclasses import replace

    return replace(plot_config, output_dir=new_dir)


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

    config = _load_config()
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

    try:
        if use_device:
            # Load the plot config early so grouping decisions stay consistent
            # between the analysis loop and the plotter.
            from plot import load_plot_config

            plot_config = None
            try:
                plot_config = load_plot_config(config, device)
            except ValueError:
                plot_config = None

            detections = _analyze_device(
                columns, device, method, method_params, plot_config, error_stream
            )
            _write_device_summary(device, detections, output_stream)
            if plot_config is not None and detections:
                _render_plots(
                    columns, device, detections, config, output_stream, error_stream
                )
        else:
            results = _generic_column_summary(
                columns, method, method_params, error_stream
            )
            _write_generic_summary(results, output_stream)
    except ValueError as exc:
        print(f"error: {exc}", file=error_stream)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
