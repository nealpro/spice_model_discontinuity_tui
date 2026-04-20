# Code Organization

## Overview

`spice_model_discontinuity` is structured as two Python packages with a shared entry point:

| Package | Role |
|---|---|
| `spice_discontinuity/` | Core detection library — no CLI dependency |
| `spice_cli/` | CLI tool — uses the core library for I/O, config, and plotting |

The entry point `spice-cli` (defined in `pyproject.toml`) maps to `spice_cli.main()`.

---

## Package: `spice_discontinuity`

Pure library. Has no knowledge of the CLI, config files, or plotting.

### `find.py` — Detection algorithms

Unified dispatch via `detect(method, x, y, **params)` → `DetectionResult`.

| Method | Algorithm | When to use |
|---|---|---|
| `simple` | `\|y_i − y_{i−1}\| ≥ T` | Clean, uniformly-scaled data |
| `higher_order` | 2nd-derivative ratio score | Moderate noise tolerance |
| `robust` ★ | MAD-normalized curvature-jump + peak filtering | Default; adapts to signal scale |

**`DetectionResult` fields:**

| Field | Description |
|---|---|
| `x` | Independent axis grid |
| `fda_2` | Second derivative array |
| `score` | Per-point sensitivity score |
| `indices` | Indices of flagged peaks |
| `threshold` | Applied cutoff value |
| `method` | Algorithm name used |

**Supporting functions:**

- `score_series(x, y)` — compute raw robust score series
- `load_csv_numeric_columns(path)` — load CSV into `dict[str, list[float]]`
- `_mad(values)` — median absolute deviation

### `inject.py` — Fault injection

Creates test data with known discontinuities for validating detector sensitivity.

| Function | Description |
|---|---|
| `inject_step(values, index, magnitude)` | Persistent offset from `index` onward |
| `inject_spike(values, index, magnitude)` | Single-sample spike |
| `inject_random_spikes(values, count, magnitude, seed)` | Randomly placed spikes |
| `inject_faults(df, fault_percentage)` | DataFrame fault cycling (jump / noise / clipping) |

### `generate.py` — Stub

Reserved for future synthetic SPICE data generation.

---

## Package: `spice_cli`

Depends on `spice_discontinuity`. Handles argument parsing, TOML config, device semantics,
and matplotlib plotting.

### `__init__.py` — Entry point

`main(argv, stdin, stdout, stderr)` runs the full user workflow:

1. Load `~/.config/spice_cli/config.toml`
2. Parse CLI arguments (override config)
3. Load CSV (file path or stdin)
4. Resolve active device (if configured)
5. Dispatch to **detection** or **injection** mode
6. Render plots (if plot config valid)
7. Print results summary; return exit code

**Detection mode** (default):
- With device → semantic field mapping, per-field grouped analysis, optional 4 plots
- Without device → generic column-by-column analysis

**Injection mode** (`--inject`):
- Insert synthetic spikes into a CSV column and write the modified file

### `devices.py` — Device field mapping

Enables semantic references such as `drain_current` instead of raw CSV column names.

| Component | Description |
|---|---|
| `Device` | dataclass: `name`, `independent`, `fields` |
| `load_devices(config)` | Parse all `[devices.<NAME>]` TOML tables |
| `active_device(config, override)` | Resolve active device (CLI > config > None) |

### `plot.py` — IV curve plotting

Generates four JPEG plots per run when a device and output directory are configured.

| Output file | Content |
|---|---|
| `iv_full.jpg` | Full I_D vs V_GS with discontinuity markers |
| `fda2_full.jpg` | Full d²I_D/dV_GS² |
| `iv_zoom.jpg` | I_D zoomed to discontinuity regions |
| `fda2_zoom.jpg` | d²I_D/dV_GS² zoomed |

`PlotConfig` stores all matplotlib customization. `load_plot_config(config, device)` parses
the `[plots]` and `[plots.grouping]` TOML sections.

---

## Configuration

User config: `~/.config/spice_cli/config.toml`. CLI flags override all config values.

| Section | Purpose |
|---|---|
| `[detection]` | Default method, sensitivity, prominence, separation |
| `[analysis]` | Active device name |
| `[devices.<NAME>]` | Semantic name → CSV column mappings |
| `[plots]` | Figure dimensions, labels, zoom params |
| `[plots.grouping]` | Family-of-curves group filtering |
| `[output]` | Default plot output directory |
| `[inputs]` | Fallback CSV files for interactive terminal |

---

## File Map

```
spice_model_discontinuity/
├── pyproject.toml               Entry points, dependencies
├── README.md                    Quick-start and config reference
├── main.py                      Thin wrapper → spice_cli.main()
├── spice_discontinuity/         Core library (no CLI dependency)
│   ├── __init__.py              Exports: find, generate, inject modules
│   ├── find.py                  Three detection algorithms + dispatch
│   ├── inject.py                Fault injection utilities
│   └── generate.py              [Stub] Synthetic data generator
├── spice_cli/                   CLI tool
│   ├── __init__.py              CLI entry point: main()
│   ├── devices.py               Device field-mapping abstractions
│   └── plot.py                  matplotlib IV curve rendering
├── docs/                        Algorithm and project documentation
│   ├── SIMPLE.md                Simple detector math
│   ├── HIGHER_ORDER.md          Higher-order derivative detector math
│   └── ROBUST.md                Robust MAD-based detector math
├── config_examples/             Example TOML configurations
│   ├── config.toml              Full example (robust method)
│   └── simple.toml              Simple method example
└── tests/
    ├── test_cli.py              Integration tests (4 cases)
    └── files/                   Test data
```

---

## Data Flow

```
CSV (file or stdin) + CLI flags + ~/.config/spice_cli/config.toml
                         │
                  spice_cli.main()
          ┌──────────────┼──────────────┐
    inject.py       devices.py        plot.py
    (--inject)       (fields)      (rendering)
          │               │              │
    faulted CSV      find.detect()    4 JPEGs
                    ┌────┼────┐
                 simple h.o. robust★
                         │
                  DetectionResult
                         │
                   stdout summary
```
