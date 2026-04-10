import time, json, sys, os, requests
from datetime import datetime, timedelta, timezone
from test_conexion import exchange
from especialista_v3 import analizar_sniper

def utcnow():
    """Reemplazo de utcnow() sin DeprecationWarning."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ══════════════════════════════════════════════════════════════
#  BOT MAESTRO V4.0
#  Mejoras sobre V3:
#  - Token Telegram desde variable de entorno (no hardcoded)
#  - SL real en Binance al abrir posición (seguro ante crashes)
#  - Sincronización estado local ↔ Binance al arrancar
#  - Detección error -4411 (acuerdo TradFi) con alerta inmediata
#  - Filtros SNIPER: Slope1H, VolR, SobreEMA7, Slope15m, GapEMA7
#  - Bloqueo post-STOP_LOSS (15min) — no re-entrar en caída libre
#  - CORTE_EMA7 como salida adicional (antes del SL)
#  - Log mejorado: H/L 1H y 15M, contexto técnico completo
#  - Heartbeat cada 6h con balance
# ══════════════════════════════════════════════════════════════

# --- RUTAS ---
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
RUTA_ESTADO   = os.path.join(BASE_DIR, "estado_bot.json")

# ── Carpeta de logs ────────────────────────────────────────────────────────
LOGS_DIR_REAL = os.path.join(BASE_DIR, "logs_real")
os.makedirs(LOGS_DIR_REAL, exist_ok=True)

# ── Archivo de trades — nunca rota, es el histórico valioso ───────────────
RUTA_TRADES = os.path.join(LOGS_DIR_REAL, "log_trades_real.txt")

# ── Función para obtener la ruta del scan semanal ─────────────────────────
def _ruta_scan_semana():
    """Retorna la ruta del archivo de scans de la semana ISO actual.
    Ejemplo: logs_real/log_scans_2026-W12.txt
    """
    hoy = utcnow()
    semana = hoy.isocalendar()
    nombre = f"log_scans_{semana[0]}-W{semana[1]:02d}.txt"
    ruta = os.path.join(LOGS_DIR_REAL, nombre)
    if not os.path.exists(ruta):
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"# Scans semana {semana[0]}-W{semana[1]:02d} "
                    f"— inicio {hoy.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
    return ruta

# --- TELEGRAM ---
TOKEN_TLG   = os.getenv('TELEGRAM_TOKEN', '')
CHAT_ID_TLG = os.getenv('TELEGRAM_CHAT_ID', '')

# --- CARTERA ---
DNA_FLOTA = {
    "SOL/USDT:USDT": {"k_lim": 45, "ma": "SMA", "pri": 1},
    "ETH/USDT:USDT": {"k_lim": 45, "ma": "SMA", "pri": 2},
}
CARTERA = list(DNA_FLOTA.keys())

# --- PARÁMETROS DE TRADING ---
STOP_LOSS     = -1.00   # % pérdida máxima para SL lógico
BE_TRIGGER    =  0.20   # % ganancia para activar break-even
BE_STOP       =  0.10   # % mínimo al salir con BE activo (con BE activo)
T1_TARGET     =  0.35   # % para cerrar mitad de posición
SL_REAL_PCT   =  0.85   # % SL real en Binance (seguro ante crashes)
FILTRO_BTC    = True    # bloquear si BTC_TREND == BAJISTA

# Trailing escalonado post-T1 (del simulador V7.3)
# Distancia se ajusta según cuánto subió desde T1:
#   Hasta +0.35%: trailing 0.20% (suelo mínimo)
#   De +0.35% a +0.60%: trailing 0.08%
#   De +0.60% a +0.80%: trailing 0.06%
#   Sobre +0.80%: trailing 0.05% (muy ajustado)
SUELO_POST_T1  =  0.20   # % suelo mínimo post-T1
TRAILING_DIST  =  0.20   # distancia base del trailing

# --- FILTROS DE ENTRADA SNIPER ---
MIN_SLOPE_1H     =  0.10   # % pendiente mínima EMA7 en 1H
MIN_VOL_R        =  0.30   # volumen relativo mínimo
MIN_SLOPE_15M    =  0.05   # % pendiente mínima EMA5 en 15M
REQUIERE_EMA7    = True    # precio debe estar sobre EMA7
MAX_GAP_EMA7_NEG = -0.05   # bloquear si GapEMA7 < este valor

# --- BLOQUEO POST-STOP ---
BLOQUEO_SL_MIN = 15       # minutos bloqueado tras STOP_LOSS
bloqueo_stop   = {}       # {simbolo: datetime_desbloqueo}

# --- SEGUIMIENTO POST-TRADE ---
POST_TRADE_CHECKPOINTS = [0.5, 1, 3, 5, 15, 30, 60, 120]
seguimiento_post = {}

# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════

def enviar_telegram(m):
    if not TOKEN_TLG or not CHAT_ID_TLG:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN_TLG}/sendMessage",
            json={"chat_id": CHAT_ID_TLG, "text": m, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

def registrar_log(mensaje):
    """SCANs van al archivo semanal. Todo lo demás va al log de trades."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    es_scan = mensaje.startswith("SCAN ")
    ruta = _ruta_scan_semana() if es_scan else RUTA_TRADES
    try:
        with open(ruta, "a", encoding="utf-8") as f:
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
        json.dump(data, f, indent=4,
                  default=lambda x: bool(x.item()) if hasattr(x, 'item') else str(x))

