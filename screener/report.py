"""Rapport HTML (styles en ligne, compatible Gmail / Outlook). Seules les valeurs retenues y figurent.

Le même gabarit sert à l'e-mail (images en pièces jointes intégrées, « cid: ») et au fichier
archivé (images en base64, lisible hors ligne)."""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Callable

from .analysis import Stock, pct
from .interactive import SCRIPT

UP, DOWN, INK, MUTED, LINE = "#0f8a5f", "#c8372d", "#1d2433", "#6b7487", "#e7eaf0"
CAT = {"achat": ("Achat à étudier", "#e6f4ee", UP), "surveiller": ("À surveiller", "#fff4e0", "#a05a00")}
RECO = {"strong_buy": "achat fort", "buy": "achat", "hold": "conserver", "underperform": "sous-pondérer",
        "sell": "vente", "strong_sell": "vente forte", "none": "–"}


def num(v: float, dec: int = 2) -> str:
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")


def eur(v: float) -> str:
    return f"{num(v)} €"


def sgn(v: float, dec: int = 1) -> str:
    return f"{v:+.{dec}f} %".replace(".", ",")


def col(v: float) -> str:
    return UP if v >= 0 else DOWN


def _kpi(label: str, value: str, color: str = INK) -> str:
    return (f'<td style="padding:6px 8px;background:#f6f7fa;border-radius:6px;vertical-align:top">'
            f'<div style="font-size:11px;color:{MUTED}">{label}</div>'
            f'<div style="font-weight:600;color:{color};white-space:nowrap">{value}</div></td>')


def _card(s: Stock, chart: str) -> str:
    label, bg, fg = CAT[s.category]
    d = s.details
    kpis = [
        _kpi("Jour", sgn(s.day_pct, 2), col(s.day_pct)),
        _kpi("1 mois", sgn(s.perf_1m), col(s.perf_1m)),
        _kpi("3 mois vs indice", f"{s.rs_3m:+.1f} pts".replace(".", ","), col(s.rs_3m)),
        _kpi("RSI 14", f"{s.rsi14:.0f}"),
    ]
    kpis2 = [
        _kpi("Stop indicatif", f"{eur(s.stop)} ({sgn(pct(s.stop, s.last))})", DOWN),
        _kpi("Objectif", f"{eur(s.target)} ({sgn(pct(s.target, s.last))})", UP),
        _kpi("Plus haut 52 s.", f"{eur(s.high_52w)} ({sgn(pct(s.last, s.high_52w))})"),
        _kpi("Volume / moy.", f"{s.vol_ratio:.1f}×".replace(".", ",")),
    ]
    funda = []
    if d.get("recommendationKey"):
        funda.append(f"Consensus : {RECO.get(d['recommendationKey'], d['recommendationKey'])}"
                     + (f" ({d['numberOfAnalystOpinions']} analystes)" if d.get("numberOfAnalystOpinions") else ""))
    pe = d.get("forwardPE") or d.get("trailingPE")
    if pe and 0 < pe < 200:
        funda.append(f"PER {num(pe, 1)}")
    dy = d.get("dividendYield")
    if dy:
        funda.append(f"Rendement {num(dy * 100 if dy < 1 else dy, 1)} %")
    funda_html = f'<div style="font-size:12px;color:{MUTED};margin-top:6px">{escape(" · ".join(funda))}</div>' if funda else ""

    warn = "".join(f'<li style="color:#8a4b00;font-weight:600">⚠ {escape(w)}</li>' for w in s.warnings)
    why = "".join(f"<li>{escape(r.replace('.', ','))}</li>" for r in s.reasons)
    setups = " · ".join(s.setups)
    return f"""
<div style="border:1px solid {LINE};border-radius:12px;padding:14px 16px;margin:0 0 16px;background:#fff">
 <table role="presentation" style="width:100%;border-collapse:collapse"><tr>
  <td style="vertical-align:top"><div style="font-size:18px;font-weight:700">{escape(s.name)}
   <span style="font-size:12px;color:{MUTED};font-weight:400">{escape(s.ticker)}</span></div>
   <span style="display:inline-block;margin-top:4px;background:{bg};color:{fg};padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600">{label}</span>
   <span style="font-size:12px;color:{MUTED}">&nbsp;score {s.score:+d} · {escape(setups)}</span></td>
  <td style="text-align:right;vertical-align:top;white-space:nowrap"><div style="font-size:20px;font-weight:700">{eur(s.last)}</div>
   <div style="color:{col(s.day_pct)};font-weight:600">{sgn(s.day_pct, 2)}</div></td>
 </tr></table>
 <table role="presentation" style="width:100%;border-collapse:separate;border-spacing:4px;margin-top:8px;font-size:13px"><tr>{''.join(kpis)}</tr><tr>{''.join(kpis2)}</tr></table>
 {chart}
 <ul style="margin:4px 0 0;padding-left:18px;font-size:13px">{warn}{why}</ul>{funda_html}
</div>"""


