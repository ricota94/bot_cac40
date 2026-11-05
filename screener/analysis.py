"""Indicateurs techniques, détection de configurations et sélection des valeurs à retenir.

Principe : une valeur n'apparaît dans le rapport que si elle présente au moins une
configuration exploitable (repli en tendance haussière, cassure, croisement, rebond…).
Le score final décide si elle est classée « Achat à étudier » ou « À surveiller ».
Ce sont des pistes à étudier, pas des ordres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else 0.0


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, period: int = 14) -> float:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def perf(close: pd.Series, n: int) -> float:
    return pct(float(close.iloc[-1]), float(close.iloc[-n - 1])) if len(close) > n else 0.0


@dataclass
class Stock:
    ticker: str
    name: str
    last: float
    day_pct: float
    perf_1m: float
    perf_3m: float
    perf_6m: float
    perf_1y: float
    rs_3m: float                   # surperformance 3 mois vs indice de référence, en points
    rsi14: float
    sma20: float
    sma50: float
    sma200: float
    sma200_up: bool
    high_52w: float
    low_52w: float
    vol_ratio: float               # volume du jour / moyenne 20 séances
    turnover: float                # capitaux échangés en moyenne par séance (20 j), en euros
    atr14: float
    as_of: date
    setups: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: int = 0
    category: str = ""             # "achat", "surveiller" ou "" (écartée)
    details: dict = field(default_factory=dict)
    stop: float = 0.0
    target: float = 0.0

    @property
    def uptrend(self) -> bool:
        return self.last > self.sma200 and self.sma50 > self.sma200


def compute(df: pd.DataFrame, meta: dict, idx_perf_3m: float) -> Stock:
    c, h, v = df["Close"], df["High"], df["Volume"]
    sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    if sma200.isna().iloc[-1]:
        sma200 = c.expanding().mean()
    last = float(c.iloc[-1])
    vol_avg = float(v.iloc[-21:-1].mean()) if len(v) > 21 else float(v.mean())
    year = df.iloc[-252:]
    return Stock(
        ticker=meta["ticker"], name=meta.get("name", meta["ticker"]), last=last,
        day_pct=pct(last, float(c.iloc[-2])), perf_1m=perf(c, 21), perf_3m=perf(c, 63),
        perf_6m=perf(c, 126), perf_1y=perf(c, 252), rs_3m=perf(c, 63) - idx_perf_3m,
        rsi14=float(rsi_series(c).iloc[-1]), sma20=float(sma20.iloc[-1]), sma50=float(sma50.iloc[-1]),
        sma200=float(sma200.iloc[-1]), sma200_up=bool(sma200.iloc[-1] > sma200.iloc[-21]),
        high_52w=float(year["High"].max()), low_52w=float(year["Low"].min()),
        vol_ratio=float(v.iloc[-1]) / vol_avg if vol_avg else 1.0, atr14=atr(df),
        turnover=float((c * v).iloc[-21:-1].mean()),
        as_of=pd.Timestamp(df.index[-1]).date(),
    )


def detect_setups(s: Stock, df: pd.DataFrame, cfg: dict) -> None:
    """Repère les configurations techniques et calcule un premier score."""
    th = cfg["seuils"]
    c, h = df["Close"], df["High"]
    sma50, sma200 = c.rolling(50).mean(), c.rolling(200).mean()
    rsi = rsi_series(c)
    score = 0

    def add(points: int, setup: str | None, reason: str) -> None:
        nonlocal score
        score += points
        if setup:
            s.setups.append(setup)
        s.reasons.append(reason)

    # 1. Repli sur support dans une tendance haussière (le « buy the dip » classique)
    if (s.uptrend and s.sma200_up and th["repli_rsi_min"] <= s.rsi14 <= th["repli_rsi_max"]
            and s.last <= s.sma50 * 1.03):
        add(3, "Repli en tendance haussière",
            f"Tendance de fond haussière (cours > MM200 en hausse, MM50 > MM200) et repli vers la MM50 "
            f"({pct(s.last, s.sma50):+.1f} %) avec un RSI de {s.rsi14:.0f} : point d'entrée potentiel")

    # 2. Cassure : nouveau plus haut 52 semaines ou 3 mois avec volume
    prior_52w = float(h.iloc[-253:-1].max())
    prior_3m = float(h.iloc[-64:-1].max())
    if s.last >= prior_52w and s.vol_ratio >= th["volume_cassure"] * 0.85:
        add(3, "Cassure du plus haut annuel",
            f"Clôture au-dessus du plus haut 52 semaines ({prior_52w:.2f}) avec un volume "
            f"{s.vol_ratio:.1f}× la moyenne : dynamique forte")
    elif s.last >= prior_3m and s.vol_ratio >= th["volume_cassure"] and s.last > s.sma200:
        add(2, "Cassure du plus haut 3 mois",
            f"Sortie par le haut de la zone des 3 derniers mois (> {prior_3m:.2f}) avec un volume "
            f"{s.vol_ratio:.1f}× la moyenne")

    # 3. Croisement en or récent (MM50 passe au-dessus de la MM200)
    diff = (sma50 - sma200).dropna()
    if len(diff) > 16 and diff.iloc[-1] > 0 and (diff.iloc[-16:-1] <= 0).any() and s.last > s.sma50:
        add(2, "Croisement en or", "La MM50 vient de passer au-dessus de la MM200 (golden cross) : "
            "changement de tendance à moyen terme")

    # 4. Retour au-dessus de la MM200
    below = (c.iloc[-6:-1] < sma200.iloc[-6:-1]).any()
    if s.last > s.sma200 and below and s.vol_ratio >= 1.2 and not s.uptrend:
        add(2, "Retour au-dessus de la MM200",
            f"Le cours repasse au-dessus de la MM200 avec du volume ({s.vol_ratio:.1f}×)")

    # 5. Rebond après survente
    if (float(rsi.iloc[-6:-1].min()) < th["rsi_survente"] and s.rsi14 >= th["rsi_survente"]
            and s.last > float(h.iloc[-2]) and s.last > s.sma200 * 0.85):
        add(2, "Rebond après survente",
            f"RSI sorti de la zone de survente (< {th['rsi_survente']}) et clôture au-dessus du plus haut "
            f"de la veille : début de rebond possible")

    if not s.setups:
        s.score = score
        return

    # Bonus / malus de contexte, appliqués uniquement aux valeurs ayant une configuration
    ref = cfg["indice"].get("ref_court", "l'indice")
    if s.rs_3m >= 5:
        add(1, None, f"Surperforme {ref} de {s.rs_3m:+.1f} pts sur 3 mois (force relative)")
    elif s.rs_3m <= -10:
        add(-1, None, f"Sous-performe {ref} de {s.rs_3m:.1f} pts sur 3 mois")

    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    if hist.iloc[-1] > 0 and (hist.iloc[-4:-1] <= 0).any():
        add(1, None, "MACD qui vient de repasser au-dessus de son signal")

    if s.rsi14 > th["rsi_surachat"]:
        add(-2, None, f"RSI {s.rsi14:.0f} : surachat, mieux vaut attendre un repli")
    if s.last < s.sma200 and not s.sma200_up:
        add(-1, None, "Tendance de fond encore baissière (MM200 orientée à la baisse)")
    if abs(s.day_pct) >= th["mouvement_fort_pct"]:
        s.warnings.append(f"Mouvement de {s.day_pct:+.1f} % aujourd'hui : vérifier l'actualité avant d'agir")
    s.score = score


def apply_details(s: Stock, d: dict, cfg: dict, today: date) -> None:
    """Ajoute le consensus des analystes et l'agenda des résultats au score."""
    s.details = d
    tgt, n = d.get("targetMeanPrice"), d.get("numberOfAnalystOpinions") or 0
    if tgt and n >= cfg["seuils"].get("analystes_min", 3):
        up = pct(tgt, s.last)
        if up >= 15:
            s.score += 1
            s.reasons.append(f"Objectif moyen des analystes {tgt:.2f} € ({up:+.0f} %, {n} analystes)")
        elif up <= 0:
            s.score -= 1
            s.reasons.append(f"Cours déjà au-dessus de l'objectif moyen des analystes ({tgt:.2f} €)")
    if d.get("recommendationKey") in ("sell", "underperform", "strong_sell"):
        s.score -= 1
        s.reasons.append("Consensus des analystes négatif")
    e = d.get("earnings")
    if e and 0 <= (e - today).days <= cfg["seuils"]["resultats_jours"]:
        s.warnings.append(f"Publication des résultats le {e:%d/%m} : le cours peut bouger fortement")


