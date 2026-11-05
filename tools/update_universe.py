"""Met à jour la liste des valeurs du CAC Small (univers.json).

Deux sources publiques, combinées :
1. le PDF de composition d'Euronext : source officielle, mais la version gratuite ne donne
   que les plus grosses valeurs (~37, plus de 80 % du poids de l'indice). Il est lu colonne
   par colonne grâce à la position des mots sous « Company », « MNEMO », « Sector », « Weight » ;
2. le modèle Wikipédia « Palette CAC Small », qui liste les autres sociétés de l'indice.
   Les noms sont convertis en tickers Yahoo Finance (.PA) avec la recherche de Yahoo.

Usage : python tools/update_universe.py [--pdf fichier.pdf]
univers.json n'est pas modifié si la lecture semble incomplète."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://live.euronext.com/sites/default/files/documentation/index-composition/CAC_Small_Index_Composition.pdf"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
MIN_OFFICIAL = 20                     # en dessous, on considère la lecture du PDF ratée
WIKI_API = "https://fr.wikipedia.org/w/api.php"
WIKI_TEMPLATE = "Modèle:Palette CAC Small"
# Sociétés que la recherche Yahoo ne retrouve pas par leur nom Wikipédia (vérifiées au lancement :
# un ticker sans cotation est simplement signalé dans le rapport).
ALIASES = {
    "Avenir Télécom": "AVT.PA", "Bastide Le Confort médical": "BLC.PA", "Groupe Casino": "CO.PA",
    "Groupe Latecoere": "LAT.PA", "HighCo": "HCO.PA", "Jacquet Metals Service": "JCQ.PA",
    "Plastivaloire": "PVL.PA", "Showroomprive.com": "SRP.PA", "Tonnellerie François Frères": "TFF.PA",
    "Vranken-Pommery Monopole": "VRAP.PA",
}
NOT_COMPANIES = re.compile(r"^(CAC|SBF|Euronext|Indice|Portail|Bourse|Liste|France)\b", re.I)
MOIS_EN = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]


def download() -> bytes:
    import requests
    r = requests.get(URL, headers=UA, timeout=60)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise ValueError("la réponse d'Euronext n'est pas un PDF")
    return r.content


def _rows(page) -> list[list[dict]]:
    """Regroupe les mots d'une page en lignes (même ordonnée, à 3 points près)."""
    words = sorted(page.extract_words(keep_blank_chars=False, use_text_flow=False),
                   key=lambda w: (round(w["top"]), w["x0"]))
    rows: list[list[dict]] = []
    for w in words:
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= 3:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def parse(pdf_bytes: bytes) -> tuple[list[dict], str]:
    import pdfplumber

    out, as_of, cols = [], "", None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not as_of:
                m = re.search(r"(" + "|".join(MOIS_EN) + r")\s+(\d{1,2}),\s+(\d{4})", text, re.I)
                if m:
                    as_of = date(int(m.group(3)), MOIS_EN.index(m.group(1).lower()) + 1, int(m.group(2))).isoformat()
            for row in _rows(page):
                labels = [w["text"].lower() for w in row]
                if "mnemo" in labels and "company" in labels:
                    pos = {w["text"].lower(): w["x0"] for w in row}
                    sector_x = next((w["x0"] for w in row if w["text"].lower().startswith("sector")), None)
                    weight_x = next((w["x0"] for w in row if w["text"].lower().startswith("weight")), None)
                    cols = (pos["company"], pos["mnemo"], sector_x, weight_x)
                    continue
                if not cols:
                    continue
                _, x_mnemo, x_sector, x_weight = cols
                tol = 4
                name = [w["text"] for w in row if w["x0"] < x_mnemo - tol]
                mnemo = [w["text"] for w in row if x_mnemo - tol <= w["x0"] < (x_sector or 1e9) - tol]
                sector = [w["text"] for w in row if (x_sector or 1e9) - tol <= w["x0"] < (x_weight or 1e9) - tol]
                weight = [w["text"] for w in row if w["x0"] >= (x_weight or 1e9) - tol]
                if len(mnemo) != 1 or not re.fullmatch(r"[A-Z0-9]{1,8}", mnemo[0]) or not name:
                    continue
                try:
                    wt = float(weight[-1].replace(",", ".")) if weight else None
                except ValueError:
                    wt = None
                out.append({"name": " ".join(name).title(), "mnemo": mnemo[0], "ticker": f"{mnemo[0]}.PA",
                            "secteur": " ".join(sector), "poids": wt})
    seen, uniq = set(), []
    for v in out:
        if v["mnemo"] not in seen:
            seen.add(v["mnemo"])
            uniq.append(v)
    return uniq, as_of