def build(selected: list[Stock], ctx: dict, n_total: int, errors: list[str], now: datetime,
          chart: Callable[[Stock], str], interactive: bool = False, title: str = "CAC Small",
          n_illiquid: int = 0) -> str:
    """chart(s) renvoie le code HTML du graphique de la valeur s (image ou graphique interactif)."""
    buys = [s for s in selected if s.category == "achat"]
    watch = [s for s in selected if s.category == "surveiller"]

    market = ""
    if "last" in ctx:
        trend = "au-dessus" if ctx["above200"] else "en dessous"
        market = (f"{escape(ctx['name'])} : "
                  f"<span style='color:{col(ctx['day'])}'>{sgn(ctx['day'], 2)}</span> aujourd'hui, "
                  f"{sgn(ctx['perf_1m'])} sur 1 mois, {trend} de sa MM200. ")
    market += f"{ctx['breadth']:.0f} % des valeurs analysées sont au-dessus de leur MM200."
    prudence = ""
    if ctx.get("prudence"):
        prudence = ("<p style='margin:10px 0 0;padding:10px 12px;background:#fff8ec;border-left:3px solid #d98a1c;"
                    "color:#6b4a12;font-size:13px'>Contexte de marché fragile : privilégie des positions réduites "
                    "et respecte les stops.</p>")

    def section(title: str, items: list[Stock], intro: str) -> str:
        if not items:
            return ""
        return (f"<h3 style='font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:{MUTED};margin:26px 0 4px'>"
                f"{title} ({len(items)})</h3><p style='margin:0 0 10px;font-size:13px;color:{MUTED}'>{intro}</p>"
                + "".join(_card(s, chart(s)) for s in items))

    body = section("Achat à étudier", buys,
                   "Configuration technique favorable et score élevé. À valider avec l'actualité de la société.")
    body += section("À surveiller", watch,
                    "Configuration intéressante mais pas encore confirmée : à garder à l'œil les prochains jours.")
    if not selected:
        body = ("<p style='margin:24px 0;padding:16px;background:#f6f7fa;border-radius:10px'>Aucune valeur "
                "ne présente de configuration convaincante ce soir. Pas d'achat à envisager : rester patient.</p>")

    err = (f"<p style='color:{DOWN};font-size:12px'>Valeurs non récupérées : {escape(', '.join(errors))}</p>"
           if errors else "")
    illiq = (f" (dont {n_illiquid} avec une configuration mais trop peu échangées)" if n_illiquid else "")
    if not selected:
        hint = ""
    elif interactive:
        hint = (f"<p style='margin:10px 0 0;font-size:12px;color:{MUTED}'>Passe la souris (ou le doigt) sur un graphique "
                "pour voir le cours exact à chaque date.</p>")
    else:
        hint = (f"<p style='margin:10px 0 0;font-size:12px;color:{MUTED}'>Graphiques interactifs (cours exact à chaque "
                "date) : télécharge la pièce jointe et ouvre-la dans ton navigateur.</p>")
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Screener {escape(title)} du {now:%d/%m/%Y}</title></head>
<body style="margin:0;background:#f6f7fa">
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{INK};max-width:640px;margin:0 auto;padding:20px 14px;font-size:14px;line-height:1.45">
<h2 style="margin:0 0 4px">Screener {escape(title)} : {now:%d/%m/%Y}</h2>
<p style="margin:0 0 12px;color:{MUTED}">{n_total} valeurs analysées · <b style="color:{INK}">{len(buys)} achat(s) à étudier</b>, {len(watch)} à surveiller · les autres sont écartées{illiq}</p>
<p style="margin:0;font-size:13px">{market}</p>{prudence}{hint}
{body}{err}
<p style="margin-top:22px;font-size:12px;color:#8a93a6">Sélection automatique à partir d'indicateurs techniques (MM50/MM200, RSI, MACD, volumes,
force relative, liquidité) et du consensus des analystes (Yahoo Finance). Le stop est placé à 2 ATR sous le cours, l'objectif reprend le consensus
ou vise 2 fois le risque. Ce ne sont pas des conseils financiers : vérifie l'actualité avant tout achat.</p>
</div>{SCRIPT if interactive and selected else ""}</body></html>"""


def img_tag(src: str, name: str) -> str:
    return (f'<img src="{src}" alt="Graphique {escape(name)}" width="560" '
            'style="width:100%;max-width:560px;height:auto;display:block;margin:8px 0">')

