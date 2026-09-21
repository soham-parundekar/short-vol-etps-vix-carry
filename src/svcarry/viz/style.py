"""Shared figure style so every chart in the report reads as one system.

Design rules enforced here, rather than left to each figure:

* **Fixed categorical order, never cycled.** Series colours are assigned from a
  fixed list in order. A ninth series is not a new hue - it folds into "other" or
  the chart becomes small multiples.
* **Colour is never the only encoding.** Line style varies alongside hue, so the
  figures survive greyscale printing and colour-vision deficiency.
* **One y-axis.** There is no helper here for a secondary axis, deliberately. Two
  measures on different scales become two panels or an indexed common base.
* **Recessive chrome.** Grid and spines sit well behind the data; text uses ink
  colours, never a series colour.
* **Sequential means one hue, light to dark. Diverging means two hues with a
  neutral grey midpoint.** No rainbow maps anywhere.

The palette below was validated for colour-vision deficiency and for separation
under normal vision: the first six slots clear the adjacent-pair gates (worst
adjacent CVD ΔE 9.1, worst adjacent normal-vision ΔE 19.6), and the first three
clear the all-pairs gates, which is why scatter plots cap at three series. Three
slots sit below 3:1 contrast against the paper surface, so every figure that uses
them carries a legend and, where there are four or fewer series, direct labels -
identity is never left to colour alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

__all__ = [
    "PALETTE",
    "SEQUENTIAL",
    "DIVERGING",
    "INK",
    "LINESTYLES",
    "apply_style",
    "series_style",
    "new_figure",
    "direct_label",
    "shade_windows",
    "format_date_axis",
    "add_source",
    "save_figure",
    "greyscale_check",
]

#: Categorical hues, assigned in this order and never cycled.
PALETTE: list[str] = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

#: Secondary encoding, varied in step with the hue so the figures work in greyscale.
LINESTYLES: list[tuple] = [
    (0, ()),              # solid
    (0, (5, 2)),          # dashed
    (0, (1, 1.4)),        # dotted
    (0, (6, 2, 1, 2)),    # dash-dot
    (0, (3, 1.5)),        # short dash
    (0, (8, 2, 1, 2, 1, 2)),
    (0, (2, 2)),
    (0, (10, 3)),
]

#: One-hue sequential ramp, light to dark, for magnitude (heatmaps, densities).
SEQUENTIAL: list[str] = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]

#: Diverging pair with a neutral grey midpoint, for signed quantities.
DIVERGING: tuple[str, str, str] = ("#2a78d6", "#f0efec", "#e34948")

#: Text and chrome. Never a series colour.
INK = {
    "primary": "#0b0b0b",
    "secondary": "#52514e",
    "muted": "#8a8983",
    "grid": "#e4e3df",
    "surface": "#fcfcfb",
    "stress": "#efeeea",     # shading for stress windows
}


def sequential_cmap(name: str = "svcarry_seq") -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(name, SEQUENTIAL)


def diverging_cmap(name: str = "svcarry_div") -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(name, list(DIVERGING))


def apply_style() -> None:
    """Install the project's matplotlib defaults. Call once per script."""
    mpl.rcParams.update(
        {
            "figure.figsize": (9.0, 5.0),
            "figure.dpi": 130,
            "savefig.dpi": 220,
            "figure.facecolor": INK["surface"],
            "axes.facecolor": INK["surface"],
            "savefig.facecolor": INK["surface"],
            "savefig.bbox": "tight",
            "font.size": 10.5,
            "font.family": "sans-serif",
            "axes.titlesize": 12.5,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.titlepad": 12,
            "axes.labelsize": 10,
            "axes.labelcolor": INK["secondary"],
            "axes.edgecolor": INK["grid"],
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": INK["grid"],
            "grid.linewidth": 0.7,
            "grid.alpha": 1.0,
            "xtick.color": INK["muted"],
            "ytick.color": INK["muted"],
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "lines.linewidth": 1.7,
            "lines.markersize": 4.5,
            "lines.solid_capstyle": "round",
            "legend.frameon": False,
            "legend.fontsize": 9.5,
            "legend.labelcolor": INK["secondary"],
            "legend.handlelength": 2.4,
            "text.color": INK["primary"],
        }
    )
    mpl.rcParams["axes.prop_cycle"] = mpl.cycler(color=PALETTE)


