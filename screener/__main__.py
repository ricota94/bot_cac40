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
from .interactive import chart_html
from .report import build, img_tag

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Screener quotidien du CAC Small")
    ap.add_argument("--demo", action="store_true", help="données simulées (sans Internet)")
    ap.add_argument("--no-email", action="store_true", help="génère le rapport sans l'envoyer")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    univ = json.loads((ROOT / cfg["univers_fichier"]).read_text(encoding="utf-8"))
    univers = univ["valeurs"]
    title = cfg["indice"]["name"]
    idx_tk = cfg["indice"].get("ticker")          # vide : indice équipondéré calculé sur les valeurs
    now = datetime.now(ZoneInfo("Europe/Paris"))
    print(f"{len(univers)} valeurs ({title}, composition au {univ.get('composition_au', '?')})")

    tickers = [m["ticker"] for m in univers] + ([idx_tk] if idx_tk else [])
    data = fake_all(tickers) if args.demo else fetch_all(tickers)
    if idx_tk and idx_tk in data:
        idx, idx_name = data[idx_tk], title
    else:
        idx = an.equal_weight_index({t: data[t] for t in tickers if t in data and t != idx_tk})
        idx_name = f"{title} (moyenne équipondérée des valeurs)"
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

    # Consensus analystes + agenda des résultats, seulement pour les valeurs liquides qui ont une configuration
    liq_min = cfg["seuils"].get("liquidite_min_eur", 0)
    for s in stocks:
        if s.setups and s.turnover >= liq_min:
            d = fake_details(s.ticker, s.last) if args.demo else fetch_details(s.ticker)
            an.apply_details(s, d, cfg, now.date())
        an.classify(s, cfg)
        mark = {"achat": "ACHAT", "surveiller": "surv.", "": "-"}[s.category]
        print(f"{s.ticker:9} {s.last:>9.2f} {s.day_pct:+6.2f} %  RSI {s.rsi14:3.0f}  {s.turnover / 1e3:>8.0f} k€/j  "
              f"score {s.score:+d}  {mark:6} {', '.join(s.setups)}")
    n_illiquid = sum(1 for s in stocks if s.setups and s.turnover < liq_min)

    sel = cfg["selection"]
    rank = lambda s: (s.score, s.rs_3m)
    buys = sorted((s for s in stocks if s.category == "achat"), key=rank, reverse=True)[: sel["max_achat"]]
    watch = sorted((s for s in stocks if s.category == "surveiller"), key=rank, reverse=True)[: sel["max_surveiller"]]
    selected = buys + watch
    ctx = an.market_context(idx, stocks, idx_name)

    pngs = {s.ticker: trend_png(frames[s.ticker], s.stop) for s in selected}
    cid = lambda s: "chart-" + s.ticker.replace(".", "-").replace("^", "").lower()

    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    slug = title.lower().replace(" ", "_")
    report_path = out_dir / f"screener_{slug}_{now:%Y-%m-%d}.html"
    # Fichier joint : graphiques interactifs (survol = cours exact à la date). Corps du mail : images PNG.
    report_path.write_text(build(selected, ctx, len(stocks), errors, now,
                                 lambda s: chart_html(frames[s.ticker], s.stop, cid(s)), interactive=True,
                                 title=title, n_illiquid=n_illiquid),
                           encoding="utf-8")
    print(f"Rapport : {report_path} ({len(buys)} achat(s), {len(watch)} à surveiller)")

    if args.no_email:
        return 0

    from .mailer import send
    if buys:
        names = ", ".join(s.name for s in buys[:3]) + ("…" if len(buys) > 3 else "")
        subject = f"{title} {now:%d/%m} : {len(buys)} achat(s) à étudier ({names})"
    elif watch:
        subject = f"{title} {now:%d/%m} : {len(watch)} valeur(s) à surveiller"
    else:
        subject = f"{title} {now:%d/%m} : rien d'intéressant ce soir"
    html = build(selected, ctx, len(stocks), errors, now, lambda s: img_tag(f"cid:{cid(s)}", s.name),
                 title=title, n_illiquid=n_illiquid)
    send(subject, html, {cid(s): pngs[s.ticker] for s in selected}, report_path, sender_name=f"Screener {title}")
    print("E-mail envoyé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