def _detectar_error_binance(e):
    err = str(e)
    if '-4411' in err or 'TradFi' in err or 'agreement' in err.lower():
        msg = ("*ACCION REQUERIDA*: Binance exige firmar acuerdo de futuros.\n"
               "Entra a Binance Futures y acepta el contrato.")
        registrar_log(f"CRITICAL -4411: {msg}")
        enviar_telegram(msg)
        time.sleep(300)

# ══════════════════════════════════════════════════════════════
# STOP LOSS REAL EN BINANCE
# ══════════════════════════════════════════════════════════════

def colocar_sl_real(simbolo, precio_entrada, cantidad):
    try:
        precio_sl = round(precio_entrada * (1 - SL_REAL_PCT / 100), 4)
        exchange.create_order(
            simbolo, 'stop_market', 'sell', cantidad,
            params={'stopPrice': precio_sl, 'reduceOnly': True}
        )
        registrar_log(f"SL_REAL colocado {simbolo} | SL:{precio_sl:.4f} ({-SL_REAL_PCT:.2f}%)")
        return precio_sl
    except Exception as e:
        registrar_log(f"ERROR SL_REAL {simbolo}: {e}")
        enviar_telegram(f"SL REAL FALLO {simbolo}: {e} — cierra manualmente si el bot se cae.")
        return None

def cancelar_sl_real(simbolo):
    try:
        ordenes = exchange.fetch_open_orders(simbolo)
        for o in ordenes:
            if o.get('type') in ('stop_market', 'stop') and o.get('side') == 'sell':
                exchange.cancel_order(o['id'], simbolo)
                registrar_log(f"SL_REAL cancelado {simbolo} | orden:{o['id']}")
    except Exception as e:
        registrar_log(f"ERROR cancelar SL_REAL {simbolo}: {e}")

# ══════════════════════════════════════════════════════════════
# SINCRONIZACIÓN AL ARRANCAR
# ══════════════════════════════════════════════════════════════

def sincronizar_con_binance(estado_bot):
    try:
        posiciones_binance = exchange.fetch_positions(list(DNA_FLOTA.keys()))
        simbolos_binance = {
            p['symbol'] for p in posiciones_binance
            if abs(p.get('contracts', 0) or 0) > 0
        }
        simbolos_estado = set(estado_bot.get("posiciones", {}).keys())

        huerfanas = simbolos_binance - simbolos_estado
        for s in huerfanas:
            msg = f"POSICION HUERFANA: {s} en Binance pero no en estado local. Revisar manualmente."
            registrar_log(msg)
            enviar_telegram(msg)

        zombies = simbolos_estado - simbolos_binance
        for s in zombies:
            registrar_log(f"SYNC: {s} en estado local pero NO en Binance -> limpiando.")
            enviar_telegram(f"SYNC: {s} cerrada externamente. Estado limpiado.")
            del estado_bot["posiciones"][s]
        if zombies and not estado_bot["posiciones"]:
            estado_bot["ocupado"] = False

        registrar_log(
            f"SYNC {'OK' if not huerfanas and not zombies else 'CON DIFERENCIAS'}: "
            f"{len(simbolos_estado)} local | {len(simbolos_binance)} Binance"
        )
        guardar_estado(estado_bot)
        return estado_bot

    except Exception as e:
        registrar_log(f"ERROR sincronizar_con_binance: {e}")
        _detectar_error_binance(e)
        return estado_bot

