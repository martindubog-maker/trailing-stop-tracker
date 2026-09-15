"""
Vigilante de Trailing Stop
---------------------------
Este script:
1. Lee la lista de stocks desde watchlist.json
2. Consulta el precio actual de cada stock en Yahoo Finance
3. Guarda el precio en el historial del stock (para el gráfico)
4. Actualiza el precio máximo visto para cada stock
5. Si el precio cayó más del % configurado desde el máximo, envía
   una notificación por ntfy y marca el stock como "triggered"
6. Guarda watchlist.json actualizado

No necesitas entender cada línea para usarlo, pero está comentado
por si en algún momento quieres tocarlo.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

WATCHLIST_FILE = "watchlist.json"

# "history" guarda alta resolución (un punto cada 5 min) pero SOLO de los
# últimos días, para no crecer sin límite. Con chequeos cada 5 min, 2016
# puntos equivalen aprox. a 1 semana. Es la vista de detalle reciente.
HISTORY_MAX_POINTS = 2016

# "daily_history" guarda 1 punto por día, para siempre (o casi). A este
# ritmo, incluso 10 años de datos pesan muy poco. Es la vista de largo plazo.
DAILY_HISTORY_MAX_DAYS = 3650  # ~10 años

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
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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

        # Guardamos el punto de alta resolución (últimos días, para el gráfico reciente).
        history = stock.setdefault("history", [])
        history.append({"t": now_iso, "p": round(price, 4)})
        if len(history) > HISTORY_MAX_POINTS:
            del history[: len(history) - HISTORY_MAX_POINTS]

        # Guardamos/actualizamos el punto del día en el historial de largo plazo.
        # Si ya hay un punto para hoy, lo actualizamos con el precio más reciente;
        # si es un día nuevo, agregamos uno nuevo (así queda 1 punto por día, para siempre).
        today_str = now_iso[:10]  # "YYYY-MM-DD"
        daily = stock.setdefault("daily_history", [])
        if daily and daily[-1]["d"] == today_str:
            daily[-1]["p"] = round(price, 4)
        else:
            daily.append({"d": today_str, "p": round(price, 4)})
        if len(daily) > DAILY_HISTORY_MAX_DAYS:
            del daily[: len(daily) - DAILY_HISTORY_MAX_DAYS]

        changed = True

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

    if changed:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("watchlist.json actualizado.")
    else:
        print("Sin cambios.")


if __name__ == "__main__":
    main()
