"""Sonde temporaire : sources publiques de la composition complète du CAC Small."""
import io, re, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}
def get(u):
    r = requests.get(u, headers=UA, timeout=30); return r
# 1. Fiche de l'indice : nombre de valeurs
try:
    import pdfplumber
    r = get("https://live.euronext.com/sites/default/files/documentation/index-fact-sheets/CAC_Small_Index_Factsheet.pdf")
    print("FACTSHEET", r.status_code, len(r.content))
    if r.content.startswith(b"%PDF"):
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            t = "\n".join((p.extract_text() or "") for p in pdf.pages)
        for l in t.splitlines():
            if re.search(r"constituent|number|composants|valeurs", l, re.I): print("  ", l)
except Exception as e: print("FACTSHEET ERR", e)
# 2. Pages HTML publiques
for u in ["https://www.boursorama.com/bourse/indices/cours/composition/1rPCACS/",
          "https://www.boursorama.com/bourse/indices/cours/composition/1rPCACS/?page=2",
          "https://www.abcbourse.com/marches/indice_cac-small",
          "https://www.abcbourse.com/marches/composition_indice/cac-small",
          "https://www.zonebourse.com/cours/indice/CAC-SMALL-7198/composition/",
          "https://fr.wikipedia.org/wiki/CAC_Small"]:
    try:
        r = get(u); t = r.text
        title = re.search(r"<title>(.*?)</title>", t, re.S)
        isins = sorted(set(re.findall(r"\bFR\d{10}\b", t)))
        mnemos = sorted(set(re.findall(r"1rP([A-Z0-9]{2,6})\b", t)))
        print(f"\n### {u}\n{r.status_code} {len(t)} title={title.group(1).strip()[:80] if title else ''} isinFR={len(isins)} 1rP={len(mnemos)}")
        print("  1rP:", " ".join(mnemos[:250]))
        if "wikipedia" in u:
            i = t.find("Composition_de_l"); body = re.sub(r"<[^>]+>", " ", t)
            j = body.find("Composition de l'indice", body.find("Composition de l'indice") + 10)
            print("  wiki:", " ".join(body[j:j+5000].split()))
        if "abcbourse" in u or "zonebourse" in u:
            body = " ".join(re.sub(r"<[^>]+>", " ", t).split())
            k = body.lower().find("composition"); print("  extrait:", body[k:k+2500])
    except Exception as e: print("\n###", u, "ERR", e)