# ══════════════════════════════════════════════════════════════
# FILTROS SNIPER
# ══════════════════════════════════════════════════════════════

def evaluar_filtros_sniper(res, adn):
    """
    Retorna (pasa: bool, bloqueos_str: str, motivo_entrada: str|None)
    """
    bloqueos = []

    if FILTRO_BTC and res.get('btc_trend_suav', res.get('btc_trend', '')) == 'BAJISTA':
        bloqueos.append("BTC_BAJISTA")

    slope_1h = res.get('pendiente_7', 0)
    if slope_1h < MIN_SLOPE_1H:
        bloqueos.append(f"SLOPE_1H:{slope_1h:+.3f}%")

    slope_15m = res.get('slope_ema5_15m', 0)
    if slope_15m < MIN_SLOPE_15M:
        bloqueos.append(f"SLOPE_15M:{slope_15m:+.3f}%")

    vol_r = res.get('vol_r', 0)
    if vol_r < MIN_VOL_R:
        bloqueos.append(f"VOL_R:{vol_r:.2f}x")

    if REQUIERE_EMA7 and not res.get('precio_sobre_ema7', False):
        bloqueos.append("P<EMA7")

    gap_ema7 = res.get('gap_ema7', 0)
    if gap_ema7 < MAX_GAP_EMA7_NEG:
        bloqueos.append(f"GAP_EMA7:{gap_ema7:+.3f}%")

    if res['k'] >= adn['k_lim']:
        bloqueos.append(f"K>{adn['k_lim']}")
    if res['k'] <= res['d']:
        bloqueos.append("K<=D")
    if "P<MA" in res.get('block', ''):
        bloqueos.append("P<MA50")

    if bloqueos:
        return False, " | ".join(bloqueos), None

    motivo = "SNIPER" if (slope_1h > 0.10 and vol_r > 1.30) else "ESTANDAR"

    # F_FUNDING: bloquear ESTANDAR si mercado saturado de longs
    # SNIPER tiene señal más fuerte y puede seguir operando
    if res.get('funding_alto', False) and motivo == 'ESTANDAR':
        return False, f"FUNDING_ALTO:{res.get('funding_rate',0):.5f}", None

    return True, "", motivo

# ══════════════════════════════════════════════════════════════
# SEGUIMIENTO POST-TRADE
# ══════════════════════════════════════════════════════════════

def iniciar_seguimiento(simbolo, motivo_salida, p_cierre):
    seguimiento_post[simbolo] = {
        "motivo":     motivo_salida,
        "p_cierre":   p_cierre,
        "t_cierre":   datetime.now(),
        "pendientes": list(POST_TRADE_CHECKPOINTS),
    }

def chequear_post_trade(simbolo, res):
    if simbolo not in seguimiento_post:
        return
    seg = seguimiento_post[simbolo]
    elapsed_min = (datetime.now() - seg["t_cierre"]).total_seconds() / 60
    pendientes_restantes = []
    for cp in seg["pendientes"]:
        if elapsed_min >= cp:
            p_actual = res.get('p', 0)
            retorno  = ((p_actual - seg["p_cierre"]) / seg["p_cierre"]) * 100 if seg["p_cierre"] > 0 else 0
            t_label  = f"{cp}min" if cp < 60 else f"{int(cp//60)}h"
            fin_str  = " --- FIN SEGUIMIENTO" if cp == POST_TRADE_CHECKPOINTS[-1] else ""
            registrar_log(
                f"POST_TRADE [{seg['motivo']}] {simbolo} | t:{t_label} | "
                f"P_cierre:{seg['p_cierre']:.4f} | P_ahora:{p_actual:.4f} | "
                f"Retorno:{retorno:+.3f}% | "
                f"SobreEMA7:{res.get('precio_sobre_ema7', False)} | "
                f"GapEMA7:{res.get('gap_ema7', 0):+.4f}% | "
                f"Cruce15m:{res.get('cruce_15m', '-') or '-'} | "
                f"BTC:{res.get('btc_trend', '?')}{fin_str}"
            )
        else:
            pendientes_restantes.append(cp)
    if pendientes_restantes:
        seguimiento_post[simbolo]["pendientes"] = pendientes_restantes
    else:
        del seguimiento_post[simbolo]

