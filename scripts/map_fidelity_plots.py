"""Plots for the map-fidelity research lane.

Run: uv run --with matplotlib python scripts/map_fidelity_plots.py
(matplotlib is not a repo dependency; --with keeps it out of pyproject.)

Reads docs/evidence/map_fidelity/spectrum.csv + hf_by_terrain.csv,
writes spectrum.png and hf_by_terrain.png (both downscaled, < 1 MB).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path("docs/evidence/map_fidelity")


def spectrum() -> None:
    series = defaultdict(lambda: ([], []))
    with (OUT / "spectrum.csv").open() as f:
        for r in csv.DictReader(f):
            k, a = series[r["map"]]
            k.append(float(r["cycles_per_km"]))
            a.append(float(r["amplitude_levels"]))
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=110)
    styles = {"ck3_vanilla": "-", "ours_generated": "-", "ck2_faerun": "--", "ck2_vanilla": ":"}
    for name, (k, a) in series.items():
        ax.loglog(k, a, styles.get(name, "-"), label=name, lw=1.6)
    for wl, lbl in ((10, "10 km"), (5, "5 km"), (2, "2 km"), (1, "1 km")):
        ax.axvline(1.0 / wl, color="0.85", lw=0.8, zorder=0)
        ax.text(1.0 / wl, ax.get_ylim()[1], lbl, fontsize=7, color="0.5",
                ha="center", va="bottom")
    ax.set_xlabel("spatial frequency (cycles / km)")
    ax.set_ylabel("amplitude (CK3 16-bit height levels)")
    ax.set_title("Radial power spectrum of land heightmap patches (512x512, n=6)")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "spectrum.png")
    plt.close(fig)


def terrain_bars() -> None:
    rows = list(csv.DictReader((OUT / "hf_by_terrain.csv").open()))
    rows.sort(key=lambda r: float(r["hf_rms_levels"]))
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=110)
    ax.barh([r["terrain"] for r in rows], [float(r["hf_rms_levels"]) for r in rows],
            color="#4c72b0")
    ax.set_xlabel("high-frequency RMS (16-bit levels, detail below ~6 km)")
    ax.set_title("Vanilla CK3 heightmap detail amplitude by terrain type")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "hf_by_terrain.png")
    plt.close(fig)


def prototype_spectrum() -> None:
    """Sword Coast crop before/after the detail passes, against vanilla."""
    src = OUT / "sword_coast/spectrum_prototype.csv"
    if not src.exists():
        return
    series = defaultdict(lambda: ([], []))
    with src.open() as f:
        for r in csv.DictReader(f):
            k, a = series[r["stage"]]
            k.append(float(r["cycles_per_km"]))
            a.append(float(r["amplitude_levels"]))
    with (OUT / "spectrum.csv").open() as f:
        for r in csv.DictReader(f):
            if r["map"] == "ck3_vanilla":
                k, a = series["ck3_vanilla (reference)"]
                k.append(float(r["cycles_per_km"]))
                a.append(float(r["amplitude_levels"]))
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=110)
    for name, (k, a) in series.items():
        ax.loglog(k, a, "--" if "vanilla" in name else "-", label=name, lw=1.6)
    ax.axvline(1 / (2 * 2.90), color="0.6", lw=0.9)
    ax.text(1 / (2 * 2.90), ax.get_ylim()[1], " CK2 source Nyquist", fontsize=7,
            color="0.4", va="bottom")
    ax.axvline(1 / (2 * 1.4839), color="0.6", lw=0.9, ls=":")
    ax.text(1 / (2 * 1.4839), ax.get_ylim()[1], " our Nyquist", fontsize=7,
            color="0.4", va="bottom")
    ax.set_xlabel("spatial frequency (cycles / km)")
    ax.set_ylabel("amplitude (CK3 16-bit height levels)")
    ax.set_title("Sword Coast heightmap: before / after the detail passes")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "sword_coast/spectrum_prototype.png")
    plt.close(fig)


if __name__ == "__main__":
    spectrum()
    terrain_bars()
    prototype_spectrum()
    print("wrote", OUT / "spectrum.png", OUT / "hf_by_terrain.png",
          OUT / "sword_coast/spectrum_prototype.png")
