"""Command-line interface for SPICE discontinuity tools."""

import argparse
import csv
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Sequence, TextIO

from devices import Device, active_device
from spice_discontinuity.find import (
    Discontinuity,
    detect_discontinuities_higher_order,
    find_discontinuities,
    get_discontinuity_indices,
)

CONFIG_PATH = Path("~/.config/spice_cli/config.toml").expanduser()


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
        required=False,
        default=None,
        help="Threshold for adjacent-point delta magnitude (must be > 0). "
        "Falls back to [detection].sensitivity in ~/.config/spice_cli/config.toml.",
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


def _analyze_columns(
    columns: dict[str, list[float]],
    threshold: float,
) -> dict[str, list[Discontinuity]]:
    return {
        column_name: find_discontinuities(values, threshold)
        for column_name, values in columns.items()
    }


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("_")
    return cleaned or "column"


def _resolve_vgs(
    column_name: str,
    columns: dict[str, list[float]],
    n: int,
    error_stream: TextIO,
):
    """Return the x-axis array for the column named ``column_name`` or a fallback arange."""
    import numpy as np

    if column_name and column_name in columns:
        return np.asarray(columns[column_name], dtype=float)
    if column_name:
        print(
            f"warning: independent column {column_name!r} not found in CSV; "
            "falling back to row index.",
            file=error_stream,
        )
    return np.arange(n, dtype=float)


def _emit_device_plots(
    columns: dict[str, list[float]],
    device: Device,
    sensitivity: float,
    plots_dir: Path,
    show: bool,
    error_stream: TextIO,
) -> int | None:
    """Device-aware plotting. Returns None if the CSV does not belong to this device."""
    import numpy as np

    from plot import plot_all_views

    if device.independent_column not in columns:
        return None
    if not any(csv_name in columns for _, csv_name in device.dependent_items()):
        return None

    plots_dir.mkdir(parents=True, exist_ok=True)

    plotted = 0
    for semantic, csv_name in device.dependent_items():
        if csv_name not in columns:
            print(
                f"warning: device field {device.name}.{semantic} = {csv_name!r} not in CSV; skipping.",
                file=error_stream,
            )
            continue
        values = columns[csv_name]
        if len(values) < 4:
            continue
        ids = np.asarray(values, dtype=float)
        vgs = _resolve_vgs(device.independent_column, columns, len(ids), error_stream)
        try:
            vgs_mid3, fda_2, final_score = detect_discontinuities_higher_order(vgs, ids)
        except (ValueError, ZeroDivisionError) as exc:
            print(
                f"warning: skipping plot for {device.name}.{semantic}: {exc}",
                file=error_stream,
            )
            continue
        idx = get_discontinuity_indices(final_score, sensitivity)
        column_tag = _safe_filename(f"{device.name}_{semantic}")
        plot_all_views(
            vgs_mid3,
            fda_2,
            final_score,
            idx,
            column=column_tag,
            plots_dir=plots_dir,
            threshold=sensitivity,
            title=f"{device.name}.{semantic} ({csv_name})",
            show=show,
        )
        plotted += 1

    return plotted


def _emit_generic_plots(
    columns: dict[str, list[float]],
    sensitivity: float,
    plots_dir: Path,
    show: bool,
    error_stream: TextIO,
) -> int:
    """Fallback when no device is configured: plot every numeric column against row index."""
    import numpy as np

    from plot import plot_all_views

    plots_dir.mkdir(parents=True, exist_ok=True)

    plotted = 0
    for column_name, values in columns.items():
        if len(values) < 4:
            continue
        ids = np.asarray(values, dtype=float)
        vgs = np.arange(len(ids), dtype=float)
        try:
            vgs_mid3, fda_2, final_score = detect_discontinuities_higher_order(vgs, ids)
        except (ValueError, ZeroDivisionError) as exc:
            print(
                f"warning: skipping plot for {column_name!r}: {exc}", file=error_stream
            )
            continue
        idx = get_discontinuity_indices(final_score, sensitivity)
        plot_all_views(
            vgs_mid3,
            fda_2,
            final_score,
            idx,
            column=_safe_filename(column_name),
            plots_dir=plots_dir,
            threshold=sensitivity,
            title=column_name,
            show=show,
        )
        plotted += 1

    return plotted


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

    config = _load_config()

    sensitivity = args.sensitivity
    if sensitivity is None:
        sensitivity = config.get("detection", {}).get("sensitivity")
    if sensitivity is None:
        print(
            "error: sensitivity required via -s/--sensitivity or [detection].sensitivity in config.",
            file=error_stream,
        )
        return 2
    if sensitivity <= 0:
        print("error: -s/--sensitivity must be greater than 0.", file=error_stream)
        return 2

    input_path = args.input

    try:
        if input_path and input_path != "-":
            with Path(input_path).open(encoding="utf-8", newline="") as handle:
                columns = _load_numeric_columns_from_stream(handle)
        else:
            is_tty = getattr(input_stream, "isatty", lambda: False)
            if is_tty():
                configured_files = config.get("inputs", {}).get("files") or []
                if configured_files:
                    with Path(configured_files[0]).open(
                        encoding="utf-8", newline=""
                    ) as handle:
                        columns = _load_numeric_columns_from_stream(handle)
                else:
                    print(
                        "error: no input provided. Pass a file path or pipe CSV data on stdin.",
                        file=error_stream,
                    )
                    return 2
            else:
                columns = _load_numeric_columns_from_stream(input_stream)

        results = _analyze_columns(columns, sensitivity)
        _write_summary(results, output_stream)

        plots_dir = config.get("output", {}).get("plots_dir")
        if plots_dir:
            show_interactive = bool(getattr(input_stream, "isatty", lambda: False)())
            try:
                device = active_device(config, override=args.device)
            except (KeyError, ValueError) as exc:
                print(f"error: {exc}", file=error_stream)
                return 2

            count: int | None = None
            if device is not None:
                count = _emit_device_plots(
                    columns,
                    device,
                    sensitivity,
                    Path(plots_dir),
                    show=show_interactive,
                    error_stream=error_stream,
                )
            if count is None:
                count = _emit_generic_plots(
                    columns,
                    sensitivity,
                    Path(plots_dir),
                    show=show_interactive,
                    error_stream=error_stream,
                )
            if count:
                print(
                    f"Saved {count * 4} plot(s) to {plots_dir}/",
                    file=output_stream,
                )

        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=error_stream)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
