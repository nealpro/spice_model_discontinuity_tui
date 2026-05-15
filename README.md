# discont-finder

![Version](https://img.shields.io/badge/version-0.1.5-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## TL;DR

**`discont-finder`** is a Python CLI toolkit that automatically detects anomalies ("discontinuities") in SPICE transistor simulation data. When a semiconductor simulation model misbehaves — producing sudden unexplained jumps or glitches in a device's current-voltage curve — this tool finds them in seconds, rather than requiring an engineer to manually scan thousands of data rows. Developed for NFET IV-curve validation and applied to real-world simulation datasets in collaboration with industry partners.

---

## Overview

### The Problem

SPICE models are the industry-standard way to simulate how transistors and other semiconductor devices behave before fabrication. A well-behaved model produces smooth, continuous current-voltage (IV) curves. When a model has a defect — whether from numerical instability, a broken interpolation table, or a physical modeling error — the output develops a *discontinuity*: a sharp, localized jump or kink that shouldn't be there.

Finding these defects manually is impractical. A single simulation sweep can produce hundreds of data points across dozens of bias conditions. A discontinuity might appear in only one curve, at a single voltage step, buried among otherwise clean data.

### What This Tool Does

`discont-finder` provides an end-to-end pipeline for discontinuity analysis:

1. **Detect** — a robust, statistics-based algorithm scans any CSV of simulation data and flags anomalies automatically, with near-zero false positives on healthy curves.
2. **Inject** — a fault-injection module plants synthetic discontinuities into clean data, enabling ground-truth validation of the detector.
3. **Generate** — a signal-generation module creates synthetic reference curves (polynomial, sinusoidal, exponential) for stress testing.
4. **Report** — results are written to a machine-readable `results.csv` with row-level traceability back to the original CSV, suitable for downstream analysis in Excel or scripts.
5. **Visualize** — optional IV-curve plots mark detected regions on both the full sweep and a zoomed view, with a companion second-derivative plot for algorithm transparency.

---

## Key Features

- **Robust statistical detection** — uses a MAD-normalized curvature-jump score, which is inherently scale-invariant. Healthy FET threshold transitions (natural curvature changes) stay below a score of ~20; real model discontinuities produce scores in the hundreds or higher.
- **Zero false positives** on 7 clean signal families in the test suite; 100% detection rate on injected faults across all tested curve types.
- **Tunable sensitivity** — conservative defaults (`sigma=50`, `min_prominence=20`) catch only unambiguous faults. Lower thresholds expose subtler anomalies.
- **Device-aware grouped analysis** — maps semantic field names (e.g., `gate_voltage`, `drain_current`) to raw CSV column names via YAML config. New device types require no code changes.
- **Fault injection** — three fault modes: persistent step, single-sample spike, and random multi-spike, each with optional seeding for reproducibility.
- **Synthetic signal generation** — polynomial, sinusoidal, and exponential generators for building controlled test datasets.
- **IV-curve plots** — full sweep and zoomed plots with discontinuity markers, second-derivative overlay; DC sweep only.
- **Pipeline-friendly** — reads from a file path or `stdin`; writes `results.csv` to a configurable output directory.
- **Benchmarked** — `detect_robust` processes 100,000 samples in ~3 ms and scales near-linearly in practice (O(N log N) theoretical bound).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Numerics | NumPy, SciPy (`find_peaks`) |
| Data I/O | pandas |
| Visualization | Matplotlib |
| Config | PyYAML |
| Package manager | uv |

---

## Project Structure

```
spice_discontinuity/    ← pure algorithm library (no CLI or I/O dependencies)
  find.py               ← MAD-normalized discontinuity detection
  inject.py             ← synthetic fault injection
  generate.py           ← test signal generation
spice_cli/              ← CLI entry point, orchestration, plotting, device I/O
docs/                   ← technical deep-dives, user guide, config reference
config_examples/        ← annotated YAML examples
tests/                  ← integration test suite
```

---

## Installation

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd spice_model_discontinuity
uv sync
uv tool install .
```

Verify the install:

```bash
discont-finder --help
```

---

## Quick Start

**Analyze a CSV file:**

```bash
discont-finder path/to/data.csv
```

**Pipe from stdin:**

```bash
cat path/to/data.csv | discont-finder -
```

**Enable IV-curve plots** (DC sweep data only):

```bash
discont-finder data.csv -p
```

**Inject synthetic faults and verify detection:**

```bash
# Plant 5 known spike faults into a clean file
discont-finder clean.csv --inject -o faulted.csv --count 5 --magnitude 1e-4 --seed 42

# Confirm the detector finds them
discont-finder faulted.csv -s 20
```

**Use a device profile** (enables grouped analysis and plots):

```bash
discont-finder data.csv --device FET -p
```

---

## CLI Reference

```
usage: discont-finder [options] [input]

positional:
  input                     CSV file path, or '-' for stdin

config:
  -c, --config PATH         YAML config file (default: ~/.config/spice_cli/config.yaml)
  --help-format TOPIC       Print format docs for TOPIC and exit
                            Topics: config, device, csv, plots

detection:
  -s, --sensitivity FLOAT   Robust sigma threshold (MAD z-score cutoff)
  --min-prominence FLOAT    Minimum peak prominence above surrounding valleys
  --min-separation INT      Minimum index spacing between flagged peaks

device:
  --device NAME             Override active device from config

output:
  -p, --plot                Render IV-curve plots (DC sweep only)

injection:
  --inject                  Enable injection mode
  -o, --output PATH         Output CSV path (required with --inject)
  --column COL              Column to corrupt
  --count N                 Number of spikes to inject
  --magnitude MAG           Spike magnitude
  --seed INT                RNG seed for reproducibility
```

Run `discont-finder --help-format <topic>` for detailed format documentation.

---

## Detection Algorithm

### Intuition

The detector measures how sharply a curve bends at each point, then asks: *is this particular bend dramatically larger than anything else in the dataset?* A real discontinuity — a sudden jump in current caused by a model defect — produces a spike in the bending signal that dwarfs the natural curvature variation of a healthy sweep. By using the Median Absolute Deviation (MAD) as a robust yardstick, the method stays reliable even when the overall signal scale varies across device types or bias conditions.

A healthy FET threshold transition is a real but *smooth* curvature change — it scores well below the default threshold. A broken model interpolation that introduces a step discontinuity scores in the hundreds or higher.

### Math

Given sorted samples $(x_i, y_i)$, the detector builds:

$$
f^{(1)}_i = \frac{y_{i+1} - y_i}{x_{i+1} - x_i}
\qquad
\bar{x}^{(1)}_i = \frac{x_i + x_{i+1}}{2}
$$

$$
f^{(2)}_i = \frac{f^{(1)}_{i+1} - f^{(1)}_i}{\bar{x}^{(1)}_{i+1} - \bar{x}^{(1)}_i}
\qquad
\bar{x}^{(2)}_i = \frac{\bar{x}^{(1)}_i + \bar{x}^{(1)}_{i+1}}{2}
$$

$$
j_i = \frac{f^{(2)}_{i+1} - f^{(2)}_i}{\max\left(\left|\bar{x}^{(2)}_{i+1} - \bar{x}^{(2)}_i\right|, \varepsilon\right)}
$$

$$
\hat{\sigma} = 1.4826 \cdot \mathrm{MAD}(j)
\qquad
s_i = \frac{|j_i|}{\hat{\sigma}}
$$

### Peak Filtering

Candidate peaks in $s_i$ are accepted only if they satisfy all three constraints simultaneously:

| Parameter | Default | Role |
|---|---|---|
| `sigma` (height) | 50 | Minimum MAD z-score to be flagged |
| `min_prominence` | 20 | Minimum rise above surrounding valleys — rejects clustered false positives |
| `min_separation` | 3 | Minimum index distance between flags — prevents burst reporting |

See [`docs/ROBUST.md`](docs/ROBUST.md) for the full derivation.

---

## Configuration

Config lives at `~/.config/spice_cli/config.yaml`. CLI flags always override config values. Pass `-c /path/to/config.yaml` to use a different file.

See [`config_examples/config.yaml`](config_examples/config.yaml) for a fully annotated example, and [`docs/config_reference.md`](docs/config_reference.md) for the complete key reference.

### Minimal working config

```yaml
analysis:
  device: "FET"

devices:
  FET:
    independent: "gate_voltage"
    gate_voltage: "V(X1.GATE,X1.SOURCE)"
    drain_current: "I(VDRAIN)"
```

### `detection`

| Key | Meaning |
|---|---|
| `sensitivity` | MAD z-score threshold (`sigma`). Default `50`. |
| `min_prominence` | Minimum peak prominence. Default `20`. |
| `min_separation` | Minimum index spacing between peaks. Default `3`. |

### `devices.<NAME>`

Each device table maps semantic names to CSV column names.

| Key | Meaning |
|---|---|
| `independent` | Field used as the x-axis |
| any other key | Dependent or grouping field; value is the raw CSV column name |

Example:

```yaml
devices:
  FET:
    independent: "gate_voltage"
    gate_voltage: "VGS"
    drain_current: "ID"
    source_bulk_voltage: "VSB"
```

### `plots`

| Key | Meaning |
|---|---|
| `output_dir` | Directory for generated plots |
| `figsize` | Figure size pair |
| `dpi` | Image resolution |
| `ylabel` | Y-axis label |
| `unit_scale` | Scale factor applied to current values (e.g. `1e6` for µA) |
| `xlabel` | X-axis label |
| `xlim` | Optional x-axis limits |
| `tick_step` | Optional x-axis tick spacing |
| `zoom_padding` | Padding around detected discontinuity regions |
| `zoom_merge_within` | Distance used to merge nearby zoom windows |
| `title_prefix` | Prefix added to plot titles |

### `plots.grouping`

| Key | Meaning |
|---|---|
| `column` | Raw CSV column name used to group curves |
| `min` | Inclusive lower bound for plotted groups |
| `max` | Inclusive upper bound |
| `step` | Allowed spacing between groups |
| `skip` | Explicit list of group values to omit |
| `label_template` | Legend label format string |

### `io`

| Key | Meaning |
|---|---|
| `output_dir` | Base directory for `results.csv` and all generated files |
| `inputs` | Ordered list of CSV files to use when stdin is interactive |

---

## Output

### `results.csv`

Always written to the output directory. One row per detected discontinuity.

| Column | Meaning |
|---|---|
| `field` | Semantic field name (device mode) or raw CSV column (generic mode) |
| `group_field` | Name of the grouping axis, if configured |
| `group` | Value of the grouping variable (e.g. bulk voltage in V) |
| `input_row` | 1-based row in the original CSV — jump directly to the suspect row in a spreadsheet |
| `x_value` | Independent-axis value where the discontinuity was detected |
| `y_value` | Dependent-axis value at that point |
| `score` | MAD z-score. Threshold is 50 by default; scores in the hundreds = unambiguous fault |
| `threshold` | Minimum score required to flag a point |
| `method` | Detection algorithm (always `robust`) |

**Worked example:**

```
drain_current, source_bulk_voltage, 0, 312, 0.255, 3.47e-05, 334799, 5, robust
```

- **field** = `drain_current` → flagged column is I_D
- **group** = `0` → V_SB = 0 V curve
- **input_row** = `312` → row 312 in the original CSV
- **x_value** = `0.255` → discontinuity near V_GS = 0.255 V (close to threshold voltage)
- **score** = `334,799` → ~67,000× above threshold; an unambiguous fault

See [`docs/results_interpretation.md`](docs/results_interpretation.md) for a full column reference and interpretation guidance.

### Plot files

Generated with `-p` or when a `[plots]` section is present in config. DC sweep data only.

| File | Contents |
|---|---|
| `iv_full.jpg` | I_D vs V_GS, all bias groups, with discontinuity markers |
| `fda2_full.jpg` | d²I_D/dV_GS² vs V_GS — the raw signal the detector scores |
| `iv_zoom.jpg` | I_D zoomed to detected discontinuity regions |
| `fda2_zoom.jpg` | d²I_D/dV_GS² zoomed (omitted if no discontinuities found) |

---

## Testing & Validation

The test suite covers two orthogonal properties of the detector: it must find real faults, and it must not invent them.

| Suite | Signals tested | Result |
|---|---|---|
| No false positives (clean signals) | Linear, quadratic, cubic polynomials; low- and high-frequency sinusoids; slow and fast exponentials | **7/7 pass — zero false positives** |
| Detection on injected faults | Same 7 signal families with a step fault injected at the midpoint | **7/7 pass — 100% detection rate** |

**14 / 14 tests pass.**

Run the suite:

```bash
python -m pytest tests/ -v
```

### Performance

Benchmarked with pyperf on Apple Silicon (Python 3.14, arm64):

| N samples | `detect_robust` time |
|---|---|
| 1,000 | ~121 µs |
| 10,000 | ~333 µs |
| 100,000 | ~3 ms |

Scales near-linearly in practice (O(N log N) theoretical bound; NumPy's `introselect` makes median computation effectively O(N)). See [`docs/performance_study.md`](docs/performance_study.md) for full benchmark tables and complexity analysis.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/ROBUST.md`](docs/ROBUST.md) | Full detection algorithm derivation and parameter definitions |
| [`docs/user_guide.md`](docs/user_guide.md) | Installation, workflows, troubleshooting |
| [`docs/config_reference.md`](docs/config_reference.md) | Complete YAML config key reference |
| [`docs/results_interpretation.md`](docs/results_interpretation.md) | How to read and act on `results.csv` |
| [`docs/performance_study.md`](docs/performance_study.md) | Benchmarks and empirical complexity analysis |
| [`docs/algorithms_study.md`](docs/algorithms_study.md) | Theoretical complexity of all library modules |

---

## License

Released under the [MIT License](LICENSE).
