"""Reads, validates, and prints the SPICE discontinuity tool config."""

import argparse
import sys
from pathlib import Path

import yaml
from termcolor import colored


def print_error(message):
    print(colored(message, "red"))


def load_config(path: Path) -> dict:
    if not path.exists():
        print_error(f"[Error]: Config file not found: {path}")
        sys.exit(1)
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print_error(f"[Error]: Invalid YAML in {path}: {e}")
        sys.exit(1)
        return {}
    if not isinstance(data, dict):
        print_error("[Error]: Config file must contain a YAML mapping at the top level.")
        sys.exit(1)
        return {}
    return data


def validate_config(data):
    # input_path — required, str or list of str
    if "input_path" not in data:
        print_error("[Error]: Missing required field 'input_path'.")
        sys.exit(1)
        return {}

    input_path = data["input_path"]
    if isinstance(input_path, str):
        if not input_path.strip():
            print_error("[Error]: 'input_path' must not be empty.")
            sys.exit(1)
            return {}
    elif isinstance(input_path, list):
        if not input_path:
            print_error("[Error]: 'input_path' list must not be empty.")
            sys.exit(1)
            return {}
        for item in input_path:
            if not isinstance(item, str):
                print_error("[Error]: Every entry in 'input_path' must be a string.")
                sys.exit(1)
                return {}
    else:
        print_error("[Error]: 'input_path' must be a string or a list of strings.")
        sys.exit(1)
        return {}

    # sensitivity — required, numeric, > 0
    if "sensitivity" not in data:
        print_error("[Error]: Missing required field 'sensitivity'.")
        sys.exit(1)
        return {}

    sensitivity = data["sensitivity"]
    if not isinstance(sensitivity, (int, float)) or isinstance(sensitivity, bool):
        print_error("[Error]: 'sensitivity' must be a number.")
        sys.exit(1)
        return {}
    if not 0 <= sensitivity <= 100:
        print_error("[Error]: 'sensitivity' must be between 0 and 100.")
        sys.exit(1)
        return {}

    # ignore_columns — optional, list of str, defaults to []
    ignore_columns = data.get("ignore_columns") or []
    if isinstance(ignore_columns, str):
        ignore_columns = [ignore_columns]
    if not isinstance(ignore_columns, list):
        print_error("[Error]: 'ignore_columns' must be a list of strings.")
        sys.exit(1)
        return {}
    for item in ignore_columns:
        if not isinstance(item, str):
            print_error("[Error]: Every entry in 'ignore_columns' must be a string.")
            sys.exit(1)
            return {}

    # output_file — optional, str, defaults to None
    output_file = data.get("output_file", None)
    if output_file is not None and not isinstance(output_file, str):
        print_error("[Error]: 'output_file' must be a string.")
        sys.exit(1)
        return {}

    return {
        "input_path": input_path,
        "sensitivity": float(sensitivity),
        "ignore_columns": ignore_columns,
        "output_file": output_file,
    }


def resolve_input_paths(input_path):
    if isinstance(input_path, list):
        return [Path(p) for p in input_path]

    path = Path(input_path)

    if path.is_dir():
        files = list(path.rglob("*.csv"))
        if not files:
            print_error(f"[Error]: No CSV files found in directory: {path}")
            sys.exit(1)
            return []
        return files

    if path.is_file():
        return [path]

    print_error(f"[Error]: Input path does not exist: {path}")
    sys.exit(1)
    return []


def print_config(config: dict) -> None:
    print("Config loaded successfully.")
    print(f"  input_path:      {config['input_path']}")
    print(f"  sensitivity:     {config['sensitivity']}")
    print(f"  ignore_columns:  {config['ignore_columns']}")
    print(f"  output_file:     {config['output_file']}")


TEMPLATE_CONFIG = """\
input_path: "path/to/file_or_directory"

sensitivity: 50

ignore_columns:
  - COLUMN_NAME_1
  - COLUMN_NAME_2

output_file: "results.txt"
"""


def generate_template():
    output = Path("config.yaml") if not Path("config.yaml").exists() else Path("discontinuity_config.yaml")
    output.write_text(TEMPLATE_CONFIG, encoding="utf-8")
    print_error(f"A config file was not provided an outline will be at \"./{output}\"")
    print_error(f"Please fill out the outline and rerun with a -c {output} argument")
    sys.exit(0)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to config.yaml",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = get_args()
    if not args.config:
        generate_template()
    raw = load_config(Path(args.config))
    config = validate_config(raw)
    files = resolve_input_paths(config["input_path"])
    print_config(config)
    print(f"  resolved files:  {[str(f) for f in files]}")
