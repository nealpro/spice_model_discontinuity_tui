"""Focused Ids/Vgs plotting for SPICE discontinuity analysis.

Produces exactly four views:

    iv_full.jpg     — Ids vs Vgs, one curve per filtered group
    iv_zoom.jpg     — Ids vs Vgs, x-windowed around merged discontinuity regions
    fda2_full.jpg   — d²Ids/dVgs² vs Vgs, same groups
    fda2_zoom.jpg   — d²Ids/dVgs², same x-window as iv_zoom

Group filtering (family-of-curves) is driven by ``[plots.grouping]`` in the
user TOML config, mirroring the VBULK filter knobs the user has been using
manually. The zoom pair is skipped when no group flags any discontinuity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from devices import Device
from spice_discontinuity.find import DetectionResult

_TOL = 1e-6


def _lazy_plt():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "matplotlib is required for plotting; install it to use this feature."
        ) from exc
    return plt


@dataclass(frozen=True)
class PlotConfig:
    """All plot knobs. Populate via ``load_plot_config``."""

    output_dir: Path
    figsize: tuple[float, float] = (16.0, 9.0)
    dpi: int = 200
    ids_ylabel: str = r"$I_D$"
    ids_unit_scale: float = 1.0
    vgs_xlabel: str = r"$V_{GS}$ (V)"
    vgs_xlim: tuple[float, float] | None = None
    vgs_tick_step: float | None = None
    zoom_padding: float = 0.05
    zoom_merge_within: float = 0.02
    grouping_field: str | None = None      # semantic device field name
    grouping_column: str | None = None     # resolved CSV column name
    group_min: float | None = None
    group_max: float | None = None
    group_step: float | None = None
    group_skip: tuple[float, ...] = ()
    label_template: str = "{field} = {value:.3g}"
    title_prefix: str = ""


def _as_float_list(values: Any) -> list[float]:
    if values is None:
        return []
    return [float(v) for v in values]


def load_plot_config(config: Mapping[str, Any], device: Device | None) -> PlotConfig:
    """Read ``[plots]`` + ``[plots.grouping]`` from the TOML dict.

    The grouping ``field`` in TOML is a semantic device key (e.g.
    ``source_bulk_voltage``). It is resolved to a CSV column name through
    ``device.fields``. When no device is configured the grouping field is
    used verbatim as the CSV column name.
    """
    plots = dict(config.get("plots") or {})
    grouping_raw = dict(plots.pop("grouping", None) or {})

    output_dir_raw = plots.get("output_dir") or config.get("output", {}).get(
        "plots_dir"
    )
    if output_dir_raw is None:
        raise ValueError(
            "plot output directory not set; define [plots].output_dir or "
            "[output].plots_dir in config."
        )

    figsize = plots.get("figsize")
    figsize_tuple = tuple(_as_float_list(figsize)) if figsize else (16.0, 9.0)
    if len(figsize_tuple) != 2:
        raise ValueError("[plots].figsize must be a pair of numbers.")

    xlim_raw = plots.get("vgs_xlim")
    xlim = tuple(_as_float_list(xlim_raw)) if xlim_raw else None
    if xlim is not None and len(xlim) != 2:
        raise ValueError("[plots].vgs_xlim must be a pair of numbers.")

    semantic_field = grouping_raw.get("field")
    csv_column: str | None = None
    if semantic_field:
        if device is not None and semantic_field in device.fields:
            csv_column = device.fields[semantic_field]
        else:
            csv_column = semantic_field

    return PlotConfig(
        output_dir=Path(output_dir_raw),
        figsize=figsize_tuple,  # type: ignore[arg-type]
        dpi=int(plots.get("dpi", 200)),
        ids_ylabel=str(plots.get("ids_ylabel", r"$I_D$")),
        ids_unit_scale=float(plots.get("ids_unit_scale", 1.0)),
        vgs_xlabel=str(plots.get("vgs_xlabel", r"$V_{GS}$ (V)")),
        vgs_xlim=xlim,  # type: ignore[arg-type]
        vgs_tick_step=(
            float(plots["vgs_tick_step"]) if plots.get("vgs_tick_step") is not None
            else None
        ),
        zoom_padding=float(plots.get("zoom_padding", 0.05)),
        zoom_merge_within=float(plots.get("zoom_merge_within", 0.02)),
        grouping_field=semantic_field,
        grouping_column=csv_column,
        group_min=(
            float(grouping_raw["min"]) if grouping_raw.get("min") is not None else None
        ),
        group_max=(
            float(grouping_raw["max"]) if grouping_raw.get("max") is not None else None
        ),
        group_step=(
            float(grouping_raw["step"]) if grouping_raw.get("step") is not None
            else None
        ),
        group_skip=tuple(_as_float_list(grouping_raw.get("skip"))),
        label_template=str(
            grouping_raw.get("label_template", "{field} = {value:.3g}")
        ),
        title_prefix=str(plots.get("title_prefix", "")),
    )


def filter_groups(
    group_values: list[float], config: PlotConfig
) -> list[float]:
    """Apply min/max/step/skip filters from ``[plots.grouping]``.

    Mirrors the user's original filter snippet: inclusive range, optional
    step alignment relative to ``group_min``, explicit skip list.
    """
    out: list[float] = []
    step = config.group_step
    base = config.group_min if config.group_min is not None else (
        min(group_values) if group_values else 0.0
    )
    for value in sorted(group_values):
        if config.group_min is not None and value < config.group_min - _TOL:
            continue
        if config.group_max is not None and value > config.group_max + _TOL:
            continue
        if any(abs(value - s) < _TOL for s in config.group_skip):
            continue
        if step is not None and step > 0:
            multiple = round((value - base) / step)
            expected = base + multiple * step
            if abs(value - expected) > _TOL:
                continue
        out.append(value)
    return out


def _merge_intervals(
    intervals: list[tuple[float, float]], merge_within: float
) -> list[tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for lo, hi in intervals[1:]:
        prev_lo, prev_hi = merged[-1]
        if lo <= prev_hi + merge_within:
            merged[-1] = (prev_lo, max(prev_hi, hi))
        else:
            merged.append((lo, hi))
    return merged


def _discontinuity_windows(
    detections: Mapping[float, DetectionResult], config: PlotConfig
) -> list[tuple[float, float]]:
    x_values: list[float] = []
    for result in detections.values():
        if result.indices.size == 0 or result.x.size == 0:
            continue
        idx = result.indices[
            (result.indices >= 0) & (result.indices < result.x.size)
        ]
        if idx.size:
            x_values.extend(result.x[idx].tolist())
    if not x_values:
        return []

    x_min, x_max = min(x_values), max(x_values)
    span = x_max - x_min if x_max > x_min else max(abs(x_max), 1.0)
    pad = max(config.zoom_padding * span, config.zoom_merge_within)
    raw = [(v - pad, v + pad) for v in sorted(x_values)]
    return _merge_intervals(raw, config.zoom_merge_within)


def _apply_common_axes(ax, config: PlotConfig, xlim: tuple[float, float] | None):
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel(config.vgs_xlabel, fontsize=12)
    if xlim is not None:
        ax.set_xlim(*xlim)
        if config.vgs_tick_step:
            ax.set_xticks(
                np.arange(xlim[0], xlim[1] + config.vgs_tick_step / 2, config.vgs_tick_step)
            )


def _label_for(value: float, config: PlotConfig) -> str:
    try:
        return config.label_template.format(
            value=value, field=config.grouping_field or "group"
        )
    except (KeyError, IndexError):
        return f"{config.grouping_field or 'group'} = {value:.3g}"


def _plot_ids(
    ax,
    groups: Mapping[float, tuple[np.ndarray, np.ndarray]],
    detections: Mapping[float, DetectionResult],
    config: PlotConfig,
    xlim: tuple[float, float] | None,
    *,
    flag_markers: bool,
) -> None:
    for value in sorted(groups):
        vgs, ids = groups[value]
        ax.plot(
            vgs,
            ids * config.ids_unit_scale,
            marker="o",
            markersize=2.5,
            linewidth=1.2,
            label=_label_for(value, config),
        )
        if flag_markers:
            result = detections.get(value)
            if result is None or result.indices.size == 0 or result.x.size == 0:
                continue
            idx = result.indices[
                (result.indices >= 0) & (result.indices < result.x.size)
            ]
            if idx.size == 0:
                continue
            flagged_x = result.x[idx]
            flagged_y = np.interp(flagged_x, vgs, ids) * config.ids_unit_scale
            ax.scatter(
                flagged_x, flagged_y, color="red", s=28, zorder=5, label=None,
            )
    _apply_common_axes(ax, config, xlim)
    ax.set_ylabel(config.ids_ylabel, fontsize=12)


def _plot_fda2(
    ax,
    detections: Mapping[float, DetectionResult],
    config: PlotConfig,
    xlim: tuple[float, float] | None,
    *,
    flag_markers: bool,
) -> None:
    for value in sorted(detections):
        result = detections[value]
        if result.fda_2.size == 0:
            continue
        # fda_2 lives on x_mid2 (length x_mid3 + 1). Reconstruct x_mid2 by
        # extending x_mid3 one step to the left.
        if result.x.size >= 2:
            first = result.x[0] - (result.x[1] - result.x[0])
            x_mid2 = np.concatenate(([first], result.x))
        else:
            x_mid2 = result.x
        ax.plot(
            x_mid2[: result.fda_2.size],
            result.fda_2,
            linewidth=1.0,
            label=_label_for(value, config),
        )
        if flag_markers and result.indices.size:
            idx = result.indices[
                (result.indices >= 0) & (result.indices < result.x.size)
            ]
            if idx.size:
                # result.fda_2 index that aligns with x_mid3[i] is i+1.
                fda_indices = idx + 1
                fda_indices = fda_indices[fda_indices < result.fda_2.size]
                ax.scatter(
                    result.x[idx[: fda_indices.size]],
                    result.fda_2[fda_indices],
                    color="red",
                    s=28,
                    zorder=5,
                )
    _apply_common_axes(ax, config, xlim)
    ax.set_ylabel(r"$d^2 I_D / dV_{GS}^2$", fontsize=12)


def render_iv_plots(
    groups: Mapping[float, tuple[np.ndarray, np.ndarray]],
    detections: Mapping[float, DetectionResult],
    *,
    config: PlotConfig,
) -> list[Path]:
    """Render the four focused plots and return their paths.

    Zoom plots are skipped entirely when no group flagged any discontinuity.
    Returns the list of files actually written.
    """
    plt = _lazy_plt()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    if not groups:
        return []

    windows = _discontinuity_windows(detections, config)
    title_tag = f"{config.title_prefix} ".lstrip()

    def legend_title() -> str:
        return config.grouping_field or ""

    def _save(fig, ax, name: str, title: str) -> Path:
        ax.set_title(f"{title_tag}{title}", fontsize=14)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, title=legend_title(), fontsize=9, loc="best")
        fig.tight_layout()
        out = config.output_dir / name
        fig.savefig(out, dpi=config.dpi)
        plt.close(fig)
        return out

    written: list[Path] = []

    fig, ax = plt.subplots(figsize=config.figsize)
    _plot_ids(ax, groups, detections, config, config.vgs_xlim, flag_markers=True)
    written.append(_save(fig, ax, "iv_full.jpg", r"$I_D$ vs $V_{GS}$ (full)"))

    fig, ax = plt.subplots(figsize=config.figsize)
    _plot_fda2(ax, detections, config, config.vgs_xlim, flag_markers=True)
    written.append(
        _save(fig, ax, "fda2_full.jpg", r"$d^2 I_D/dV_{GS}^2$ (full)")
    )

    if windows:
        zoom_xlim = (windows[0][0], windows[-1][1])

        fig, ax = plt.subplots(figsize=config.figsize)
        _plot_ids(ax, groups, detections, config, zoom_xlim, flag_markers=True)
        written.append(
            _save(fig, ax, "iv_zoom.jpg", r"$I_D$ vs $V_{GS}$ (zoom)")
        )

        fig, ax = plt.subplots(figsize=config.figsize)
        _plot_fda2(ax, detections, config, zoom_xlim, flag_markers=True)
        written.append(
            _save(fig, ax, "fda2_zoom.jpg", r"$d^2 I_D/dV_{GS}^2$ (zoom)")
        )

    return written
