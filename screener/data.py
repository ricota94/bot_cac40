"""Récupération des cours journaliers (2 ans) des 40 valeurs et de l'indice."""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

COLS = ["Open", "High", "Low", "Close", "Volume"]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[[c for c in COLS if c in df.columns]].dropna(subset=["Close"])
    return df[~df.index.duplicated(keep="last")]


def fetch_all(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Téléchargement groupé, puis nouvel essai valeur par valeur pour celles qui manquent."""
    import yfinance as yf  # import local : pas nécessaire en mode démo

    out: dict[str, pd.DataFrame] = {}
    try:
        raw = yf.download(tickers, period="2y", interval="1d", group_by="ticker",
                          auto_adjust=True, threads=True, progress=False)
        for t in tickers:
            if t in raw.columns.get_level_values(0):
                df = _clean(raw[t])
                if len(df) > 30:
                    out[t] = df
    except Exception as e:
        print(f"Téléchargement groupé en échec ({e}), passage valeur par valeur", file=sys.stderr)

    for t in [t for t in tickers if t not in out]:
        for attempt in range(3):
            try:
                df = _clean(yf.Ticker(t).history(period="2y", interval="1d", auto_adjust=True))
                if len(df) > 30:
                    out[t] = df
                    break
            except Exception as e:
                print(f"  {t} essai {attempt + 1} : {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return out


def fetch_details(ticker: str) -> dict:
    """Infos complémentaires (consensus des analystes, valorisation, date des résultats).
    Facultatif : en cas d'échec, on renvoie un dict vide et le screener continue."""
    import yfinance as yf

    d: dict = {}
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        for k in ("targetMeanPrice", "numberOfAnalystOpinions", "recommendationKey",
                  "trailingPE", "forwardPE", "dividendYield", "sector"):
            if info.get(k) is not None:
                d[k] = info[k]
        try:
            cal = t.calendar or {}
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates:
                d["earnings"] = pd.Timestamp(dates[0]).date()
        except Exception:
            pass
    except Exception as e:
        print(f"  détails {ticker} indisponibles : {e}", file=sys.stderr)
    return d


def fake_all(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Données simulées (marches aléatoires avec tendance) pour tester sans Internet."""
    out = {}
    n = 504
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    for i, t in enumerate(tickers):
        rng = np.random.default_rng(1000 + i)
        drift = rng.normal(0.0004, 0.0008)
        rets = rng.normal(drift, 0.016, n)
        close = rng.uniform(20, 400) * np.exp(np.cumsum(rets))
        vol = rng.integers(500_000, 5_000_000, n).astype(float)
        vol[-1] *= rng.choice([1, 1, 1, 2.2])
        out[t] = pd.DataFrame({
            "Open": close * (1 + rng.normal(0, 0.004, n)),
            "High": close * (1 + abs(rng.normal(0, 0.009, n))),
            "Low": close * (1 - abs(rng.normal(0, 0.009, n))),
            "Close": close, "Volume": vol,
        }, index=idx)
    return out


def fake_details(ticker: str, last: float) -> dict:
    rng = np.random.default_rng(abs(hash(ticker)) % 2**32)
    return {"targetMeanPrice": last * rng.uniform(0.9, 1.3), "numberOfAnalystOpinions": int(rng.integers(5, 25)),
            "recommendationKey": str(rng.choice(["buy", "hold", "strong_buy"])),
            "forwardPE": float(rng.uniform(8, 30)), "dividendYield": float(rng.uniform(0.5, 6))}
