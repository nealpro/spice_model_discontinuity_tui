# Config Reference

## File Location

| | Path |
|---|---|
| Default | `~/.config/spice_cli/config.toml` |
| Override | `spice-cli -c /path/to/config.toml` |
| Format | [TOML](https://toml.io) |

CLI flags take priority over all config values.

---

## `[output]`

Base directory for all generated files (results CSV and plots).

| Key | Type | Default | Description |
|---|---|---|---|
| `output_dir` | string | `spice_cli_output/` in cwd | Base output directory for results and plots |
| `plots_dir` | string | — | Legacy alias; used as a fallback if `output_dir` is not set |

```toml
[output]
output_dir = "spice_cli_output"
```

When neither key is set, output goes to `spice_cli_output/` under the current working directory.

---

## `[detection]`

Default detection parameters. CLI flags override these.

| Key | Type | Default | Applies to |
|---|---|---|---|
| `method` | string | `"robust"` | All methods |
| `sensitivity` | float | 50.0 (robust), required (simple/higher_order) | All methods |
| `min_prominence` | float | 20.0 | `robust` only |
| `min_separation` | int | 3 | `robust` only |

```toml
[detection]
method         = "robust"
sensitivity    = 50.0
min_prominence = 20.0
min_separation = 3
```

- **`method`**: `"simple"` | `"higher_order"` | `"robust"`. See [SIMPLE.md](SIMPLE.md), [HIGHER_ORDER.md](HIGHER_ORDER.md), [ROBUST.md](ROBUST.md).
- **`sensitivity`**: For `simple`/`higher_order`, a raw score threshold (must be > 0). For `robust`, the MAD-z-score threshold (sigma multiplier).
- **`min_prominence`**: Robust only. Minimum height a peak must rise above the surrounding valleys to be flagged. Prevents clustered false positives.
- **`min_separation`**: Robust only. Minimum index distance between two flagged peaks.

---

## `[inputs]`

Fallback input files used when no file argument is given and stdin is an interactive terminal.

| Key | Type | Description |
|---|---|---|
| `files` | array of strings | CSV file paths; the first entry is used |

```toml
[inputs]
files = ["data/nmos.csv"]
```

---

## `[analysis]`

| Key | Type | Description |
|---|---|---|
| `device` | string | Name of the active `[devices.<NAME>]` table |

```toml
[analysis]
device = "FET"
```

Override per-run with `--device NAME`.

---

## `[devices.<NAME>]`

Maps semantic field names to CSV column headers. Add a new device by adding a new table — no code change required.

**Required key:**

| Key | Type | Description |
|---|---|---|
| `independent` | string | Name of the field (within this same table) used as the x-axis |

**All other string-valued keys** are treated as dependent fields:

```
<semantic_name> = "<CSV column header>"
```

Column name matching is **case-sensitive and exact**, including spaces and parentheses. LTspice-style names like `V(X1.GATE,X1.SOURCE)` are supported.

```toml
[devices.NFET]
independent         = "gate_voltage"
gate_voltage        = "V(X1.GATE,X1.SOURCE)"
drain_current       = "I(VDRAIN)"
source_bulk_voltage = "V(X1.SOURCE,X1.BULK)"
```

In this example, `gate_voltage` is the x-axis; `drain_current` and `source_bulk_voltage` are the fields analyzed for discontinuities.

---

## `[plots]`

> **Note:** Plotting is only supported for DC sweep data.
>
> Plots are generated when the `-p`/`--plot` flag is passed **or** when this section is present in config. Without a `[plots]` section and without `-p`, no plots are written.

| Key | Type | Default | Description |
|---|---|---|---|
| `output_dir` | string | `<output_dir>/plots/` | Directory for JPEG plot files |
| `figsize` | [float, float] | `[16.0, 9.0]` | Figure dimensions in inches |
| `dpi` | int | `200` | Plot resolution |
| `ids_ylabel` | string | `"$I_D$"` | Y-axis label (supports LaTeX) |
| `ids_unit_scale` | float | `1.0` | Multiplier on y-axis values (e.g. `1e6` for µA) |
| `vgs_xlabel` | string | `"$V_{GS}$ (V)"` | X-axis label (supports LaTeX) |
| `vgs_xlim` | [float, float] | auto | X-axis limits |
| `vgs_tick_step` | float | auto | X-axis tick spacing |
| `zoom_padding` | float | `0.05` | Fractional padding around zoom windows |
| `zoom_merge_within` | float | `0.02` | Merge zoom windows within this x-distance |
| `title_prefix` | string | `""` | Prefix prepended to each plot title |

```toml
[plots]
output_dir      = "spice_plots"
figsize         = [16, 9]
dpi             = 200
ids_ylabel      = "$I_D$ (µA)"
ids_unit_scale  = 1e6
vgs_xlabel      = "$V_{GS}$ (V)"
vgs_xlim        = [0.0, 1.8]
vgs_tick_step   = 0.2
title_prefix    = "NFET"
```

### Output files

Four JPEG files are written per analyzed field:

| File | Content |
|---|---|
| `iv_full.jpg` | I_D vs V_GS — full sweep with discontinuity markers |
| `fda2_full.jpg` | d²I_D/dV_GS² — full sweep |
| `iv_zoom.jpg` | I_D vs V_GS — zoomed to discontinuity regions |
| `fda2_zoom.jpg` | d²I_D/dV_GS² — zoomed (omitted if no discontinuities found) |

---

## `[plots.grouping]`

Filters which group values are plotted and controls their curve labels. Used for family-of-curves sweeps (e.g. varying bulk voltage).

| Key | Type | Description |
|---|---|---|
| `field` | string | Semantic field name from `[devices.<NAME>]` used to group curves |
| `min` | float | Exclude groups below this value |
| `max` | float | Exclude groups above this value |
| `step` | float | Only include groups at multiples of this interval from `min` |
| `skip` | array | Specific group values to exclude |
| `label_template` | string | Python format string; `{field}` and `{value:.Ng}` available |

Filter chain order: **min → max → skip → step**.

Use `{{ }}` to escape literal braces in LaTeX label strings.

```toml
[plots.grouping]
field          = "source_bulk_voltage"
min            = 0.0
max            = 1.5
step           = 0.1
skip           = []
label_template = "$V_{{SB}} = {value:.2f}$ V"
```

---

## Minimal Working Config

```toml
[analysis]
device = "FET"

[devices.FET]
independent   = "gate_voltage"
gate_voltage  = "V(X1.GATE,X1.SOURCE)"
drain_current = "I(VDRAIN)"
```

Detection uses `robust` defaults. Results go to `spice_cli_output/results.csv`. No plots are generated unless `-p` is passed.

---

## Full Annotated Example

See [`config_examples/config.toml`](../config_examples/config.toml) for a complete example with all sections populated.
