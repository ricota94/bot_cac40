"""Graphique 9 mois (cours, MM50, MM200, stop indicatif) au format PNG."""
from __future__ import annotations

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

INK, MUTED, GRID, BLUE, ORANGE, RED = "#1d2433", "#8a93a6", "#e7eaf0", "#3b6fd8", "#d98a1c", "#c8372d"
MOIS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"]


def trend_png(df: pd.DataFrame, stop: float) -> bytes:
    c = df["Close"]
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200).mean()
    v = slice(-190, None)
    idx = df.index[v]
    fig, ax = plt.subplots(figsize=(6.0, 2.3))
    ax.plot(idx, c.iloc[v], color=INK, linewidth=1.4, label="Cours")
    ax.plot(idx, sma50.iloc[v], color=BLUE, linewidth=1, label="MM50")
    ax.plot(idx, sma200.iloc[v], color=ORANGE, linewidth=1, label="MM200")
    ax.axhline(stop, color=RED, linestyle=(0, (3, 3)), linewidth=0.9, label="Stop indicatif")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: MOIS[mdates.num2date(x).month - 1]))
    ax.legend(loc="upper left", fontsize=7, frameon=False, ncol=4, labelcolor=MUTED)
    ax.margins(x=0)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.yaxis.tick_right()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
