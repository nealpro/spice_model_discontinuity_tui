# User Guide

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone <repo>
cd spice_model_discontinuity
uv sync
```

Verify the entry point is available:

```bash
uv run spice-cli --help
```

---

## Quick Start

Analyze a CSV file:

```bash
uv run spice-cli data.csv
```

Pipe from stdin:

```bash
cat data.csv | uv run spice-cli -
```

The tool prints a per-column discontinuity summary to stdout. If a device is configured
and a plot output directory is set, it also writes four JPEG plots.

---

## Detection Methods

Select a method with `--method`. The default is `robust` (configurable).

### Simple (`--method simple`)

Flags consecutive samples whose absolute difference exceeds a threshold:

```
|y_i − y_{i−1}| ≥ T
```

Set `T` with `-s`/`--sensitivity`. Best for clean, uniformly-scaled data with no noise.

### Higher-Order (`--method higher_order`)

Flags points where the relative jump in the second finite-difference derivative exceeds a
threshold. More noise-tolerant than `simple`, but still requires explicit threshold tuning.

### Robust (`--method robust`) — recommended

Treats discontinuities as statistical outliers in a normalized curvature-jump signal.

Given sorted samples $(x_i, y_i)$:

1. Compute first differences: `f1_i = (y_{i+1} − y_i) / (x_{i+1} − x_i)`
2. Compute second differences: `f2_i` on midpoint grid
3. Compute curvature-jump signal: `j_i = (f2_{i+1} − f2_i) / Δx_mid`
4. Normalize: `s_i = |j_i| / (1.4826 × MAD(j))`
5. Flag peaks in `s_i` satisfying three constraints (height, prominence, separation)

The MAD normalization makes the score scale-invariant across different devices and
operating conditions.

**Robust-specific flags:**

| Flag | Default | Meaning |
|---|---|---|
| `-s`/`--sensitivity` | 50 | Minimum z-score height for a peak to be flagged |
| `--min-prominence` | 20 | Minimum peak prominence above surrounding valleys |
| `--min-separation` | 3 | Minimum index distance between flagged peaks |

The defaults are deliberately conservative. Lower `--sensitivity` to detect subtler
discontinuities; lower `--min-prominence` if peaks are real but close in magnitude to
the baseline.

---

## CLI Flags Reference

```
usage: spice-cli [options] [input]

positional:
  input                     CSV file path, or '-' for stdin

detection:
  --method {simple,higher_order,robust}
  -s, --sensitivity FLOAT   Threshold (simple/higher_order) or sigma (robust)
  --min-prominence FLOAT    Robust: minimum peak prominence
  --min-separation INT      Robust: minimum index spacing between peaks

device:
  --device NAME             Override active device from config

injection:
  --inject                  Enable injection mode
  -o, --output PATH         Output CSV path (required with --inject)
  --column COL              Column to corrupt
  --count N                 Number of spikes to inject
  --magnitude MAG           Spike magnitude
  --seed INT                RNG seed for reproducibility