def series_style(i: int, n_series: int = 1, scatter: bool = False) -> dict:
    """Colour and line style for series ``i`` (zero-based), in fixed order.

    Raises rather than cycling. A chart with more series than the palette supports
    is a chart that needs small multiples or an "other" bucket, and silently
    reusing a colour would make two different series look like one.
    """
    cap = 3 if scatter else len(PALETTE)
    if i >= cap:
        raise ValueError(
            f"series index {i} exceeds the {cap}-slot cap"
            + (" for all-pairs forms such as scatter; fold into 'other' or facet"
               if scatter else "; fold into 'other' or use small multiples")
        )
    return {"color": PALETTE[i], "linestyle": LINESTYLES[i]}


def new_figure(
    title: str, ylabel: str, xlabel: str = "", figsize=(9.0, 5.0), nrows: int = 1,
    height_ratios: Sequence[float] | None = None, sharex: bool = True,
):
    """A figure with the title and axis labels already set.

    Every figure in this project has a title that states what it shows and a y-axis
    label with units; making that the only way to create a figure is cheaper than
    remembering.
    """
    apply_style()
    if nrows == 1:
        fig, ax = plt.subplots(figsize=figsize)
        axes = [ax]
    else:
        fig, axes = plt.subplots(
            nrows, 1, figsize=figsize, sharex=sharex,
            gridspec_kw={"height_ratios": height_ratios or [1] * nrows},
        )
        axes = list(np.atleast_1d(axes))
    axes[0].set_title(title, color=INK["primary"])
    axes[0].set_ylabel(ylabel)
    if xlabel:
        axes[-1].set_xlabel(xlabel)
    return fig, (axes[0] if nrows == 1 else axes)


def direct_label(ax, x, y, text: str, color: str, dx: float = 0.0, **kw):
    """Label a series at its own end rather than only in the legend.

    Used whenever there are four or fewer series. It is also the relief required
    by the palette's contrast warning: the lighter hues are never asked to carry
    identity on their own.
    """
    ax.annotate(
        text, xy=(x, y), xytext=(6 + dx, 0), textcoords="offset points",
        va="center", ha="left", fontsize=9.5, color=color, fontweight="medium",
        clip_on=False, **kw,
    )


def shade_windows(ax, windows: "dict[str, tuple]", label: bool = True, alpha: float = 1.0):
    """Shade named stress windows behind the data.

    ``windows`` maps a label to ``(start, end)``; ``end`` may be ``None`` for an
    open window. Shading sits behind the grid so it never competes with the series.
    """
    for i, (name, (lo, hi)) in enumerate(windows.items()):
        x0 = pd.Timestamp(lo)
        x1 = pd.Timestamp(hi) if hi else ax.get_xlim()[1]
        ax.axvspan(x0, x1, color=INK["stress"], zorder=0, alpha=alpha, lw=0)
        if label:
            ax.annotate(
                name.replace("_", " "), xy=(x0, 1.0), xycoords=("data", "axes fraction"),
                xytext=(2, -10), textcoords="offset points", fontsize=8,
                color=INK["muted"], rotation=0, ha="left", va="top",
            )


def format_date_axis(ax, fmt: str | None = None) -> None:
    """Date ticks that never repeat a label.

    The previous version paired an automatic locator with a fixed ``%Y`` format, so
    whenever the locator chose half-yearly ticks every year was printed twice. The
    concise formatter labels each tick at the resolution it actually has. Pass
    ``fmt`` only for a deliberately fixed format.
    """
    import matplotlib.dates as mdates

    loc = mdates.AutoDateLocator(minticks=4, maxticks=10)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(
        mdates.DateFormatter(fmt) if fmt else mdates.ConciseDateFormatter(loc)
    )


def add_source(fig, text: str, width: int = 150) -> None:
    """Source / method note, bottom left, in muted ink, wrapped.

    Wrapped because figures are saved with a tight bounding box: a single long line
    widens the canvas to fit it and leaves the plot occupying half the image.
    """
    import textwrap

    fig.text(0.0, -0.02, textwrap.fill(text, width), fontsize=8, color=INK["muted"],
             ha="left", va="top")


def save_figure(fig, path: str | Path, also_pdf: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    if also_pdf:
        fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)
    return path


def greyscale_check(colors: Iterable[str]) -> list[tuple[str, str, float]]:
    """Relative-luminance gaps between colours, for the print case.

    Returns pairs whose luminance differs by less than 0.08, which is where a
    greyscale reader starts to lose them. Colour is never the only encoding in this
    project, so a close pair is a warning rather than a failure - but it should be
    known about rather than discovered in a printed copy.
    """
    def lum(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        rgb = [int(h[i: i + 2], 16) / 255.0 for i in (0, 2, 4)]
        rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    cols = list(colors)
    out = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            d = abs(lum(cols[i]) - lum(cols[j]))
            if d < 0.08:
                out.append((cols[i], cols[j], round(d, 4)))
    return out
