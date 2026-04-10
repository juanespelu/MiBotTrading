import time, json, sys, os, requests
from datetime import datetime
from test_conexion import exchange
from especialista_v3 import analizar_sniper

# --- RUTAS ABSOLUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_BITACORA = os.path.join(BASE_DIR, "log_mejora_bot.txt")
RUTA_ESTADO = os.path.join(BASE_DIR, "estado_bot.json")

# --- CONFIGURACION ---
TOKEN_TLG   = "8053730090:AAGcO5gRrCLUW-x49kbgFaddBUuHJ0kPk2o"
CHAT_ID_TLG = "5406833047"

DNA_FLOTA = {
    "SOL/USDT:USDT": {"k_lim": 45, "ma": "SMA", "pri": 1},
    "ETH/USDT:USDT": {"k_lim": 45, "ma": "SMA", "pri": 2},
}
CARTERA = list(DNA_FLOTA.keys())

# --- PARAMETROS V4.0 ---
STOP_LOSS     = -1.00
BE_TRIGGER    =  0.20
BE_STOP       =  0.10
T1_TARGET     =  0.35
TRAILING_DIST =  0.30
SUELO_POST_T1 =  0.35
FILTRO_BTC    = True

# --- SEGUIMIENTO POST-TRADE ---
# Checkpoints: 30s, 1min, 3min, 5min, 15min, 30min, 1h, 2h
POST_TRADE_CHECKPOINTS = [0.5, 1, 3, 5, 15, 30, 60, 120]  # en minutos
seguimiento_post = {}  # {simbolo: {motivo, p_cierre, t_cierre, checkpoints_pendientes}}

def iniciar_seguimiento(simbolo, motivo_salida, p_cierre):
    seguimiento_post[simbolo] = {
        "motivo":      motivo_salida,
        "p_cierre":    p_cierre,
        "t_cierre":    datetime.now(),
        "pendientes":  list(POST_TRADE_CHECKPOINTS),
    }

def procesar_seguimiento(res):
    """Llamar en cada ciclo con el resultado del especialista para cada símbolo."""
    ahora = datetime.now()
    for simbolo in list(seguimiento_post.keys()):
        seg = seguimiento_post[simbolo]
        if simbolo not in [s for s in res if res.get('simbolo') == simbolo]:
            pass  # se procesa por símbolo en el loop principal
    # Esta función se llama desde el loop con el res ya disponible

def chequear_post_trade(simbolo, res):
    """Chequea si hay checkpoints pendientes para este símbolo y los registra."""
    if simbolo not in seguimiento_post:
        return
    seg = seguimiento_post[simbolo]
    ahora = datetime.now()
    elapsed_min = (ahora - seg["t_cierre"]).total_seconds() / 60
    pendientes_restantes = []
    for cp in seg["pendientes"]:
        if elapsed_min >= cp:
            p_actual  = res.get('p', 0)
            retorno   = ((p_actual - seg["p_cierre"]) / seg["p_cierre"]) * 100 if seg["p_cierre"] > 0 else 0
            fin_str   = " --- FIN SEGUIMIENTO" if cp == POST_TRADE_CHECKPOINTS[-1] else ""
            registrar_log_tecnico(
                f"POST_TRADE [{seg['motivo']}] {simbolo} | "
                f"t:{cp if cp < 60 else f'{int(cp//60)}h'}{'min' if cp < 60 else ''} | "
                f"P_cierre:{seg['p_cierre']:.4f} | P_ahora:{p_actual:.4f} | "
                f"Retorno:{retorno:+.3f}% | "
                f"SobreEMA7:{res.get('precio_sobre_ema7', False)} | "
                f"GapEMA7:{res.get('gap_ema7', 0):+.4f}% | "
                f"Cruce15m:{res.get('cruce_15m', '-') or '-'} | "
                f"VelasCruce15m:{res.get('velas_desde_cruce', -1)} | "
                f"BTC:{res.get('btc_trend', '?')}{fin_str}"
            )
        else:
            pendientes_restantes.append(cp)
    if pendientes_restantes:
        seguimiento_post[simbolo]["pendientes"] = pendientes_restantes
    else:
        del seguimiento_post[simbolo]

