"""Point d'entrée : python -m screener [--demo] [--no-email]"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import analysis as an
from .charts import trend_png
from .data import fake_all, fake_details, fetch_all, fetch_details
from .report import build, data_uri

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Screener quotidien du CAC 40")
    ap.add_argument("--demo", action="store_true", help="données simulées (sans Internet)")
    ap.add_argument("--no-email", action="store_true", help="génère le rapport sans l'envoyer")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    univers = cfg["univers"]
    idx_tk = cfg["indice"]["ticker"]
    now = datetime.now(ZoneInfo("Europe/Paris"))

    tickers = [m["ticker"] for m in univers]
    data = fake_all(tickers + [idx_tk]) if args.demo else fetch_all(tickers + [idx_tk])
    idx = data.get(idx_tk)
    idx_perf_3m = an.perf(idx["Close"], 63) if idx is not None else 0.0

    stocks, frames, errors = [], {}, []
    for meta in univers:
        tk = meta["ticker"]
        df = data.get(tk)
        if df is None or len(df) < 60:
            errors.append(meta["name"])
            print(f"✗ {tk}: pas de données", file=sys.stderr)
            continue
        s = an.compute(df, meta, idx_perf_3m)
        an.detect_setups(s, df, cfg)
        stocks.append(s)
        frames[tk] = df

    if not stocks:
        print("Aucune donnée récupérée, arrêt.", file=sys.stderr)
        return 1

    # Consensus analystes + agenda des résultats, seulement pour les valeurs qui ont une configuration
    for s in stocks:
        if s.setups:
            d = fake_details(s.ticker, s.last) if args.demo else fetch_details(s.ticker)
            an.apply_details(s, d, cfg, now.date())
        an.classify(s, cfg)
        mark = {"achat": "ACHAT", "surveiller": "surv.", "": "-"}[s.category]
        print(f"{s.ticker:9} {s.last:>9.2f} {s.day_pct:+6.2f} %  RSI {s.rsi14:3.0f}  score {s.score:+d}  {mark:6} {', '.join(s.setups)}")

    sel = cfg["selection"]
    rank = lambda s: (s.score, s.rs_3m)
    buys = sorted((s for s in stocks if s.category == "achat"), key=rank, reverse=True)[: sel["max_achat"]]
    watch = sorted((s for s in stocks if s.category == "surveiller"), key=rank, reverse=True)[: sel["max_surveiller"]]
    selected = buys + watch
    ctx = an.market_context(idx, stocks)

    pngs = {s.ticker: trend_png(frames[s.ticker], s.stop) for s in selected}
    cid = lambda s: "chart-" + s.ticker.replace(".", "-").replace("^", "").lower()

    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    report_path = out_dir / f"screener_cac40_{now:%Y-%m-%d}.html"
    report_path.write_text(build(selected, ctx, len(stocks), errors, now, lambda s: data_uri(pngs[s.ticker])),
                           encoding="utf-8")
    print(f"Rapport : {report_path} ({len(buys)} achat(s), {len(watch)} à surveiller)")

    if args.no_email:
        return 0

    from .mailer import send
    if buys:
        names = ", ".join(s.name for s in buys[:3]) + ("…" if len(buys) > 3 else "")
        subject = f"CAC 40 {now:%d/%m} : {len(buys)} achat(s) à étudier ({names})"
    elif watch:
        subject = f"CAC 40 {now:%d/%m} : {len(watch)} valeur(s) à surveiller"
    else:
        subject = f"CAC 40 {now:%d/%m} : rien d'intéressant ce soir"
    html = build(selected, ctx, len(stocks), errors, now, lambda s: f"cid:{cid(s)}")
    send(subject, html, {cid(s): pngs[s.ticker] for s in selected}, report_path)
    print("E-mail envoyé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
