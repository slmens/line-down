"""Charts for the disruption finding, from analysis/output/results.json.

Usage: .venv/bin/python analysis/plot_effect.py
Writes analysis/output/effect_over_time.png and analysis/output/effect_by_group.png.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent / "output"
SURFACE, INK, INK2, GRID, REF = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#8a8984"
# one blue ramp, darkest = nearest (validated: ordinal, light mode)
RING_COLORS = {"0-250 m": "#184f95", "250-500 m": "#2a78d6", "500-1000 m": "#86b6ef"}

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def pct_axis(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0%}" if v else "0"))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def over_time(r):
    a, p = r["all"], r["placebo (no real disruption)"]
    x = [m + 7.5 for m in a["slots_minutes"]]  # plot each 15-min slot at its middle
    fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
    near = a["by_slot"]["0-250 m"]
    ax.fill_between(x, near["lo"], near["hi"], color=RING_COLORS["0-250 m"], alpha=0.12, linewidth=0)
    ax.plot(x, p["by_slot"]["0-250 m"]["lift"], color=REF, linewidth=1.5, linestyle=(0, (4, 3)),
            label="Fake disruptions, 0-250 m (method check)")
    for ring, color in RING_COLORS.items():
        v = a["by_slot"][ring]["lift"]
        ax.plot(x, v, color=color, linewidth=2, marker="o", markersize=4, label=ring)
        peak = max(range(len(v)), key=v.__getitem__)
        far = ring == "500-1000 m"  # sits under the other two lines, so label it below its point
        ax.annotate(f"{ring}  {v[peak]:+.0%}", (x[peak], v[peak]), xytext=(0, -14) if far else (10, 0),
                    textcoords="offset points", color=INK, fontsize=10, va="center", ha="center" if far else "left")
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.axvline(0, color=INK2, linewidth=0.8, linestyle=":")
    ax.text(2, ax.get_ylim()[1] * 0.97, "delay logged", color=INK2, fontsize=9, va="top")
    ax.set_xticks(range(-60, 181, 30))
    ax.set_xlabel("minutes from the subway delay")
    ax.set_ylabel("extra Bike Share trips vs a normal day")
    pct_axis(ax)
    ax.set_title(f"Bike Share trips near a subway disruption, by distance from the station\n"
                 f"{a['events']:,} delays of 10+ min, Lines 1/2/4, 2023-2026; shaded = 95% range (0-250 m)",
                 loc="left", color=INK, fontsize=12)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "effect_over_time.png")


def by_group(r):
    groups = ["all", "delay 10-19 min", "delay 20-59 min", "delay 60+ min",
              "rush hour (7-10am, 4-7pm weekdays)", "off-peak", "placebo (no real disruption)"]
    fig, ax = plt.subplots(figsize=(9, 5), dpi=200)
    offsets = {"0-250 m": -0.22, "250-500 m": 0, "500-1000 m": 0.22}
    for ring, color in RING_COLORS.items():
        for i, g in enumerate(groups):
            v = r[g]["first_hour"][ring]
            y = i + offsets[ring]
            ax.plot([v["lo"], v["hi"]], [y, y], color=color, linewidth=2, solid_capstyle="round")
            ax.plot(v["lift"], y, "o", color=color, markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.5,
                    label=ring if i == 0 else None)
    ax.set_yticks(range(len(groups)))
    ax.set_yticklabels([f"{g}  (n={r[g]['events']:,})" for g in groups], color=INK)
    ax.invert_yaxis()
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0%}" if v else "0"))
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel("extra trips in the first hour vs a normal day\n(dot = estimate, line = 95% range)")
    ax.set_title("First-hour effect by kind of disruption and distance", loc="left", color=INK, fontsize=12)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "effect_by_group.png")


if __name__ == "__main__":
    results = json.loads((OUT / "results.json").read_text())
    over_time(results)
    by_group(results)
    print("wrote", OUT / "effect_over_time.png", "and", OUT / "effect_by_group.png")
