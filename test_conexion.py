import socket
socket.setdefaulttimeout(10)

import ccxt

exchange = ccxt.binance({
    'apiKey': 'c1UhqsvLWF6QS2z7ikXR0tYc2Fo4I70A2fPxGjbmazzWTTUQoftAXSpV40kkDRNV',
    'secret': 'WKtQOGY112NgvHaYXXxNxr4gTN99dCfgFQiPt3mNWTFGrOExkxAEc3GdVfwhMsAY',
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