def wikipedia_names() -> list[str]:
    """Titres des articles liés depuis le modèle « Palette CAC Small » de Wikipédia."""
    import requests
    r = requests.get(WIKI_API, headers=UA, timeout=30, params={
        "action": "parse", "page": WIKI_TEMPLATE, "prop": "links", "format": "json", "formatversion": 2})
    r.raise_for_status()
    links = r.json().get("parse", {}).get("links", [])
    names = [l["title"] for l in links if l.get("ns") == 0 and l.get("exists", True)]
    return [re.sub(r"\s*\(.*?\)$", "", n) for n in names if not NOT_COMPANIES.match(n)]


def key(name: str) -> str:
    """Nom simplifié pour comparer « Groupe SMCP » et « Smcp », « Séché Environnement » et « Seche Environnem. »."""
    import unicodedata
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(groupe|group|sa|se|compagnie|cie|et|the|des|de|du|la|le)\b|&|\(.*?\)|\.com", " ", n)
    return re.sub(r"[^a-z0-9]", "", n)


def same_company(a: str, b: str) -> bool:
    ka, kb = key(a), key(b)
    return bool(ka and kb) and min(len(ka), len(kb)) >= 3 and (ka.startswith(kb) or kb.startswith(ka))


def yahoo_ticker(name: str) -> tuple[str, str] | None:
    """Essaie le nom tel quel, puis des variantes simplifiées."""
    variants = [name, re.sub(r"^Groupe\s+", "", name), name.replace("&", "et"),
                re.sub(r"\.com$|\s+(SA|SE|Group|Groupe)$", "", name)]
    for v in dict.fromkeys(variants):
        found = _search(v)
        if found:
            return found
    if name in ALIASES:
        return ALIASES[name], ""
    return None


def _search(name: str) -> tuple[str, str] | None:
    """Cherche le ticker Paris (.PA) d'une société par son nom via la recherche Yahoo Finance."""
    import yfinance as yf
    try:
        quotes = yf.Search(name, max_results=10, news_count=0).quotes
    except Exception as e:
        print(f"  recherche « {name} » en échec : {e}", file=sys.stderr)
        return None
    for q in quotes:
        sym = q.get("symbol", "")
        if sym.endswith(".PA") and q.get("quoteType") == "EQUITY":
            return sym, q.get("sector") or q.get("sectorDisp") or ""
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="lire un PDF local plutôt que le télécharger")
    args = ap.parse_args()

    raw = Path(args.pdf).read_bytes() if args.pdf else download()
    official, as_of = parse(raw)
    for v in official:
        v["source"] = "Euronext"
    print(f"Euronext : {len(official)} valeurs lues (composition au {as_of or 'date inconnue'})")
    if len(official) < MIN_OFFICIAL:
        print("Lecture du PDF incomplète : univers.json n'est pas modifié.", file=sys.stderr)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            print("--- début du PDF, pour diagnostic ---\n" + (pdf.pages[0].extract_text() or "")[:3000])
        return 1

    values = list(official)
    known = {v["ticker"] for v in values}
    try:
        names = wikipedia_names()
    except Exception as e:
        names = []
        print(f"Wikipédia indisponible ({e}) : seules les valeurs Euronext sont retenues.", file=sys.stderr)
    print(f"Wikipédia : {len(names)} sociétés")
    unresolved = []
    for n in names:
        if any(same_company(n, v["name"]) for v in official):
            continue                                   # déjà dans la liste officielle
        found = yahoo_ticker(n)
        if not found:
            unresolved.append(n)
            continue
        tk, sector = found
        if tk in known:
            continue
        known.add(tk)
        values.append({"name": n, "mnemo": tk[:-3], "ticker": tk, "secteur": sector, "poids": None,
                       "source": "Wikipédia"})

    for v in values:
        print(f"{v['ticker']:10} {v['name'][:38]:38} {v['secteur'][:24]:24} {v['source']}")
    if unresolved:
        print(f"Sans ticker Paris trouvé ({len(unresolved)}) : {', '.join(unresolved)}")
    print(f"Total : {len(values)} valeurs")

    dest = ROOT / "univers.json"
    doc = {"_aide": "Généré automatiquement par tools/update_universe.py (workflow hebdomadaire). "
                    "Ne pas modifier à la main : la prochaine mise à jour écraserait les changements.",
           "indice": "CAC Small", "composition_au": as_of,
           "sources": [URL, f"https://fr.wikipedia.org/wiki/{WIKI_TEMPLATE.replace(' ', '_')}"],
           "non_trouvees": unresolved, "valeurs": values}
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Écrit : {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
