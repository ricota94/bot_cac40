"""Graphique interactif (SVG + un peu de JavaScript, sans dépendance externe) pour le rapport HTML.

Au survol de la souris (ou au doigt sur mobile), une ligne verticale suit la courbe et une
bulle affiche la date exacte, le cours de clôture et les moyennes mobiles de ce jour-là.
Les messageries n'exécutent pas de JavaScript : ce graphique n'existe que dans le fichier joint,
le corps du mail garde l'image PNG."""
from __future__ import annotations

import json
import math
import pandas as pd

W, H = 600, 250                  # dimensions logiques (le SVG s'adapte à la largeur)
PL, PR, PT, PB = 8, 58, 26, 22   # marges : axe des prix à droite, légende en haut, mois en bas
MOIS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"]
INK, MUTED, GRID, BLUE, ORANGE, RED = "#1d2433", "#8a93a6", "#e7eaf0", "#3b6fd8", "#d98a1c", "#c8372d"
DASH = ' stroke-dasharray="4 3"'
SESSIONS = 190                   # ~9 mois de séances


def _nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.ceil(lo / step) * step
    return [start + i * step for i in range(int((hi - start) / step) + 1)]


def _fmt(v: float) -> str:
    dec = 0 if v >= 1000 or float(v).is_integer() else 2 if v < 100 else 1
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")


def chart_html(df: pd.DataFrame, stop: float, uid: str) -> str:
    c = df["Close"]
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    view = df.index[-SESSIONS:]
    close, m50, m200 = c.iloc[-SESSIONS:], s50.iloc[-SESSIONS:], s200.iloc[-SESSIONS:]
    n = len(close)

    vals = pd.concat([close, m50.dropna(), m200.dropna()])
    lo, hi = min(float(vals.min()), stop), float(vals.max())
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    x = lambda i: PL + (W - PL - PR) * (i / (n - 1) if n > 1 else 0)
    y = lambda v: PT + (H - PT - PB) * (1 - (v - lo) / (hi - lo))

    def path(series: pd.Series) -> str:
        pts, pen = [], "M"
        for i, v in enumerate(series):
            if pd.isna(v):
                pen = "M"
                continue
            pts.append(f"{pen}{x(i):.1f},{y(float(v)):.1f}")
            pen = "L"
        return " ".join(pts)

    grid = "".join(
        f'<line x1="{PL}" x2="{W - PR}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}"/>'
        f'<text x="{W - PR + 6}" y="{y(t) + 4:.1f}" fill="{MUTED}" font-size="11">{_fmt(t)}</text>'
        for t in _nice_ticks(lo, hi))
    months, prev = [], None
    for i, d in enumerate(view):
        if prev is not None and d.month != prev:
            months.append(f'<text x="{x(i):.1f}" y="{H - 5}" fill="{MUTED}" font-size="11" '
                          f'text-anchor="middle">{MOIS[d.month - 1]}</text>')
        prev = d.month
    legend = "".join(
        f'<g transform="translate({PL + k * 108},10)"><line x1="0" x2="16" y1="0" y2="0" stroke="{col}" '
        f'stroke-width="2"{DASH if dash else ""}/>'
        f'<text x="21" y="4" fill="{MUTED}" font-size="11">{lab}</text></g>'
        for k, (lab, col, dash) in enumerate([("Cours", INK, False), ("MM50", BLUE, False),
                                              ("MM200", ORANGE, False), ("Stop indicatif", RED, True)]))

    r = lambda v: None if pd.isna(v) else round(float(v), 2)
    data = {"d": [d.strftime("%Y-%m-%d") for d in view], "c": [r(v) for v in close],
            "a": [r(v) for v in m50], "b": [r(v) for v in m200],
            "lo": lo, "hi": hi, "W": W, "H": H, "PL": PL, "PR": PR, "PT": PT, "PB": PB}

    payload = json.dumps(data).replace("</", "<\\/")
    return f"""<div class="ichart" id="{uid}" style="position:relative;margin:8px 0;touch-action:pan-y">
<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;overflow:visible;font-family:inherit"
 role="img" aria-label="Graphique interactif du cours sur 9 mois">
{legend}{grid}{''.join(months)}
<line x1="{PL}" x2="{W - PR}" y1="{y(stop):.1f}" y2="{y(stop):.1f}" stroke="{RED}" stroke-dasharray="4 3"/>
<path d="{path(m200)}" fill="none" stroke="{ORANGE}" stroke-width="1.3"/>
<path d="{path(m50)}" fill="none" stroke="{BLUE}" stroke-width="1.3"/>
<path d="{path(close)}" fill="none" stroke="{INK}" stroke-width="1.8" stroke-linejoin="round"/>
<g class="hover" style="display:none;pointer-events:none">
 <line class="vl" y1="{PT}" y2="{H - PB}" stroke="{MUTED}" stroke-dasharray="2 3"/>
 <circle class="pb" r="3.5" fill="{ORANGE}" stroke="#fff" stroke-width="1.5"/>
 <circle class="pa" r="3.5" fill="{BLUE}" stroke="#fff" stroke-width="1.5"/>
 <circle class="pc" r="4.5" fill="{INK}" stroke="#fff" stroke-width="2"/>
</g>
<rect class="hit" x="{PL}" y="{PT}" width="{W - PL - PR}" height="{H - PT - PB}" fill="transparent" style="cursor:crosshair"/>
</svg>
<div class="tip" style="display:none"></div>
<script type="application/json">{payload}</script>
</div>"""


