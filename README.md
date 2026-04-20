# spice_model_discontinuity

## About

`spice_model_discontinuity` is a small Python toolkit for SPICE workflow data:

- **find** discontinuities in CSV data
- **plot** analyzed IV curves and discontinuity markers when configured

## Getting started

### Install

Requires Python 3.11+.

```bash
uv sync
```

### Run the CLI

```bash
uv run spice-find path/to/data.csv
```

You can also read from stdin:

```bash
cat path/to/data.csv | uv run spice-find -
```

Useful flags:

- `--method simple|higher_order|robust`
- `-s/--sensitivity`
- `--min-prominence`
- `--min-separation`
- `--device`

Method details:

- [`docs/SIMPLE.md`](docs/SIMPLE.md)
- [`docs/HIGHER_ORDER.md`](docs/HIGHER_ORDER.md)
- [`docs/ROBUST.md`](docs/ROBUST.md)

If a device is configured, the CLI maps semantic fields from TOML into CSV
columns and analyzes each dependent field against the declared independent
axis. If you run it with no input path on an interactive terminal, it can fall
back to the first configured entry in `[inputs].files`. When plotting is
configured, it writes:

- `iv_full.jpg`
- `fda2_full.jpg`
- `iv_zoom.jpg`
- `fda2_zoom.jpg`

## Robust detection math

See [`docs/ROBUST.md`](docs/ROBUST.md) for the full derivation and parameter
definitions.

Robust mode treats discontinuities as outliers in a normalized curvature-jump
signal.

Given sorted samples $(x_i, y_i)$, the detector builds:

$$
f^{(1)}_i = \frac{y_{i+1} - y_i}{x_{i+1} - x_i}
$$

$$
f^{(2)}_i = \frac{f^{(1)}_{i+1} - f^{(1)}_i}{\bar{x}_{i+1} - \bar{x}_i}
\quad \text{where} \quad
\bar{x}_i = \frac{x_i + x_{i+1}}{2}
$$

$$
j_i = \frac{f^{(2)}_{i+1} - f^{(2)}_i}{\max\left(|\Delta \bar{x}_i|, \varepsilon\right)}
$$

$$
\sigma_{\mathrm{MAD}} = 1.4826 \cdot \mathrm{MAD}(j)
$$

$$
s_i = \frac{|j_i|}{\sigma_{\mathrm{MAD}}}
$$

MAD is median absolute deviation.

The CLI flags peaks in $s_i$ using:

- height $\ge \sigma$
- prominence $\ge$ `min_prominence`
- minimum separation $\ge$ `min_separation`

The default robust settings are conservative:

- `sigma = 50`
- `min_prominence = 20`
- `min_separation = 3`

## Configuration

User config lives at:

```text
~/.config/spice_cli/config.toml
```

CLI flags override config values.

`config_examples/config.toml` provides an example configuration.

### `detection`

Default detector settings.

| Key | Meaning |
| --- | --- |
| `method` | `simple`, `higher_order`, or `robust` (default) |
| `sensitivity` | Raw threshold for `simple`/`higher_order`; sigma threshold for `robust` |
| `min_prominence` | Robust peak prominence cutoff |
| `min_separation` | Robust minimum peak spacing |

### `analysis`

| Key | Meaning |
| --- | --- |
| `device` | Active device name from `[devices.<NAME>]` |

### `devices.<NAME>`

Each device table maps semantic names to CSV columns.

| Key | Meaning |
| --- | --- |
| `independent` | Semantic field used as the x-axis |
| any other string value | Dependent or grouping field mapped to a CSV column |

Example:

```toml
[devices.FET]
independent = "gate_voltage"
gate_voltage = "VGS"
drain_current = "ID"
source_bulk_voltage = "VSB"
```

### `plots`

| Key | Meaning |
| --- | --- |
| `output_dir` | Directory for generated plots (`[output].plots_dir` also works) |
| `figsize` | Figure size pair |
| `dpi` | Image resolution |
| `ids_ylabel` | Y-axis label for current plots |
| `ids_unit_scale` | Scale factor applied to current values |
| `vgs_xlabel` | X-axis label |
| `vgs_xlim` | Optional x-limits |
| `vgs_tick_step` | Optional x-axis tick spacing |
| `zoom_padding` | Padding around detected regions |
| `zoom_merge_within` | Distance used to merge nearby windows |
| `title_prefix` | Prefix added to plot titles |

### `plots.grouping`

| Key | Meaning |
| --- | --- |
| `field` | Semantic device field used to group curves |
| `min` | Inclusive lower bound for plotted groups |
| `max` | Inclusive upper bound for plotted groups |
| `step` | Optional allowed spacing between groups |
| `skip` | Explicit list of group values to omit |
| `label_template` | Legend label format string |

If a device is active, `field` is resolved through that device's mappings. If
no device is active, `field` is treated as a raw CSV column name.

### `output`

| Key | Meaning |
| --- | --- |
| `plots_dir` | Fallback plot output directory when `plots.output_dir` is unset |

### `inputs`

| Key | Meaning |
| --- | --- |
| `files` | Ordered list of CSV files to use when stdin is interactive |

## License

This project is released under the MIT License. See `LICENSE`.
