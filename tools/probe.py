"""Sonde temporaire : repère où Euronext publie la composition du CAC Small."""
import re, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
URLS = [
 "https://live.euronext.com/en/markets/paris/indices/list",
 "https://live.euronext.com/en/product/indices/QS0010989133-XPAR",
 "https://live.euronext.com/en/product/indices/QS0010989133-XPAR/market-information",
 "https://live.euronext.com/en/ajax/getIndexComposition/QS0010989133-XPAR",
 "https://live.euronext.com/en/ajax/getIndexCompositionFull/QS0010989133-XPAR",
 "https://live.euronext.com/sites/default/files/documentation/index-composition/CAC_Small_Index_Composition.pdf",
 "https://live.euronext.com/sites/default/files/documentation/index-composition/CAC_40_Index_Composition.pdf",
 "https://fr.wikipedia.org/wiki/CAC_Small",
]
for u in URLS:
    try:
        r = requests.get(u, headers=UA, timeout=30)
        t = r.text if "pdf" not in r.headers.get("content-type", "") else ""
        title = re.search(r"<title>(.*?)</title>", t, re.S)
        isins = set(re.findall(r"\b(?:FR|NL|LU|BE|GB|IT|ES|CH|IL)\d{9}[0-9A-Z]\b|\bQS\d{10}\b", t))
        print(f"\n### {u}\n{r.status_code} {r.headers.get('content-type')} {len(r.content)} o  title={title.group(1).strip()[:90] if title else ''}  isins={len(isins)}")
        for m in sorted(set(re.findall(r'href="([^"]*(?:omposition|CAC.?S|small)[^"]*)"', t, re.I)))[:15]:
            print("  lien:", m)
        for m in re.findall(r'[^<>]{0,60}CAC Small[^<>]{0,80}', t)[:8]:
            print("  txt:", " ".join(m.split()))
        if "ajax" in u or "wikipedia" in u:
            print("  extrait:", " ".join(re.sub(r"<[^>]+>", " ", t).split())[:1500])
    except Exception as e:
        print(f"\n### {u}\nERREUR {e}")

import yfinance as yf
for s in ["^CACS", "^CACS.PA", "CACS.PA", "^CACSM", "^PX4", "^CN20", "^SBF120"]:
    try:
        h = yf.Ticker(s).history(period="5d")
        print("yahoo", s, len(h), h["Close"].iloc[-1] if len(h) else "")
    except Exception as e:
        print("yahoo", s, "ERR", e)
