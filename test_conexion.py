import socket
socket.setdefaulttimeout(10)

import os
import ccxt

# --- Credenciales desde entorno (NUNCA hardcodeadas) ----------------------
# En el VPS las exporta el wrapper start_bot_*.sh desde .env.
# Para ejecución local (o si el wrapper no las exportó) cargamos .env aquí.
def _cargar_env_local():
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(ruta):
        return
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            os.environ.setdefault(clave.strip(), valor.strip())

_cargar_env_local()

API_KEY    = os.getenv("BINANCE_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
if not API_KEY or not SECRET_KEY:
    raise RuntimeError(
        "Faltan BINANCE_API_KEY / BINANCE_SECRET_KEY. "
        "Definilas en .env (junto a este archivo) o exportalas en el entorno."
    )

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': False,
    'timeout': 10000,
    'options': {
        'defaultType': 'future',
        'fetchMarkets': ['linear'],  # solo futuros lineales, evita cargar margen/spot
    }
})

def verificar_conexion():
    try:
        exchange.load_markets()
        print("Conexion con Binance: EXITOSA")
        balance = exchange.fetch_balance()
        usdt_total = balance['total'].get('USDT', 0)
        print(f"Balance en Futuros: {usdt_total} USDT")
        if usdt_total >= 7.64:
            print("El bot tiene combustible suficiente.")
        else:
            print("Saldo menor a 7.64 USDT. Verifica la transferencia a Futuros.")
    except Exception as e:
        print(f"Error de conexion: {e}")

if __name__ == "__main__":
    verificar_conexion()