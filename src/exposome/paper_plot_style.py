"""Publication-style matplotlib helpers adapted from ``astro-paper-plot-style``.

The visual language comes from the SN2021njo plotting skill: serif typography,
inward ticks, strong axes, compact legends, restrained functional colors, and
paired PDF/PNG exports. The helpers are domain-neutral so cohort and exposome
figures can share the style without importing astronomy-specific utilities.
"""

from __future__ import annotations

from pathlib import Path


FIG_SIZES = {
    "onecol": (3.4, 2.6),
    "paper_row": (6.95, 2.45),
    "twocol": (7.0, 4.5),
    "square": (7.0, 7.0),
}

COLORS = {
    "data": "black",
    "reference": "#FF7F0E",
    "secondary": "#1F77B4",
    "muted": "dimgray",
    "grid": "0.88",
}


def apply_astro_paper_style(profile: str = "paper", *, use_seaborn: bool = True) -> None:
    """Apply the shared paper style to subsequent matplotlib figures."""

    import matplotlib.pyplot as plt

    if profile not in {"paper", "compact"}:
        raise ValueError(f"Unknown style profile: {profile}")
    if use_seaborn:
        try:
            plt.style.use("seaborn-v0_8-paper")
        except OSError:
            pass

    if profile == "compact":
        small, medium, big = 8, 9, 10
        axes_lw = 1.4
        major_width, minor_width = 0.9, 0.6
        major_size, minor_size = 4.0, 2.0
    else:
        small, medium, big = 12, 14, 16
        axes_lw = 2.0
        major_width, minor_width = 1.5, 1.0
        major_size, minor_size = 6.0, 3.0

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Computer Modern", "DejaVu Serif"],
            "mathtext.fontset": "cm",
            "text.usetex": False,
            "axes.linewidth": axes_lw,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": True,
            "ytick.right": True,
            "xtick.minor.visible": True,
            "ytick.minor.visible": True,
            "xtick.major.width": major_width,
            "ytick.major.width": major_width,
            "xtick.minor.width": minor_width,
            "ytick.minor.width": minor_width,
            "xtick.major.size": major_size,
            "ytick.major.size": major_size,
            "xtick.minor.size": minor_size,
            "ytick.minor.size": minor_size,
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "legend.frameon": False,
        }
    )
    plt.rc("font", size=small)
    plt.rc("axes", labelsize=medium, titlesize=medium)
    plt.rc("xtick", labelsize=small)
    plt.rc("ytick", labelsize=small)
    plt.rc("legend", fontsize=max(small - 1, 7))
    plt.rc("figure", titlesize=big)


def set_inward_ticks(ax, *, categorical_axis: str | None = None) -> None:
    """Force inward ticks and disable meaningless minor categorical ticks."""

    from matplotlib.ticker import NullLocator

    ax.tick_params(axis="both", which="both", direction="in", top=True, right=True)
    ax.minorticks_on()
    if categorical_axis == "x":
        ax.xaxis.set_minor_locator(NullLocator())
    elif categorical_axis == "y":
        ax.yaxis.set_minor_locator(NullLocator())


def style_rank_axis(ax, *, categorical_axis: str = "y") -> None:
    """Apply restrained grid and tick conventions to a ranking axis."""

    set_inward_ticks(ax, categorical_axis=categorical_axis)
    numeric_axis = "x" if categorical_axis == "y" else "y"
    ax.grid(axis=numeric_axis, color=COLORS["grid"], linewidth=0.55, alpha=0.85)
    ax.grid(axis=categorical_axis, visible=False)
    ax.set_axisbelow(True)


def save_paper_figure(
    fig,
    path_stem: str | Path,
    *,
    png_dpi: int = 300,
    bbox_inches: str = "tight",
    pad_inches: float = 0.02,
) -> list[Path]:
    """Save a figure as publication-ready PDF and PNG."""

    stem = Path(path_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    outputs = [stem.with_suffix(".pdf"), stem.with_suffix(".png")]
    fig.savefig(outputs[0], bbox_inches=bbox_inches, pad_inches=pad_inches)
    fig.savefig(outputs[1], dpi=png_dpi, bbox_inches=bbox_inches, pad_inches=pad_inches)
    return outputs