```

---

## Devices

A *device* maps semantic field names to CSV column names and enables grouped analysis.
Without a device, the CLI analyzes all numeric columns against the row index.

### Defining a Device

In `~/.config/spice_cli/config.toml`:

```toml
[devices.FET]
independent = "gate_voltage"
gate_voltage        = "V(X1.GATE,X1.SOURCE)"
drain_current       = "I(VDRAIN)"
source_bulk_voltage = "V(X1.SOURCE,X1.BULK)"
```

The `independent` key names the field used as the x-axis. All other fields are treated as
dependent variables. If a field holds a grouping variable (e.g., bulk voltage), the CLI
groups curves by its unique values for both analysis and plotting.

### Activating a Device

In config:

```toml
[analysis]
device = "FET"
```

Or via flag (overrides config):

```bash
uv run spice-cli data.csv --device FET
```

**With a device active, the CLI:**
1. Resolves CSV columns through the device's field mappings
2. Analyzes each dependent field vs the independent axis
3. Groups results by the grouping column if one is configured under `[plots.grouping]`
4. Generates 4 plots if `[plots]` is configured with an output directory

---

## Configuration Reference

Config file: `~/.config/spice_cli/config.toml`  
CLI flags override all config values.  
See `config_examples/config.toml` for a full annotated example.

### `[detection]`

```toml
[detection]
method          = "robust"
sensitivity     = 50.0
min_prominence  = 20.0
min_separation  = 3
```

### `[analysis]`

```toml
[analysis]
device = "FET"
```

### `[devices.<NAME>]`

```toml
[devices.FET]
independent         = "gate_voltage"
gate_voltage        = "VGS"
drain_current       = "ID"
source_bulk_voltage = "VSB"
```

### `[plots]`

```toml
[plots]
output_dir      = "~/spice_plots"
figsize         = [12, 5]
dpi             = 150
ids_ylabel      = "I_D"
ids_unit_scale  = 1e3          # A → mA
vgs_xlabel      = "V_GS (V)"
vgs_xlim        = [-0.5, 1.5]
vgs_tick_step   = 0.25
zoom_padding    = 0.1
zoom_merge_within = 0.05
title_prefix    = "NMOS"
```

### `[plots.grouping]`

```toml
[plots.grouping]
field          = "source_bulk_voltage"
min            = -0.6
max            = 0.0
step           = 0.2
skip           = [-0.4]
label_template = "V_SB = {value:.2f} V"
```

`field` is resolved through the active device's mappings. If no device is active, it is
treated as a raw CSV column name.

### `[output]`

```toml
[output]
plots_dir = "~/spice_plots"   # fallback if plots.output_dir is unset
```

### `[inputs]`

```toml
[inputs]
files = ["data/nmos.csv", "data/pmos.csv"]
```

Used when no file is specified and stdin is an interactive terminal.

---

## Workflows

### Detect discontinuities in an IV sweep

```bash
uv run spice-cli data.csv --method robust --sensitivity 30
```

Lowering `--sensitivity` from the default of 50 catches subtler discontinuities.

### Analyze a FET sweep with plots

1. Configure device and plot settings in `~/.config/spice_cli/config.toml`.
2. Run:
   ```bash
   uv run spice-cli data.csv --device FET
   ```
3. Review stdout summary and the four plots written to `plots.output_dir`.

### Inject synthetic faults and verify detection

```bash
# Create test data with 5 known spikes
uv run spice-cli clean.csv --inject -o faulted.csv --count 5 --magnitude 1e-4 --seed 42

# Verify the detector finds them
uv run spice-cli faulted.csv --method robust -s 20
```

### Pipeline usage

```bash
cat simulation_output.csv | uv run spice-cli - --device FET
```

---

## Output

### Stdout summary (no device)

```
5 columns analyzed
  V:  0 discontinuities
  ID: 2 discontinuities at indices [142, 301]
  ...
```

### Stdout summary (with device)

```
Device: FET
3 fields analyzed
  drain_current: 2 discontinuities
  ...
```

### Plot files

| File | Description |
|---|---|
| `iv_full.jpg` | I_D vs V_GS, all bulk-voltage groups, with discontinuity markers |
| `fda2_full.jpg` | d²I_D/dV_GS² vs V_GS |
| `iv_zoom.jpg` | I_D zoomed to detected discontinuity regions |
| `fda2_zoom.jpg` | d²I_D/dV_GS² zoomed |

---

## Troubleshooting

**No discontinuities detected on data that has them:**
- Lower `--sensitivity` (default 50 is conservative)
- Try `--min-prominence 5` or `--min-separation 1`
- Run `--method simple -s 0.001` to confirm data is loading correctly

**Too many false positives:**
- Increase `--sensitivity`
- Increase `--min-prominence`
- Confirm the data is sorted by the independent axis

**Plots not generated:**
- `[plots] output_dir` must be set in config
- An active device must be configured via `[analysis] device`
- CSV column names must exactly match the values in `[devices.<NAME>]` (case-sensitive)

**Device fields not resolving:**
- Run without `--device` first to see raw column names from the CSV
- Compare column names against the values (not keys) in `[devices.<NAME>]`