# --- FUNCIONES DE APOYO ---
def enviar_telegram(m):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN_TLG}/sendMessage",
            json={"chat_id": CHAT_ID_TLG, "text": m, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

def registrar_log_tecnico(mensaje):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(RUTA_BITACORA, "a", encoding="utf-8") as f:
            f.write(f"[{ahora}] {mensaje}\n")
            f.flush()
            os.fsync(f.fileno())
    except:
        pass

def cargar_estado():
    if not os.path.exists(RUTA_ESTADO):
        with open(RUTA_ESTADO, "w") as f:
            json.dump({"ocupado": False, "posiciones": {}}, f)
    with open(RUTA_ESTADO, 'r') as f:
        return json.load(f)

def guardar_estado(data):
    with open(RUTA_ESTADO, 'w') as f:
        json.dump(data, f, indent=4, default=lambda x: bool(x.item()) if hasattr(x, 'item') else str(x))

# --- NUCLEO OPERATIVO ---
def buscar_oportunidades():
    try:
        estado_bot = cargar_estado()
        balance = float(exchange.fetch_balance()['total']['USDT'])

        # Display en terminal
        if estado_bot["ocupado"] and estado_bot["posiciones"]:
            sim = list(estado_bot["posiciones"].keys())[0]
            pos = estado_bot["posiciones"][sim]
            nombre = sim.split("/")[0]
            gmax = pos.get("g_max", 0)
            gmin = pos.get("g_min", 0)
            fase = "T1+" if pos.get("t1_hecho") else ("BE+" if pos.get("be_activado") else "")
            estado_str = f"OPEN {nombre} {fase} Max:{gmax:+.2f}% Min:{gmin:+.2f}%"
        else:
            estado_str = "LIBRE"
        sys.stdout.write(f"\r [{datetime.now().strftime('%H:%M:%S')}] Bal:{balance:.2f} USDT | {estado_str}        ")
        sys.stdout.flush()

        for simbolo in CARTERA:
            adn = DNA_FLOTA[simbolo]
            res = analizar_sniper(simbolo, k_lim=adn['k_lim'], ma_tipo=adn['ma'])

            info_estado = "ESPERA"

            if simbolo in estado_bot["posiciones"]:
                pos = estado_bot["posiciones"][simbolo]
                ganancia = ((res['p'] - pos['precio_entrada']) / pos['precio_entrada']) * 100 if res['p'] > 0 else 0
                info_estado = f"OPEN ({ganancia:+.2f}%)"

                if ganancia > pos.get('g_max', -999):
                    pos['g_max'] = round(ganancia, 4)
                if ganancia < pos.get('g_min', 999):
                    pos['g_min'] = round(ganancia, 4)

                # 1. TRAILING POST-T1
                if pos.get('t1_hecho'):
                    trailing_actual = max(SUELO_POST_T1, ganancia - TRAILING_DIST)
                    if trailing_actual > pos.get('trailing_stop', SUELO_POST_T1):
                        pos['trailing_stop'] = trailing_actual
                    if ganancia <= pos['trailing_stop']:
                        exchange.create_market_sell_order(simbolo, pos['cantidad'])
                        enviar_telegram(
                            f"*TRAILING*: {simbolo} cerrado en {ganancia:+.2f}% | "
                            f"Max:{pos.get('g_max',0):+.2f}% Min:{pos.get('g_min',0):+.2f}%"
                        )
                        subida_post_t1 = round(ganancia - pos.get('g_max_a_t1', T1_TARGET), 4) if pos.get('precio_t1') else 0
                        registrar_log_tecnico(
                            f"CIERRE_TRAILING {simbolo} | PnL:{ganancia:+.2f}% | "
                            f"Max:{pos.get('g_max',0):+.2f}% | Min:{pos.get('g_min',0):+.2f}% | "
                            f"Trail:{pos.get('trailing_stop',0):+.2f}% | "
                            f"P_t1:{pos.get('precio_t1',0):.4f} | SubidaPostT1:{subida_post_t1:+.4f}% | "
                            f"Sesion:{pos.get('sesion','?')} | BTC:{pos.get('btc_trend_entrada','?')} | "
                            f"Motivo:{pos.get('motivo_entrada','?')} | "
                            f"GapEMA7:{pos.get('gap_ema7_entrada',0):+.4f}% | SobreEMA7:{pos.get('precio_sobre_ema7',False)} | "
                            f"Cruce15m:{pos.get('cruce_15m_entrada','-')} | VelasCruce15m:{pos.get('velas_cruce_entrada',-1)} | "
                            f"Entrada:{pos.get('f_entrada_str','?')}"
                        )
                        iniciar_seguimiento(simbolo, "CIERRE_TRAILING", res['p'])
                        del estado_bot["posiciones"][simbolo]
                        estado_bot["ocupado"] = False

                # 2. T1
                elif ganancia >= T1_TARGET and not pos.get('t1_hecho'):
                    mitad = pos['cantidad'] / 2
                    exchange.create_market_sell_order(simbolo, mitad)
                    pos['cantidad']      = mitad
                    pos['t1_hecho']      = True
                    pos['trailing_stop'] = SUELO_POST_T1
                    pos['precio_t1']     = res['p']
                    pos['g_max_a_t1']    = round(ganancia, 4)
                    pos['t_t1']          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    enviar_telegram(
                        f"*T1 ({T1_TARGET}%)*: {simbolo} | Mitad cobrada | "
                        f"P:{res['p']:.4f} | Trail activo desde {SUELO_POST_T1:.2f}%"
                    )
                    registrar_log_tecnico(
                        f"T1 {simbolo} | P_t1:{res['p']:.4f} | ganancia:{ganancia:+.2f}% | "
                        f"Trail_suelo:{SUELO_POST_T1:.2f}% | "
                        f"SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                        f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | "
                        f"Cruce15m:{res.get('cruce_15m','-') or '-'} | "
                        f"BTC:{res.get('btc_trend','?')}"
                    )
                    iniciar_seguimiento(simbolo + "_T1", "POST_T1", res['p'])

                # 3. BREAK-EVEN
                elif ganancia >= BE_TRIGGER and not pos.get('be_activado'):
                    pos['be_activado'] = True
                    enviar_telegram(f"*BE activado*: {simbolo} en {ganancia:+.2f}%")
                    registrar_log_tecnico(f"BE_ACTIVADO {simbolo} | ganancia:{ganancia:+.2f}%")

                # 4. SALIDAS DE EMERGENCIA
                if simbolo in estado_bot["posiciones"] and not pos.get('t1_hecho'):
                    salida = None
                    if pos.get('be_activado') and ganancia <= BE_STOP:
                        salida = "RETROCESO_BE"
                    elif not pos.get('be_activado') and ganancia <= STOP_LOSS:
                        salida = "STOP_LOSS"
                    if salida:
                        exchange.create_market_sell_order(simbolo, pos['cantidad'])
                        enviar_telegram(
                            f"*{salida}*: {simbolo} en {ganancia:+.2f}% | "
                            f"Max:{pos.get('g_max',0):+.2f}% Min:{pos.get('g_min',0):+.2f}%"
                        )
                        registrar_log_tecnico(
                            f"{salida} {simbolo} | PnL:{ganancia:+.2f}% | "
                            f"Max:{pos.get('g_max',0):+.2f}% | Min:{pos.get('g_min',0):+.2f}% | "
                            f"Sesion:{pos.get('sesion','?')} | BTC:{pos.get('btc_trend_entrada','?')} | "
                            f"Motivo:{pos.get('motivo_entrada','?')} | "
                            f"GapEMA7:{pos.get('gap_ema7_entrada',0):+.4f}% | SobreEMA7:{pos.get('precio_sobre_ema7',False)} | "
                            f"Cruce15m:{pos.get('cruce_15m_entrada','-')} | VelasCruce15m:{pos.get('velas_cruce_entrada',-1)} | "
                            f"Entrada:{pos.get('f_entrada_str','?')}"
                        )
                        iniciar_seguimiento(simbolo, salida, res['p'])
                        del estado_bot["posiciones"][simbolo]
                        estado_bot["ocupado"] = False

            elif not estado_bot["ocupado"]:
                btc_bloquea = FILTRO_BTC and res.get('btc_trend') == 'BAJISTA'

                if not btc_bloquea and res['k'] < adn['k_lim'] and res['k'] > res['d'] and "P<MA" not in res.get('block', ''):
                    monto_usdt      = balance * 0.95
                    cantidad_tokens = monto_usdt / res['p']
                    orden           = exchange.create_market_buy_order(simbolo, cantidad_tokens)
                    enviar_telegram(
                        f"*ENTRADA REAL*: {simbolo} | "
                        f"P:{res['p']:.4f} K:{res['k']:.1f} | "
                        f"Slope:{res.get('pendiente_7',0):+.3f}% VolR:{res.get('vol_r',0):.1f}x | "
                        f"GapEMA7:{res.get('gap_ema7',0):+.3f}% VelasCruce:{res.get('velas_desde_cruce',-1)} | "
                        f"BTC:{res.get('btc_trend','?')}"
                    )
                    estado_bot["posiciones"][simbolo] = {
                        "precio_entrada": res['p'],
                        "cantidad":       orden['amount'],
                        "t1_hecho":       False,
                        "be_activado":    False,
                        "trailing_stop":  SUELO_POST_T1,
                        "g_max":          0.0,
                        "g_min":          0.0,
                        # Contexto de entrada para análisis
                        "sesion":         "ASIATICA" if datetime.utcnow().hour < 8 else ("EUROPEA" if datetime.utcnow().hour < 16 else "AMERICANA"),
                        "slope_entrada":  round(res.get('pendiente_7', 0), 4),
                        "vol_r_entrada":  round(res.get('vol_r', 0), 2),
                        "gap200_entrada": round(res.get('gap200', 0), 2),
                        "gap_ema7_entrada": round(res.get('gap_ema7', 0), 4),
                        "precio_sobre_ema7": res.get('precio_sobre_ema7', False),
                        "cruce_15m_entrada": res.get('cruce_15m', '-'),
                        "velas_cruce_entrada": res.get('velas_desde_cruce', -1),
                        "cruce_1h_entrada": res.get('cruce_1h', '-'),
                        "btc_trend_entrada": res.get('btc_trend', '?'),
                        "motivo_entrada": "SNIPER" if (res.get('pendiente_7',0) > 0.10 and res.get('vol_r',0) > 1.3) else "ESTANDAR",
                        "f_entrada_str":  datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    estado_bot["ocupado"] = True
                    info_estado = "DISPARANDO"
                    registrar_log_tecnico(
                        f"ENTRADA {simbolo} | P:{res['p']:.4f} | "
                        f"K:{res['k']:.1f} D:{res['d']:.1f} | "
                        f"Slope:{res.get('pendiente_7',0):+.4f}% | "
                        f"VolR:{res.get('vol_r',0):.2f}x | "
                        f"Gap200:{res.get('gap200',0):+.2f}% | "
                        f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                        f"Cruce15m:{res.get('cruce_15m','-')} | VelasCruce15m:{res.get('velas_desde_cruce',-1)} | "
                        f"Cruce1h:{res.get('cruce_1h','-')} | "
                        f"BTC:{res.get('btc_trend','?')} | "
                        f"Slope15m:{res.get('slope_ema5_15m',0):+.3f}% | "
                        f"Motivo:{'SNIPER' if (res.get('pendiente_7',0)>0.10 and res.get('vol_r',0)>1.3) else 'ESTANDAR'}"
                    )

            chequear_post_trade(simbolo, res)
            registrar_log_tecnico(
                f"SCAN {simbolo:12} | P:{res.get('p',0):<8.2f} | "
                f"K:{res.get('k',0):.1f} D:{res.get('d',0):.1f} | "
                f"BTC:{res.get('btc_trend','?'):8s} | "
                f"Slope1h:{res.get('pendiente_7',0):+.4f}% | "
                f"GapEMA7_1h:{res.get('gap_ema7',0):+.4f}% | SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                f"Cruce1h:{res.get('cruce_1h','-')} | "
                f"Cruce15m:{res.get('cruce_15m','-')} | VelasCruce15m:{res.get('velas_desde_cruce',-1)} | "
                f"Slope15m:{res.get('slope_ema5_15m',0):+.3f}% | "
                f"BLOCK:{res.get('block',''):15s} | Estado:{info_estado}"
            )

        guardar_estado(estado_bot)

    except Exception as e:
        registrar_log_tecnico(f"ERROR: {e}")

if __name__ == "__main__":
    time.sleep(3)  # espera inicial para que ccxt termine de inicializar
    enviar_telegram(
        "*Maestro V4.0 Online*\n"
        f"SL:{STOP_LOSS}% BE:{BE_TRIGGER}% T1:{T1_TARGET}% "
        f"Trail:{TRAILING_DIST}% SueloPT1:{SUELO_POST_T1}%"
    )
    ultimo_hb = time.time()
    while True:
        buscar_oportunidades()
        if time.time() - ultimo_hb >= 21600:
            enviar_telegram("Heartbeat: Maestro V4.0 operando.")
            ultimo_hb = time.time()
        time.sleep(5)