# Un seul script pour tous les graphiques de la page.
SCRIPT = """<style>
.ichart .tip{position:absolute;top:22px;pointer-events:none;background:#1d2433;color:#fff;border-radius:8px;
padding:7px 10px;font-size:12px;line-height:1.45;white-space:nowrap;box-shadow:0 4px 14px rgba(20,30,50,.25);z-index:2}
.ichart .tip b{font-size:14px}.ichart .tip span{color:#b9c1d0}
</style>
<script>
(function(){
  var MOIS=["janv.","févr.","mars","avr.","mai","juin","juil.","août","sept.","oct.","nov.","déc."];
  var JOURS=["dim.","lun.","mar.","mer.","jeu.","ven.","sam."];
  function eur(v){return v==null?"–":v.toLocaleString("fr-FR",{minimumFractionDigits:2,maximumFractionDigits:2})+" €";}
  function pct(v,p){var x=(v/p-1)*100;return (x>=0?"+":"")+x.toFixed(1).replace(".",",")+" %";}
  document.querySelectorAll(".ichart").forEach(function(box){
    var D=JSON.parse(box.querySelector("script").textContent), n=D.c.length;
    var svg=box.querySelector("svg"), hit=box.querySelector(".hit"), g=box.querySelector(".hover"), tip=box.querySelector(".tip");
    var X=function(i){return D.PL+(D.W-D.PL-D.PR)*(n>1?i/(n-1):0);};
    var Y=function(v){return D.PT+(D.H-D.PT-D.PB)*(1-(v-D.lo)/(D.hi-D.lo));};
    function dot(cls,v,i){var e=g.querySelector(cls);if(v==null){e.style.display="none";return;}
      e.style.display="";e.setAttribute("cx",X(i));e.setAttribute("cy",Y(v));}
    function show(ev){
      var r=svg.getBoundingClientRect(), sx=(ev.clientX-r.left)*D.W/r.width;
      var i=Math.max(0,Math.min(n-1,Math.round((sx-D.PL)/(D.W-D.PL-D.PR)*(n-1))));
      var vl=g.querySelector(".vl");vl.setAttribute("x1",X(i));vl.setAttribute("x2",X(i));
      dot(".pc",D.c[i],i);dot(".pa",D.a[i],i);dot(".pb",D.b[i],i);g.style.display="";
      var p=D.d[i].split("-"), dt=new Date(+p[0],p[1]-1,+p[2]);
      tip.innerHTML="<span>"+JOURS[dt.getDay()]+" "+(+p[2])+" "+MOIS[dt.getMonth()]+" "+p[0]+"</span><br>"+
        "<b>"+eur(D.c[i])+"</b> <span>"+(i>0?pct(D.c[i],D.c[i-1])+" sur la séance":"")+"</span><br>"+
        "<span style='color:#8fb0f0'>MM50</span> "+eur(D.a[i])+" &nbsp; <span style='color:#f0b866'>MM200</span> "+eur(D.b[i])+"<br>"+
        "<span>Depuis : "+pct(D.c[n-1],D.c[i])+"</span>";
      tip.style.display="block";
      var px=X(i)*r.width/D.W, w=tip.offsetWidth, bw=box.clientWidth;
      tip.style.left=Math.max(0,Math.min(bw-w,px+(px>bw/2?-w-12:12)))+"px";
    }
    function hide(){g.style.display="none";tip.style.display="none";}
    hit.addEventListener("pointermove",show);hit.addEventListener("pointerdown",show);
    hit.addEventListener("pointerleave",hide);
  });
})();
</script>"""
