"""
Vigilante de Trailing Stop
---------------------------
Arquitectura (pensada para trackear muchos stocks sin problemas de tamaño):
- watchlist.json: solo metadata liviana de cada stock (símbolo, % de stop,
  máximo, entrada, último precio, estado). Se mantiene siempre chico, sin
  importar cuántos stocks trackees.
- history/<SYMBOL>.json: el historial de precios de CADA stock vive en su
  propio archivo separado. Así, tener muchos stocks no hace que un solo
  archivo gigante se vuelva un problema — cada uno crece independiente.

Este script:
1. Lee watchlist.json
2. Para cada stock activo, consulta su precio en Yahoo Finance
3. Lee/actualiza su archivo de historial en history/<SYMBOL>.json
4. Actualiza el máximo, precio actual, y decide si hay que notificar
5. Guarda watchlist.json y los archivos de historial que cambiaron
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

WATCHLIST_FILE = "watchlist.json"
HISTORY_DIR = "history"

HISTORY_MAX_POINTS = 2016       # ~1 semana de detalle fino (cada 5 min)
DAILY_HISTORY_MAX_DAYS = 3650   # ~10 años de resumen diario (1 punto/día)

# El "topic" de ntfy se guarda como secreto de GitHub, no acá en el código,
# para que nadie más pueda mandarte notificaciones falsas.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")


def get_price(symbol: str) -> float:
    """Consulta el precio actual de un stock usando el endpoint público de Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())
    result = data["chart"]["result"][0]
    return float(result["meta"]["regularMarketPrice"])


def send_notification(symbol: str, price: float, max_price: float, drop_pct: float):
    """Manda una notificación push al celular vía ntfy."""
    if not NTFY_TOPIC:
        print("ADVERTENCIA: no hay NTFY_TOPIC configurado, no se puede notificar.")
        return

    title = f"Vender {symbol} ahora"
    message = (
        f"{symbol} cayó {drop_pct:.2f}% desde su máximo de ${max_price:.2f}. "
        f"Precio actual: ${price:.2f}. Tu trailing stop se activó."
    )
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": "urgent",
            "Tags": "warning,chart_with_downwards_trend",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)
    print(f"Notificación enviada para {symbol}")


def history_path(symbol: str) -> str:
    return os.path.join(HISTORY_DIR, f"{symbol}.json")


def load_history(symbol: str) -> dict:
    """Lee el archivo de historial del stock, o devuelve uno vacío si no existe todavía."""
    path = history_path(symbol)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": [], "daily_history": []}


def save_history(symbol: str, hist: dict):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    # Formato compacto (sin espacios ni indentación) para ahorrar espacio.
    with open(history_path(symbol), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))


def main():
    if not os.path.exists(WATCHLIST_FILE):
        print(f"No existe {WATCHLIST_FILE}, no hay nada que revisar.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    watchlist = data.get("watchlist", [])
    watchlist_changed = False
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today_str = now_iso[:10]

    for stock in watchlist:
        symbol = stock["symbol"]

        if stock.get("triggered"):
            # Ya se notificó que hay que vender este; no lo seguimos revisando.
            continue

        try:
            price = get_price(symbol)
        except Exception as e:
            print(f"Error consultando {symbol}: {e}")
            continue

        # Precio de entrada: se fija una sola vez, la primera vez que vemos el stock.
        if stock.get("entry_price") is None:
            stock["entry_price"] = price

        # Estos dos campos livianos SÍ viven en watchlist.json (para que la
        # lista principal de la app no tenga que leer el historial completo
        # de cada stock solo para mostrar el precio actual).
        stock["last_price"] = round(price, 4)
        stock["last_updated"] = now_iso
        watchlist_changed = True

        # --- Historial detallado: vive en su propio archivo por símbolo ---
        hist = load_history(symbol)

        hist["history"].append({"t": now_iso, "p": round(price, 4)})
        if len(hist["history"]) > HISTORY_MAX_POINTS:
            del hist["history"][: len(hist["history"]) - HISTORY_MAX_POINTS]

        daily = hist["daily_history"]
        if daily and daily[-1]["d"] == today_str:
            daily[-1]["p"] = round(price, 4)
        else:
            daily.append({"d": today_str, "p": round(price, 4)})
        if len(daily) > DAILY_HISTORY_MAX_DAYS:
            del daily[: len(daily) - DAILY_HISTORY_MAX_DAYS]

        save_history(symbol, hist)

        # --- Máximo y trailing stop ---
        max_price = stock.get("highest_price")

        if max_price is None or price > max_price:
            stock["highest_price"] = price
            print(f"{symbol}: nuevo máximo ${price:.2f}")
            continue

        drop_pct = (max_price - price) / max_price * 100
        trailing_stop_pct = stock["trailing_stop_pct"]

        print(f"{symbol}: precio ${price:.2f}, máximo ${max_price:.2f}, caída {drop_pct:.2f}% (stop en {trailing_stop_pct}%)")

        if drop_pct >= trailing_stop_pct:
            send_notification(symbol, price, max_price, drop_pct)
            stock["triggered"] = True
            stock["trigger_price"] = price

    if watchlist_changed:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print("watchlist.json actualizado.")
    else:
        print("Sin cambios.")


if __name__ == "__main__":
    main()