# ══════════════════════════════════════════════════════════════
# NÚCLEO OPERATIVO
# ══════════════════════════════════════════════════════════════

_balance_cache = 0.0        # cache global del balance
_ultimo_fetch_balance = None # última vez que se intentó el fetch
INTERVALO_BALANCE = 60       # segundos entre intentos de fetch_balance

def actualizar_balance():
    """Actualiza el balance desde Binance máximo 1 vez cada 60 segundos.
    Si falla, loguea el error y espera otros 60s antes de reintentar.
    El bot sigue operando con el cache mientras tanto."""
    global _balance_cache, _ultimo_fetch_balance
    ahora = datetime.now()
    if _ultimo_fetch_balance and (ahora - _ultimo_fetch_balance).seconds < INTERVALO_BALANCE:
        return  # todavía no es momento — usar cache
    try:
        _balance_cache = float(exchange.fetch_balance()['total']['USDT'])
        _ultimo_fetch_balance = ahora
    except Exception as e_bal:
        registrar_log(f"WARN fetch_balance: {e_bal} — usando cache {_balance_cache:.2f}")
        _ultimo_fetch_balance = ahora  # espera 60s antes de reintentar

def buscar_oportunidades():
    global _balance_cache
    try:
        estado_bot = cargar_estado()
        actualizar_balance()
        balance = _balance_cache
        ahora      = datetime.now()

        # Display terminal
        if estado_bot["ocupado"] and estado_bot["posiciones"]:
            sim  = list(estado_bot["posiciones"].keys())[0]
            pos  = estado_bot["posiciones"][sim]
            fase = "T1+" if pos.get("t1_hecho") else ("BE+" if pos.get("be_activado") else "")
            estado_str = f"OPEN {sim.split('/')[0]} {fase} Max:{pos.get('g_max',0):+.2f}% Min:{pos.get('g_min',0):+.2f}%"
        else:
            estado_str = "LIBRE"
        sys.stdout.write(f"\r [{ahora.strftime('%H:%M:%S')}] Bal:{balance:.2f} USDT | {estado_str}        ")
        sys.stdout.flush()

        for simbolo in CARTERA:
            adn = DNA_FLOTA[simbolo]
            res = analizar_sniper(simbolo, k_lim=adn['k_lim'], ma_tipo=adn['ma'])
            if not res or not res.get('p'):
                continue

            info_estado = "ESPERA"

            # ── EN POSICIÓN ────────────────────────────────────────
            if simbolo in estado_bot["posiciones"]:
                pos      = estado_bot["posiciones"][simbolo]
                p_ent    = pos['precio_entrada']
                ganancia = ((res['p'] - p_ent) / p_ent) * 100
                info_estado = f"OPEN ({ganancia:+.2f}%)"

                if ganancia > pos.get('g_max', -999):
                    pos['g_max'] = round(ganancia, 4)
                if ganancia < pos.get('g_min', 999):
                    pos['g_min'] = round(ganancia, 4)

                # 1. TRAILING ESCALONADO POST-T1
                if pos.get('t1_hecho'):
                    # Distancia de trailing se ajusta según ganancia actual
                    if ganancia >= 0.80:
                        dist = 0.05
                    elif ganancia >= 0.60:
                        dist = 0.06
                    elif ganancia >= 0.35:
                        dist = 0.08
                    else:
                        dist = 0.20
                    trailing_actual = max(SUELO_POST_T1, ganancia - dist)
                    if trailing_actual > pos.get('trailing_stop', SUELO_POST_T1):
                        pos['trailing_stop'] = trailing_actual
                    if ganancia <= pos['trailing_stop']:
                        exchange.create_market_sell_order(simbolo, pos['cantidad'])
                        cancelar_sl_real(simbolo)
                        subida_post_t1 = round(ganancia - pos.get('g_max_a_t1', T1_TARGET), 4)
                        registrar_log(
                            f"SALIDA [CIERRE_TRAILING] {simbolo} | PnL:{ganancia:+.2f}% | "
                            f"P_entrada:{p_ent:.4f} | P_salida:{res['p']:.4f} | "
                            f"Max:{pos.get('g_max',0):+.2f}% | Min:{pos.get('g_min',0):+.2f}% | "
                            f"Trail:{pos.get('trailing_stop',0):+.2f}% | "
                            f"SubidaPostT1:{subida_post_t1:+.4f}% | "
                            f"Sesion:{pos.get('sesion','?')} | BTC:{pos.get('btc_trend_entrada','?')} | "
                            f"Motivo:{pos.get('motivo_entrada','?')} | "
                            f"GapEMA7:{pos.get('gap_ema7_entrada',0):+.4f}% | "
                            f"Cruce15m:{pos.get('cruce_15m_entrada','-')} | "
                            f"Entrada:{pos.get('f_entrada_str','?')} | "
                            f"ATR_1H_ent:{pos.get('atr_1h_entrada',0):.4f}% | ATR_15M_ent:{pos.get('atr_15m_entrada',0):.4f}% | "
                            f"ATR_1H_now:{res.get('atr_1h',0):.4f}% | ATR_15M_now:{res.get('atr_15m',0):.4f}%"
                        )
                        enviar_telegram(
                            f"*TRAILING*: {simbolo} | PnL:{ganancia:+.2f}% | "
                            f"Max:{pos.get('g_max',0):+.2f}% | Bal:{balance:.2f}$"
                        )
                        iniciar_seguimiento(simbolo, "CIERRE_TRAILING", res['p'])
                        del estado_bot["posiciones"][simbolo]
                        estado_bot["ocupado"] = False
                        continue

                # 2. T1
                elif ganancia >= T1_TARGET and not pos.get('t1_hecho'):
                    mitad = pos['cantidad'] / 2
                    exchange.create_market_sell_order(simbolo, mitad)
                    pos.update({
                        'cantidad':    mitad,
                        't1_hecho':    True,
                        'trailing_stop': SUELO_POST_T1,
                        'precio_t1':   res['p'],
                        'g_max_a_t1':  round(ganancia, 4),
                        't_t1':        ahora.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    cancelar_sl_real(simbolo)
                    nuevo_sl = colocar_sl_real(simbolo, p_ent, mitad)
                    if nuevo_sl:
                        pos['sl_real'] = nuevo_sl
                    registrar_log(
                        f"T1 {simbolo} | P_t1:{res['p']:.4f} | PnL:{ganancia:+.2f}% | "
                        f"Trail_suelo:{SUELO_POST_T1:.2f}% | BTC:{res.get('btc_trend','?')}"
                    )
                    enviar_telegram(
                        f"*T1 ({T1_TARGET}%)*: {simbolo} | Mitad cobrada | "
                        f"P:{res['p']:.4f} | Trail desde {SUELO_POST_T1:.2f}%"
                    )
                    iniciar_seguimiento(simbolo + "_T1", "POST_T1", res['p'])

                # 3. BREAK-EVEN
                elif ganancia >= BE_TRIGGER and not pos.get('be_activado'):
                    pos['be_activado'] = True
                    registrar_log(f"BE_ACTIVADO {simbolo} | ganancia:{ganancia:+.2f}%")
                    enviar_telegram(f"*BE activado*: {simbolo} en {ganancia:+.2f}%")

                # 4. SALIDAS (CORTE_EMA7, RETROCESO_BE, STOP_LOSS)
                if simbolo in estado_bot["posiciones"] and not pos.get('t1_hecho'):
                    ema7_val      = res.get('ema7', 0)
                    corte_ema7    = (ema7_val > 0 and res['p'] < ema7_val and not pos.get('be_activado'))
                    motivo_salida = None

                    if pos.get('be_activado') and ganancia <= BE_STOP:
                        motivo_salida = "RETROCESO_BE"
                    elif not pos.get('be_activado') and ganancia <= STOP_LOSS:
                        motivo_salida = "STOP_LOSS"
                    elif corte_ema7:
                        motivo_salida = "CORTE_EMA7"

                    if motivo_salida:
                        exchange.create_market_sell_order(simbolo, pos['cantidad'])
                        cancelar_sl_real(simbolo)
                        registrar_log(
                            f"SALIDA [{motivo_salida}] {simbolo} | PnL:{ganancia:+.2f}% | "
                            f"P_entrada:{p_ent:.4f} | P_salida:{res['p']:.4f} | "
                            f"Max:{pos.get('g_max',0):+.2f}% | Min:{pos.get('g_min',0):+.2f}% | "
                            f"Sesion:{pos.get('sesion','?')} | BTC:{pos.get('btc_trend_entrada','?')} | "
                            f"Motivo:{pos.get('motivo_entrada','?')} | "
                            f"GapEMA7:{pos.get('gap_ema7_entrada',0):+.4f}% | "
                            f"Cruce15m:{pos.get('cruce_15m_entrada','-')} | "
                            f"VelasCruce15m:{pos.get('velas_cruce_entrada',-1)} | "
                            f"Entrada:{pos.get('f_entrada_str','?')} | "
                            f"ATR_1H_ent:{pos.get('atr_1h_entrada',0):.4f}% | ATR_15M_ent:{pos.get('atr_15m_entrada',0):.4f}% | "
                            f"ATR_1H_now:{res.get('atr_1h',0):.4f}% | ATR_15M_now:{res.get('atr_15m',0):.4f}%"
                        )
                        enviar_telegram(
                            f"*{motivo_salida}*: {simbolo} | PnL:{ganancia:+.2f}% | "
                            f"Max:{pos.get('g_max',0):+.2f}% Min:{pos.get('g_min',0):+.2f}% | "
                            f"Bal:{balance:.2f}$"
                        )
                        if motivo_salida == "STOP_LOSS":
                            bloqueo_stop[simbolo] = ahora + timedelta(minutes=BLOQUEO_SL_MIN)
                            registrar_log(
                                f"BLOQUEO_SL {simbolo} | {BLOQUEO_SL_MIN}min hasta "
                                f"{bloqueo_stop[simbolo].strftime('%H:%M:%S')}"
                            )
                        elif motivo_salida == "RETROCESO_BE":
                            bloqueo_stop[simbolo] = ahora + timedelta(minutes=BLOQUEO_SL_MIN)
                            registrar_log(
                                f"BLOQUEO_BE {simbolo} | {BLOQUEO_SL_MIN}min hasta "
                                f"{bloqueo_stop[simbolo].strftime('%H:%M:%S')}"
                            )
                        iniciar_seguimiento(simbolo, motivo_salida, res['p'])
                        del estado_bot["posiciones"][simbolo]
                        estado_bot["ocupado"] = False

            # ── BUSCAR ENTRADA ──────────────────────────────────────
            elif not estado_bot["ocupado"]:
                # Bloqueo post-stop
                if simbolo in bloqueo_stop and ahora < bloqueo_stop[simbolo]:
                    mins = (bloqueo_stop[simbolo] - ahora).total_seconds() / 60
                    info_estado = f"BLOQ_SL ({mins:.0f}min)"
                else:
                    if simbolo in bloqueo_stop:
                        del bloqueo_stop[simbolo]

                    pasa, bloqueos_str, motivo = evaluar_filtros_sniper(res, adn)

                    if pasa:
                        monto_usdt      = balance * 0.95
                        cantidad_tokens = monto_usdt / res['p']
                        orden           = exchange.create_market_buy_order(simbolo, cantidad_tokens)
                        precio_sl_real  = colocar_sl_real(simbolo, res['p'], orden['amount'])

                        hora_utc = utcnow().strftime("%H:%M")
                        h_utc    = utcnow().hour
                        sesion   = "ASIATICA" if h_utc < 8 else ("EUROPEA" if h_utc < 16 else "AMERICANA")

                        estado_bot["posiciones"][simbolo] = {
                            "precio_entrada":      res['p'],
                            "cantidad":            orden['amount'],
                            "sl_real":             precio_sl_real,
                            "t1_hecho":            False,
                            "be_activado":         False,
                            "trailing_stop":       SUELO_POST_T1,
                            "g_max":               0.0,
                            "g_min":               0.0,
                            "sesion":              sesion,
                            "motivo_entrada":      motivo,
                            "f_entrada_str":       ahora.strftime("%Y-%m-%d %H:%M"),
                            "hora_utc_entrada":    hora_utc,
                            "slope_entrada":       round(res.get('pendiente_7', 0), 4),
                            "slope_15m_entrada":   round(res.get('slope_ema5_15m', 0), 4),
                            "vol_r_entrada":       round(res.get('vol_r', 0), 2),
                            "gap_ema7_entrada":    round(res.get('gap_ema7', 0), 4),
                            "precio_sobre_ema7":   res.get('precio_sobre_ema7', False),
                            "cruce_15m_entrada":   res.get('cruce_15m', '-'),
                            "velas_cruce_entrada": res.get('velas_desde_cruce', -1),
                            "cruce_1h_entrada":    res.get('cruce_1h', '-'),
                            "btc_trend_entrada":   res.get('btc_trend', '?'),
                            "gap200_entrada":      round(res.get('gap200', 0), 2),
                            "k_entrada":           round(res.get('k', 0), 1),
                            "d_entrada":           round(res.get('d', 0), 1),
                            # ATR al momento de entrada
                            "atr_1h_entrada":      round(res.get('atr_1h', 0), 4),
                            "atr_15m_entrada":     round(res.get('atr_15m', 0), 4),
                            "atr_5m_entrada":      round(res.get('atr_5m', 0), 4),
                            # OHLC al momento de entrada
                            "h_1h_entrada":        round(res.get('h_1h', 0), 4),
                            "l_1h_entrada":        round(res.get('l_1h', 0), 4),
                            "h_15m_entrada":       round(res.get('h_15m', 0), 4),
                            "l_15m_entrada":       round(res.get('l_15m', 0), 4),
                        }
                        estado_bot["ocupado"] = True
                        info_estado = "DISPARANDO"
                        registrar_log(
                            f"ENTRADA [{motivo}] {simbolo} | "
                            f"P:{res['p']:.4f} | HORA:{hora_utc}UTC | SESION:{sesion} | "
                            f"K:{res.get('k',0):.1f} D:{res.get('d',0):.1f} | "
                            f"Slope1h:{res.get('pendiente_7',0):+.4f}% | "
                            f"Slope15m:{res.get('slope_ema5_15m',0):+.3f}% | "
                            f"VolR:{res.get('vol_r',0):.2f}x | "
                            f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | "
                            f"SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                            f"Cruce15m:{res.get('cruce_15m','-')} | "
                            f"VelasCruce15m:{res.get('velas_desde_cruce',-1)} | "
                            f"Cruce1h:{res.get('cruce_1h','-')} | "
                            f"BTC:{res.get('btc_trend','?')} | "
                            f"Gap200:{res.get('gap200',0):+.2f}% | "
                            f"H_1H:{res.get('h_1h',0):.4f} | L_1H:{res.get('l_1h',0):.4f} | "
                            f"H_15M:{res.get('h_15m',0):.4f} | L_15M:{res.get('l_15m',0):.4f} | "
                            f"ATR_1H:{res.get('atr_1h',0):.4f}% | ATR_15M:{res.get('atr_15m',0):.4f}% | ATR_5M:{res.get('atr_5m',0):.4f}% | "
                            f"Funding:{res.get('funding_rate',0):.5f} | GapVWAP:{res.get('gap_vwap',0):+.4f}% | "
                            f"K15m:{res.get('k_15m',50):.1f} | D15m:{res.get('d_15m',50):.1f} | "
                            f"Cuerpo1H:{res.get('cuerpo_1h',0):.3f} | VelaAlc:{res.get('vela_alcista_1h',False)} | "
                            f"OBV_slope:{res.get('obv_slope',0):+.4f}%"
                        )
                        enviar_telegram(
                            f"*ENTRADA [{motivo}]*: {simbolo}\n"
                            f"P:{res['p']:.4f} | K:{res.get('k',0):.1f} | "
                            f"Slope:{res.get('pendiente_7',0):+.3f}% | VolR:{res.get('vol_r',0):.1f}x\n"
                            f"BTC:{res.get('btc_trend','?')} | {sesion} {hora_utc}UTC"
                        )
                    else:
                        info_estado = f"BLOQ:{bloqueos_str[:50]}"

            # SCAN log
            chequear_post_trade(simbolo, res)
            registrar_log(
                f"SCAN {simbolo} | HORA:{utcnow().strftime('%H:%M')}UTC | "
                f"P:{res.get('p',0):.4f} | "
                f"Slope1h:{res.get('pendiente_7',0):+.4f}% | "
                f"VolR:{res.get('vol_r',0):.2f}x | "
                f"K:{res.get('k',0):.1f} | D:{res.get('d',0):.1f} | "
                f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                f"Cruce1h:{res.get('cruce_1h','-') or '-'} | "
                f"Slope15m:{res.get('slope_ema5_15m',0):+.3f}% | "
                f"Cruce15m:{res.get('cruce_15m','-') or '-'} | "
                f"VelasCruce15m:{res.get('velas_desde_cruce',-1)} | "
                f"BTC:{res.get('btc_trend','?')} | "
                f"BLOCK:{res.get('block',''):15s} | Estado:{info_estado} | "
                f"ATR_1H:{res.get('atr_1h',0):.4f}% | ATR_15M:{res.get('atr_15m',0):.4f}% | "
                f"Funding:{res.get('funding_rate',0):.5f} | FundAlto:{res.get('funding_alto',False)} | "
                f"GapVWAP:{res.get('gap_vwap',0):+.4f}% | "
                f"K15m:{res.get('k_15m',50):.1f} | D15m:{res.get('d_15m',50):.1f} | "
                f"Cuerpo1H:{res.get('cuerpo_1h',0):.3f} | VelaAlc:{res.get('vela_alcista_1h',False)} | "
                f"OBV:{res.get('obv_slope',0):+.4f}%"
            )

        guardar_estado(estado_bot)

    except Exception as e:
        registrar_log(f"ERROR: {e}")
        _detectar_error_binance(e)

# ══════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    time.sleep(3)

    # ── Banner de terminal ─────────────────────────────────────────────────
    print("💰 BOT MAESTRO V4.0 — Capital Real Binance Futures")
    print("━" * 51)
    print(f"📊 T1={T1_TARGET}% | BE={BE_TRIGGER}% | SL={STOP_LOSS}%")
    print(f"🛡️  SL Real={SL_REAL_PCT}% | Trail={TRAILING_DIST}% | BloqueoSL={BLOQUEO_SL_MIN}min")
    print(f"🔍 Filtros activos:")
    print(f"   BTC!=BAJISTA | Slope15m>={MIN_SLOPE_15M}% | Slope1H>={MIN_SLOPE_1H}%")
    print(f"   Vol_R>={MIN_VOL_R}x | Funding block | BE_LOCK={BLOQUEO_SL_MIN}min")
    print(f"🎯 Flota: {', '.join(s.split('/')[0] for s in CARTERA)}")
    print(f"⏱️  Escaneo: 5s libre | 1s en posición")
    print("━" * 51)

    # ── Log inmediato — antes del sync para garantizar que quede registrado ─
    registrar_log(
        f"=== BOT V4.0 INICIADO === "
        f"SL:{STOP_LOSS}% BE:{BE_TRIGGER}% T1:{T1_TARGET}% "
        f"Trail:{TRAILING_DIST}% SL_Real:{SL_REAL_PCT}% BloqueoSL:{BLOQUEO_SL_MIN}min "
        f"Filtros: Slope1H>={MIN_SLOPE_1H}% VolR>={MIN_VOL_R}x Slope15m>={MIN_SLOPE_15M}%"
    )

    # ── Sincronizar con Binance antes de arrancar ──────────────────────────
    _estado = cargar_estado()
    _estado = sincronizar_con_binance(_estado)

    enviar_telegram(
        f"*Bot V4.0 Online*\n"
        f"SL:{STOP_LOSS}% | BE:{BE_TRIGGER}% | T1:{T1_TARGET}%\n"
        f"SL Real:{SL_REAL_PCT}% | Bloqueo SL:{BLOQUEO_SL_MIN}min\n"
        f"Filtros SNIPER: Slope1H>={MIN_SLOPE_1H}% VolR>={MIN_VOL_R}x Slope15m>={MIN_SLOPE_15M}%"
    )

    ultimo_hb = time.time()
    while True:
        buscar_oportunidades()
        if time.time() - ultimo_hb >= 21600:
            try:
                bal = float(exchange.fetch_balance()['total']['USDT'])
            except:
                bal = 0
            enviar_telegram(
                f"Heartbeat V4.0 | Bal:{bal:.2f}$ | {datetime.now().strftime('%d/%m %H:%M')}"
            )
            ultimo_hb = time.time()
        time.sleep(5)