"""
Buscador de stocks
--------------------
Recibe un texto de búsqueda (símbolo o nombre de empresa) por la variable de
entorno SEARCH_QUERY, consulta el buscador público de Yahoo Finance, y para
cada resultado encontrado (máximo 5) también consulta su precio actual.
Guarda todo en search_results.json para que la app lo lea.

Corre server-side (en GitHub Actions), así que no tiene el problema de CORS
que sí tendría si el celular intentara consultar a Yahoo directamente.
"""

import json
import os
import urllib.request
import urllib.parse

QUERY = os.environ.get("SEARCH_QUERY", "").strip()
MAX_RESULTS = 5
OUTPUT_FILE = "search_results.json"


def search_symbols(query: str):
    url = "https://query1.finance.yahoo.com/v1/finance/search?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())

    results = []
    for q in data.get("quotes", []):
        symbol = q.get("symbol")
        quote_type = q.get("quoteType")
        # Solo nos interesan acciones y ETFs, no criptos, futuros, etc.
        if not symbol or quote_type not in ("EQUITY", "ETF"):
            continue
        name = q.get("longname") or q.get("shortname") or symbol
        results.append({"symbol": symbol, "name": name})
        if len(results) >= MAX_RESULTS:
            break
    return results


def get_price(symbol: str):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None


def main():
    matches = []
    if QUERY:
        try:
            candidates = search_symbols(QUERY)
        except Exception as e:
            candidates = []
            print(f"Error buscando '{QUERY}': {e}")

        for c in candidates:
            price = get_price(c["symbol"])
            matches.append({"symbol": c["symbol"], "name": c["name"], "price": price})

    result = {"query": QUERY, "matches": matches}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(matches)} resultado(s) para '{QUERY}'")


if __name__ == "__main__":
    main()
