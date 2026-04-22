"""Entry point — loads config, runs robust detection on each CSV column."""

import sys
from pathlib import Path

import numpy as np

from config_handler import get_args, load_config, validate_config, resolve_input_paths
from find import load_csv_numeric_columns, detect_robust, _find_anomalous_row


def run(config: dict) -> None:
    files = resolve_input_paths(config["input_path"])
    sigma = max(5.0, 200.0 - config["sensitivity"] * 1.95)

    output_lines = []

    for file in files:
        print(f"Parsing {file}...")
        ignored = config["ignore_columns"]
        if ignored:
            output_lines.append(f"File: {file} (ignoring columns: {', '.join(ignored)})")
        else:
            output_lines.append(f"File: {file}")
        try:
            columns = load_csv_numeric_columns(file, ignore_columns=config["ignore_columns"])
        except ValueError as e:
            output_lines.append(f"  [Error]: {e}")
            continue

        for column_name, values in columns.items():
            if len(values) < 4:
                output_lines.append(f"  {column_name}: skipped (fewer than 4 samples)")
                continue

            x = np.arange(len(values), dtype=float)
            y = np.array(values, dtype=float)
            result = detect_robust(x, y, sigma=sigma)

            if result.indices.size == 0:
                output_lines.append(f"  {column_name}: no discontinuities detected")
            else:
                flagged_parts = []
                for i in result.indices:
                    row = _find_anomalous_row(y, int(round(result.x[i])))
                    flagged_parts.append(str(row + 2))
                flagged = ", ".join(flagged_parts)
                output_lines.append(f"  {column_name}: discontinuities at rows [{flagged}]")

    if config["output_file"]:
        Path(config["output_file"]).write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        print(f"Results written to {config['output_file']}")
    else:
        for line in output_lines:
            print(line)


if __name__ == "__main__":
    args = get_args()
    if not args.config:
        from config_handler import generate_template
        generate_template()
    raw = load_config(Path(args.config))
    config = validate_config(raw)
    print("Config loaded successfully.")
    run(config)
