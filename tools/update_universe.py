"""Met à jour la liste des valeurs de l'indice à partir du PDF de composition publié par Euronext.

Usage : python tools/update_universe.py [--pdf fichier.pdf]
Écrit univers.json (nom, mnémonique, ticker Yahoo, secteur, poids) et n'y touche pas
si la lecture du PDF semble incomplète. Le PDF est lu colonne par colonne grâce à la
position des mots sous les en-têtes « Company », « MNEMO », « Sector », « Weight »."""
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
MIN_VALUES = 80                       # en dessous, on considère la lecture ratée
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="lire un PDF local plutôt que le télécharger")
    args = ap.parse_args()
    raw = Path(args.pdf).read_bytes() if args.pdf else download()
    values, as_of = parse(raw)
    for v in values:
        print(f"{v['ticker']:10} {v['name'][:40]:40} {v['secteur'][:30]:30} {v['poids']}")
    print(f"{len(values)} valeurs lues (composition au {as_of or 'date inconnue'})")
    if len(values) < MIN_VALUES:
        print("Lecture incomplète : univers.json n'est pas modifié.", file=sys.stderr)
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            print("--- début du PDF, pour diagnostic ---\n" + (pdf.pages[0].extract_text() or "")[:3000])
        return 1
    dest = ROOT / "univers.json"
    doc = {"_aide": "Généré automatiquement depuis le PDF de composition d'Euronext par tools/update_universe.py. "
                    "Ne pas modifier à la main : la mise à jour hebdomadaire écraserait les changements.",
           "indice": "CAC Small", "source": URL, "composition_au": as_of, "valeurs": values}
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Écrit : {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
