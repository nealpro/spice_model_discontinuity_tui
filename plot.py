"""Plotting helpers for SPICE discontinuity analysis.

Four per-view figures per analyzed column so zoomed and full-range plots can
be compared side-by-side in separate windows. Each view function creates,
saves, and (optionally) shows its own figure.
"""

from pathlib import Path

import numpy as np


def _lazy_plt():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "matplotlib is required for plotting; install it to use this feature."
        ) from exc
    return plt


def _pad_range(lo: float, hi: float, pad: float = 0.1) -> tuple[float, float]:
    span = hi - lo
    if span == 0:
        span = max(abs(hi), 1.0)
    return lo - span * pad, hi + span * pad


def _valid_flagged(flagged: np.ndarray, vgs: np.ndarray) -> np.ndarray:
    if flagged.size == 0:
        return flagged
    mask = (flagged >= 0) & (flagged < len(vgs))
    return flagged[mask]


def plot_fda2_full(
    vgs_mid2: np.ndarray,
    fda_2: np.ndarray,
    flagged_vgs: np.ndarray,
    *,
    title: str,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Full-range view of fda_2, with flagged locations drawn as scatter points."""
    plt = _lazy_plt()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(vgs_mid2, fda_2, label="d²Id/dVgs²", linewidth=0.8)
    if flagged_vgs.size:
        flagged_y = np.interp(flagged_vgs, vgs_mid2, fda_2)
        ax.scatter(
            flagged_vgs, flagged_y, color="red", s=10, alpha=0.6, label="flagged"
        )
    ax.set_xlabel("Vgs")
    ax.set_ylabel("fda_2")
    ax.set_title(f"{title} — fda_2 (full)")
    ax.legend(loc="best")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(str(output_path))
    if show:
        plt.show()
    return fig


def plot_fda2_zoom(
    vgs_mid2: np.ndarray,
    fda_2: np.ndarray,
    flagged_vgs: np.ndarray,
    *,
    title: str,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Zoomed view of fda_2 with y-axis clipped to robust percentiles."""
    plt = _lazy_plt()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(vgs_mid2, fda_2, label="d²Id/dVgs²", linewidth=0.8)
    if flagged_vgs.size:
        flagged_y = np.interp(flagged_vgs, vgs_mid2, fda_2)
        ax.scatter(
            flagged_vgs, flagged_y, color="red", s=10, alpha=0.6, label="flagged"
        )

    finite = fda_2[np.isfinite(fda_2)]
    if finite.size:
        lo, hi = np.nanpercentile(finite, [1, 99])
        if lo != hi:
            ax.set_ylim(*_pad_range(float(lo), float(hi)))

    ax.set_xlabel("Vgs")
    ax.set_ylabel("fda_2 (y clipped 1–99%)")
    ax.set_title(f"{title} — fda_2 (zoom)")
    ax.legend(loc="best")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(str(output_path))
    if show:
        plt.show()
    return fig


def plot_score_full(
    vgs_mid3: np.ndarray,
    final_score: np.ndarray,
    flagged: np.ndarray,
    threshold: float | None,
    *,
    title: str,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Full-range view of the discontinuity score."""
    plt = _lazy_plt()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(vgs_mid3, final_score, label="final_score", linewidth=0.8)
    if threshold is not None:
        ax.axhline(
            threshold, color="orange", linestyle="--", label=f"threshold={threshold:g}"
        )
    valid = _valid_flagged(flagged, vgs_mid3)
    if valid.size:
        ax.scatter(
            vgs_mid3[valid],
            final_score[valid],
            color="red",
            s=12,
            alpha=0.6,
            label="flagged",
        )
    ax.set_xlabel("Vgs")
    ax.set_ylabel("final_score")
    ax.set_title(f"{title} — score (full)")
    ax.legend(loc="best")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(str(output_path))
    if show:
        plt.show()
    return fig


def plot_score_zoom(
    vgs_mid3: np.ndarray,
    final_score: np.ndarray,
    flagged: np.ndarray,
    threshold: float | None,
    *,
    title: str,
    output_path: str | Path | None = None,
    show: bool = False,
):
    """Zoomed view of the score with y clipped at the 95th percentile."""
    plt = _lazy_plt()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(vgs_mid3, final_score, label="final_score", linewidth=0.8)
    if threshold is not None:
        ax.axhline(
            threshold, color="orange", linestyle="--", label=f"threshold={threshold:g}"
        )
    valid = _valid_flagged(flagged, vgs_mid3)
    if valid.size:
        ax.scatter(
            vgs_mid3[valid],
            final_score[valid],
            color="red",
            s=12,
            alpha=0.6,
            label="flagged",
        )

    finite = final_score[np.isfinite(final_score)]
    if finite.size:
        hi = float(np.nanpercentile(finite, 95))
        if hi > 0:
            ax.set_ylim(0, hi * 1.1)

    ax.set_xlabel("Vgs")
    ax.set_ylabel("final_score (y clipped ≤ 95%)")
    ax.set_title(f"{title} — score (zoom)")
    ax.legend(loc="best")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(str(output_path))
    if show:
        plt.show()
    return fig


def plot_all_views(
    vgs_mid3: np.ndarray,
    fda_2: np.ndarray,
    final_score: np.ndarray,
    discontinuity_indices: np.ndarray,
    *,
    column: str,
    plots_dir: str | Path,
    threshold: float | None = None,
    title: str | None = None,
    show: bool = False,
) -> list[Path]:
    """Save four per-view jpgs (fda2 full/zoom, score full/zoom) and optionally show them."""
    plots_dir = Path(plots_dir)
    plots_dir.mkdir(parents=True, exist_ok=True)

    vgs_mid3 = np.asarray(vgs_mid3)
    fda_2 = np.asarray(fda_2)
    final_score = np.asarray(final_score)
    discontinuity_indices = np.asarray(discontinuity_indices, dtype=int)

    # fda_2 lives on vgs_mid2; reconstruct by extending vgs_mid3 on the left.
    if len(vgs_mid3) >= 2:
        first = vgs_mid3[0] - (vgs_mid3[1] - vgs_mid3[0])
        vgs_mid2 = np.concatenate(([first], vgs_mid3))
    else:
        vgs_mid2 = vgs_mid3

    valid_idx = _valid_flagged(discontinuity_indices, vgs_mid3)
    flagged_vgs = vgs_mid3[valid_idx] if valid_idx.size else np.empty(0)

    plot_title = title or column
    paths = [
        plots_dir / f"{column}_fda2_full.jpg",
        plots_dir / f"{column}_fda2_zoom.jpg",
        plots_dir / f"{column}_score_full.jpg",
        plots_dir / f"{column}_score_zoom.jpg",
    ]

    plot_fda2_full(
        vgs_mid2, fda_2, flagged_vgs, title=plot_title, output_path=paths[0], show=show
    )
    plot_fda2_zoom(
        vgs_mid2, fda_2, flagged_vgs, title=plot_title, output_path=paths[1], show=show
    )
    plot_score_full(
        vgs_mid3,
        final_score,
        discontinuity_indices,
        threshold,
        title=plot_title,
        output_path=paths[2],
        show=show,
    )
    plot_score_zoom(
        vgs_mid3,
        final_score,
        discontinuity_indices,
        threshold,
        title=plot_title,
        output_path=paths[3],
        show=show,
    )
    return paths
