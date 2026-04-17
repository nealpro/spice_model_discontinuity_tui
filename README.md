# spice_model_discontinuity

A Python toolkit for SPICE simulation workflows:
- **find** discontinuities in simulation data (CSV-first),
- **generate** simple NFET/PFET SPICE decks,
- **inject** synthetic discontinuities for testing.

## License

This project is released under the MIT License. See `LICENSE`.

# Getting started

## Prerequisites

1. Python 3.11+  
2. [`uv`](https://docs.astral.sh/uv/) installed (Recommended, but optional)

## Environment setup (uv)

```bash
# from repository root
uv lock
uv venv
uv sync
```

Activate (optional, `uv run` works without activation):

```bash
source .venv/bin/activate
```

## Run the CLI

```bash
uv run python main.py -s 0.5 path/to/data.csv
```

You can also read from stdin for pipe-friendly Unix workflows:

```bash
cat path/to/data.csv | uv run python main.py -s 0.5
```

Or use the package script entrypoint:

```bash
uv run spice-find -s 0.5 path/to/data.csv
```

### `find` CLI behavior

- Requires `-s/--sensitivity` (must be > 0).
- Accepts an optional CSV input path with a header row.
- If no input path is provided, reads CSV data from stdin.
- Writes summary results to stdout and errors to stderr.

The toolkit modules are available from the package:

```python
from spice_discontinuity import find, generate, inject
```
