"""
Vigilante de Trailing Stop
---------------------------
Este script:
1. Lee la lista de stocks desde watchlist.json
2. Consulta el precio actual de cada stock en Yahoo Finance
3. Actualiza el precio máximo visto para cada stock
4. Si el precio cayó más del % configurado desde el máximo, envía
   una notificación por ntfy y marca el stock como "triggered"
5. Guarda watchlist.json actualizado

No necesitas entender cada línea para usarlo, pero está comentado
por si en algún momento quieres tocarlo.
"""

import json
import os
import sys
import urllib.request

WATCHLIST_FILE = "watchlist.json"

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
    price = result["meta"]["regularMarketPrice"]
    return float(price)


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


def main():
    if not os.path.exists(WATCHLIST_FILE):
        print(f"No existe {WATCHLIST_FILE}, no hay nada que revisar.")
        return

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    watchlist = data.get("watchlist", [])
    changed = False

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

        max_price = stock.get("highest_price")

        if max_price is None or price > max_price:
            stock["highest_price"] = price
            changed = True
            print(f"{symbol}: nuevo máximo ${price:.2f}")
            continue

        drop_pct = (max_price - price) / max_price * 100
        trailing_stop_pct = stock["trailing_stop_pct"]

        print(f"{symbol}: precio ${price:.2f}, máximo ${max_price:.2f}, caída {drop_pct:.2f}% (stop en {trailing_stop_pct}%)")

        if drop_pct >= trailing_stop_pct:
            send_notification(symbol, price, max_price, drop_pct)
            stock["triggered"] = True
            stock["trigger_price"] = price
            changed = True

    if changed:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("watchlist.json actualizado.")
    else:
        print("Sin cambios.")


if __name__ == "__main__":
    main()
