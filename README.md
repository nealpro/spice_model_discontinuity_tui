# spice_model_discontinuity

A Python toolkit for SPICE simulation workflows with a Textual TUI:
- **find** discontinuities in simulation data (CSV-first),
- **generate** simple NFET/PFET SPICE decks,
- **inject** synthetic discontinuities for testing,
- and run everything from a lightweight terminal menu.

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

## Run

```bash
uv run python main.py
```

Inside the TUI, use commands such as:
- `help`
- `ls`
- `find <index> [threshold]`
- `generate [nfet|pfet] [model] [width] [length] [output]`
- `inject`
- `misc`
- `quit`

The toolkit modules are available from the package:

```python
from spice_discontinuity import find, generate, inject
```