def classify(s: Stock, cfg: dict) -> None:
    sel, th = cfg["selection"], cfg["seuils"]
    s.stop = s.last - th["stop_atr"] * s.atr14
    tgt = s.details.get("targetMeanPrice")
    s.target = tgt if tgt and tgt > s.last * 1.04 else s.last + 2 * (s.last - s.stop)
    if not s.setups or s.turnover < th.get("liquidite_min_eur", 0):
        s.category = ""
    elif s.score >= sel["score_achat"] and s.last > s.sma200 and s.rsi14 <= th["rsi_surachat"]:
        s.category = "achat"
    elif s.score >= sel["score_surveiller"]:
        s.category = "surveiller"


def equal_weight_index(frames: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Indice maison : moyenne des variations quotidiennes de toutes les valeurs (équipondéré).
    Sert de référence quand Yahoo Finance ne publie pas l'indice officiel (cas du CAC Small)."""
    if not frames:
        return None
    rets = pd.concat({t: df["Close"].pct_change() for t, df in frames.items()}, axis=1)
    rets = rets.clip(-0.5, 0.5).dropna(how="all").iloc[1:]
    level = (1 + rets.mean(axis=1, skipna=True).fillna(0)).cumprod() * 1000
    return pd.DataFrame({"Close": level})


def market_context(idx: pd.DataFrame | None, stocks: list[Stock], name: str = "") -> dict:
    ctx = {"name": name, "breadth": sum(s.last > s.sma200 for s in stocks) / len(stocks) * 100 if stocks else 0}
    if idx is not None and len(idx) > 200:
        c = idx["Close"]
        ctx.update(last=float(c.iloc[-1]), day=pct(float(c.iloc[-1]), float(c.iloc[-2])),
                   perf_1m=perf(c, 21), above200=bool(c.iloc[-1] > c.rolling(200).mean().iloc[-1]))
    ctx["prudence"] = (not ctx.get("above200", True)) or ctx["breadth"] < 40
    return ctx
