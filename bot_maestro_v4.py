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

# ══════════════════════════════════════════════════════════════
#  TRANSPLANTE DE CEREBRO (W24) — cerebro del simulador + C1/C2/C3
#  El CUERPO (órdenes reales, SL real stop_market, sync, 1 posición,
#  Telegram) queda intacto. Cambia solo el CEREBRO (filtros + params).
#  Ver analisis/ANALISIS_ESTRATEGIA.md (paquete R2) y DEPLOY_W24.md.
# ══════════════════════════════════════════════════════════════

# --- PARÁMETROS DE TRADING (= simulador) ---
STOP_LOSS     = -0.85   # % pérdida máxima (sim, era -1.00)
BE_TRIGGER    =  0.15   # % ganancia para activar break-even (sim, era 0.20)
BE_STOP       =  0.10   # % nivel de salida con BE activo (RETROCESO_BE)
T1_TARGET     =  0.25   # % para cerrar mitad de posición (sim, era 0.35)
SL_REAL_PCT   =  0.85   # % SL real en Binance — INTACTO (seguro ante crashes)
FILTRO_BTC    = True    # bloquear si BTC_TREND_SUAV == BAJISTA

# Trailing 2 niveles (= simulador): base 0.20% hasta +0.40%, luego aprieta a 0.10%
SUELO_POST_T1   = T1_TARGET   # 0.25 — nunca cierra por debajo de T1 post-T1
TRAILING_DIST   = 0.20        # distancia base
TRAILING2_DIST  = 0.10        # distancia apretada
TRAILING2_DESDE = 0.40        # nivel donde aprieta

# --- FILTROS DE ENTRADA (= simulador) ---
MIN_SLOPE_1H        = 0.10   # F2: pendiente mínima EMA7 1H
MIN_VOL_R           = 0.30   # F1: volumen relativo mínimo
MIN_SLOPE_15M       = 0.05   # pendiente mínima EMA5 15M
VOL_SNIPER          = 1.30   # vol_r para clasificar SNIPER
MAX_GAP200          = 4.0    # gap200 máximo (%)
FILTRO_ASIA_STD_ALC = True   # F3: bloquear ESTANDAR+ASIATICA+BTC:ALC

# --- C1: piso de volatilidad en entrada (análisis R2) ---
MIN_ATR_15M = 0.45   # no entrar si ATR_15m < 0.45%

# --- C2: time-stop ---
TIME_STOP_MIN = 45   # cerrar a los 45min si no superó BE

# --- C3: entradas LIMIT (maker) ---
USAR_LIMIT_ENTRY = True   # entradas post-only (maker) en vez de market
LIMIT_TIMEOUT_S  = 60     # si no llena en 60s → cancela y descarta señal (NO_FILL)

# --- DRY-RUN (Fase 3: verificación sin plata real) ---
# Con BOT_DRY_RUN=1: corre con datos de mercado REALES y toda la lógica/logs/
# Telegram, pero NO coloca NINGUNA orden (entrada, SL ni ventas son simuladas).
DRY_RUN = os.getenv('BOT_DRY_RUN', '0') == '1'

# --- BLOQUEO POST-PÉRDIDA (BE_LOCK) ---
BLOQUEO_SL_MIN = 15       # minutos bloqueado tras STOP_LOSS y RETROCESO_BE
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
        # SIN parse_mode: los nombres con guion bajo (BE_STOP, CORTE_EMA7,
        # RETROCESO_BE, etc.) rompían el Markdown y Telegram descartaba el
        # mensaje en silencio. Texto plano = entrega garantizada.
        # Se quitan los '*' (marcadores de negrita) para que no queden literales.
        requests.post(
            f"https://api.telegram.org/bot{TOKEN_TLG}/sendMessage",
            json={"chat_id": CHAT_ID_TLG, "text": m.replace('*', '')},
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
    if DRY_RUN:
        precio_sl = round(precio_entrada * (1 - SL_REAL_PCT / 100), 4)
        registrar_log(f"DRY_RUN SL_REAL {simbolo} | SL:{precio_sl:.4f} (no se coloca orden)")
        return precio_sl
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
    if DRY_RUN:
        return
    try:
        ordenes = exchange.fetch_open_orders(simbolo)
        for o in ordenes:
            if o.get('type') in ('stop_market', 'stop') and o.get('side') == 'sell':
                exchange.cancel_order(o['id'], simbolo)
                registrar_log(f"SL_REAL cancelado {simbolo} | orden:{o['id']}")
    except Exception as e:
        registrar_log(f"ERROR cancelar SL_REAL {simbolo}: {e}")

def _vender_market(simbolo, cantidad):
    """Venta market. En DRY_RUN no coloca orden (devuelve dict vacío)."""
    if DRY_RUN:
        registrar_log(f"DRY_RUN venta market {simbolo} x{cantidad} (no se coloca orden)")
        return {}
    return exchange.create_market_sell_order(simbolo, cantidad)

# ══════════════════════════════════════════════════════════════
# C3 — ENTRADA LIMIT POST-ONLY (maker)
# ══════════════════════════════════════════════════════════════

def entrar_limit_maker(simbolo, monto_usdt, precio_ref):
    """
    Coloca una orden LIMIT post-only (maker) al mejor bid y espera hasta
    LIMIT_TIMEOUT_S. Si llena → retorna info de ejecución. Si no llena (o la
    rechaza post-only) → cancela y retorna None (la señal se DESCARTA, no se
    persigue el precio). Las salidas siguen siendo market; esto solo afecta
    la entrada.
    Retorna dict(fill_price, fill_amount, fee_usdt, intended_price, order_id,
                 parcial) o None.
    """
    try:
        ob = exchange.fetch_order_book(simbolo, limit=5)
        best_bid = ob['bids'][0][0] if ob.get('bids') else precio_ref
    except Exception:
        best_bid = precio_ref
    precio_limit = round(best_bid, 4)
    cantidad = monto_usdt / precio_limit
    if DRY_RUN:
        registrar_log(f"DRY_RUN entrada limit maker {simbolo} | P:{precio_limit:.4f} | qty:{cantidad:.6f} (no se coloca orden)")
        return dict(fill_price=precio_limit, fill_amount=cantidad,
                    fee_usdt=round(monto_usdt * 0.0002, 6),
                    intended_price=precio_limit, order_id='DRY', parcial=False)
    try:
        orden = exchange.create_order(
            simbolo, 'limit', 'buy', cantidad, precio_limit,
            params={'postOnly': True}
        )
    except Exception as e:
        registrar_log(f"NO_FILL {simbolo} | error al colocar limit: {e}")
        return None

    oid = orden['id']
    t0 = time.time()
    while time.time() - t0 < LIMIT_TIMEOUT_S:
        time.sleep(2)
        try:
            o = exchange.fetch_order(oid, simbolo)
        except Exception:
            continue
        st     = o.get('status')
        filled = float(o.get('filled') or 0)
        if st == 'closed' and filled > 0:
            return _info_fill(o, precio_limit, oid, parcial=False)
        if st in ('canceled', 'rejected', 'expired'):
            registrar_log(f"NO_FILL {simbolo} | limit {st} (post-only) — descarta señal")
            return None

    # Timeout — usar parcial si lo hubo, cancelar el resto
    try:
        o = exchange.fetch_order(oid, simbolo)
        filled = float(o.get('filled') or 0)
        try:
            exchange.cancel_order(oid, simbolo)
        except Exception:
            pass
        if filled > 0:
            return _info_fill(o, precio_limit, oid, parcial=True)
    except Exception:
        pass
    registrar_log(f"NO_FILL {simbolo} | sin ejecución en {LIMIT_TIMEOUT_S}s — descarta señal")
    return None

def _info_fill(o, precio_limit, oid, parcial):
    fill_price = float(o.get('average') or o.get('price') or precio_limit)
    fill_amount = float(o.get('filled') or 0)
    fee_usdt = 0.0
    fee = o.get('fee') or {}
    if fee.get('cost'):
        fee_usdt = float(fee['cost'])
    elif o.get('fees'):
        for fobj in o['fees']:
            if fobj.get('cost'):
                fee_usdt += float(fobj['cost'])
    return dict(fill_price=fill_price, fill_amount=fill_amount, fee_usdt=fee_usdt,
                intended_price=precio_limit, order_id=oid, parcial=parcial)

# ══════════════════════════════════════════════════════════════
# INSTRUMENTACIÓN — comisión real + registro completo por trade
# ══════════════════════════════════════════════════════════════

def _fee_de_orden(orden):
    """Extrae la comisión pagada (USDT) de una orden ccxt, best-effort."""
    try:
        fee = (orden or {}).get('fee') or {}
        if fee.get('cost'):
            return abs(float(fee['cost']))
        tot = 0.0
        for f in (orden.get('fees') or []):
            if f.get('cost'):
                tot += abs(float(f['cost']))
        return tot
    except Exception:
        return 0.0

def registrar_trade_real(simbolo, pos, res, motivo_salida, ganancia, balance, ahora):
    """Registro COMPLETO por trade (gross, comisión real, net, intentado vs
    llenado, duración, régimen) + alerta Telegram por-trade del REAL."""
    p_ent = pos['precio_entrada']
    if motivo_salida == "CIERRE_TRAILING":
        gross_pct = 0.5 * T1_TARGET + 0.5 * ganancia      # convención del análisis
    else:
        gross_pct = ganancia
    notional = pos.get('notional_usdt', 0) or (p_ent * pos.get('cantidad_orig', 0))
    com_usdt = pos.get('comisiones_usdt', 0.0)
    com_pct  = (com_usdt / notional * 100) if notional else 0.0
    net_pct  = gross_pct - com_pct
    try:
        t_ent = datetime.strptime(pos.get('t_entrada_iso', ''), "%Y-%m-%d %H:%M:%S")
        dur_min = round((ahora - t_ent).total_seconds() / 60, 1)
    except Exception:
        dur_min = -1
    intentado = pos.get('precio_intentado', p_ent)
    registrar_log(
        f"TRADE REAL | {motivo_salida} | {simbolo} | motivo_ent:{pos.get('motivo_entrada','?')} | "
        f"gross:{gross_pct:+.4f}% | comision:{com_usdt:.5f}USDT({com_pct:.4f}%) | net:{net_pct:+.4f}% | "
        f"P_intentado:{intentado:.4f} | P_llenado:{p_ent:.4f} | slippage_ent:{pos.get('slippage_pct',0):+.4f}% | "
        f"P_salida:{res['p']:.4f} | max:{pos.get('g_max',0):+.3f}% | min:{pos.get('g_min',0):+.3f}% | "
        f"dur_min:{dur_min} | sesion:{pos.get('sesion','?')} | t1:{pos.get('t1_hecho',False)} | be:{pos.get('be_activado',False)} | "
        f"slope1h:{pos.get('slope_entrada',0):+.3f}% | vol_r:{pos.get('vol_r_entrada',0):.2f} | atr15m:{pos.get('atr_15m_entrada',0):.3f}% | "
        f"k:{pos.get('k_entrada',0):.1f} | btc_suav:{pos.get('btc_trend_entrada','?')} | "
        f"btc_ret1h_now:{res.get('btc_retorno_1h',0):+.3f}% | bal:{balance:.4f}"
    )
    enviar_telegram(
        f"🔴 *REAL · CIERRE {simbolo.split('/')[0]} LONG*\n"
        f"{motivo_salida} | Dur:{dur_min:.0f}min\n"
        f"Intent:{intentado:.4f} → Fill:{p_ent:.4f} ({pos.get('slippage_pct',0):+.3f}%)\n"
        f"Salida:{res['p']:.4f}\n"
        f"PnL neto:{net_pct:+.3f}% | Comisión:${com_usdt:.4f} | Bal:${balance:.2f}"
    )

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

def evaluar_filtros_sniper(res, adn, sesion):
    """
    CEREBRO DEL SIMULADOR + C1 (piso ATR). Usa btc_trend_suav (no el directo).
    El BE_LOCK (F4) se gestiona en el loop (bloqueo_stop), no acá.
    Retorna (pasa: bool, bloqueos_str: str, motivo_entrada: str|None)
    """
    pendiente_7 = res.get('pendiente_7', 0)
    vol_r       = res.get('vol_r', 0)
    btc_suav    = res.get('btc_trend_suav', res.get('btc_trend', ''))
    slope_15m   = res.get('slope_ema5_15m', 0)
    gap200      = res.get('gap200', 0)
    block       = res.get('block', '')
    atr_15m     = res.get('atr_15m', 0)

    # --- Tipo de señal (igual que el sim) ---
    pendiente_alta = pendiente_7 > 0.10
    vol_confirmado = vol_r > VOL_SNIPER
    tecnica_limpia = (block == "")
    if pendiente_alta and vol_confirmado:
        motivo = "SNIPER"
    elif tecnica_limpia and pendiente_7 > MIN_SLOPE_1H:
        motivo = "ESTANDAR"
    else:
        motivo = None

    bloqueos = []
    if motivo is None:
        bloqueos.append("SIN_MOTIVO")
    # --- Filtros generales ---
    if FILTRO_BTC and btc_suav == 'BAJISTA':
        bloqueos.append("BTC_BAJISTA")
    if slope_15m <= MIN_SLOPE_15M:
        bloqueos.append(f"SLOPE_15M:{slope_15m:+.3f}%")
    if gap200 > MAX_GAP200:
        bloqueos.append(f"GAP200:{gap200:.2f}%")
    # F1: volumen mínimo
    if vol_r < MIN_VOL_R:
        bloqueos.append(f"VOL_R:{vol_r:.2f}x")
    # F2: K(15m) subiendo
    k15 = res.get('k_15m', 50); d15 = res.get('d_15m', 50)
    pasa_k15m = res.get('k_15m_mayor_d', False) or (k15 - d15) > -5
    if not pasa_k15m:
        bloqueos.append(f"K15M:{k15:.1f}<=D15M:{d15:.1f}")
    # F3: ESTANDAR+ASIATICA+BTC:ALCISTA
    if motivo == "ESTANDAR" and sesion == "ASIATICA" and btc_suav == "ALCISTA" and FILTRO_ASIA_STD_ALC:
        bloqueos.append("ESTANDAR+ASIA+ALC")
    # F5: funding alto bloquea ESTANDAR (SNIPER puede)
    if res.get('funding_alto', False) and motivo == "ESTANDAR":
        bloqueos.append(f"FUNDING_ALTO:{res.get('funding_rate',0):.5f}")
    # C1: piso de volatilidad (análisis R2)
    if atr_15m < MIN_ATR_15M:
        bloqueos.append(f"ATR15M:{atr_15m:.3f}<{MIN_ATR_15M}")

    if bloqueos:
        return False, " | ".join(bloqueos), None
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
        # Solo escribir el display en vivo si hay terminal interactiva (TTY).
        # Bajo systemd no hay TTY: evita que los '\r' inunden el journal del sistema.
        if sys.stdout.isatty():
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

                # 1. TRAILING 2 NIVELES POST-T1 (= simulador)
                if pos.get('t1_hecho'):
                    # base 0.20% hasta +0.40%, luego aprieta a 0.10%
                    dist = TRAILING2_DIST if ganancia >= TRAILING2_DESDE else TRAILING_DIST
                    trailing_actual = max(SUELO_POST_T1, ganancia - dist)
                    if trailing_actual > pos.get('trailing_stop', SUELO_POST_T1):
                        pos['trailing_stop'] = trailing_actual
                    if ganancia <= pos['trailing_stop']:
                        _osell = _vender_market(simbolo, pos['cantidad'])
                        pos['comisiones_usdt'] = pos.get('comisiones_usdt', 0.0) + _fee_de_orden(_osell)
                        cancelar_sl_real(simbolo)
                        registrar_trade_real(simbolo, pos, res, "CIERRE_TRAILING", ganancia, balance, ahora)
                        iniciar_seguimiento(simbolo, "CIERRE_TRAILING", res['p'])
                        del estado_bot["posiciones"][simbolo]
                        estado_bot["ocupado"] = False
                        continue

                # 2. T1
                elif ganancia >= T1_TARGET and not pos.get('t1_hecho'):
                    mitad = pos['cantidad'] / 2
                    _ot1 = _vender_market(simbolo, mitad)
                    pos['comisiones_usdt'] = pos.get('comisiones_usdt', 0.0) + _fee_de_orden(_ot1)
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
                    # C2: time-stop — trade que no superó BE en TIME_STOP_MIN minutos
                    elif (not pos.get('be_activado')) and pos.get('t_entrada_iso'):
                        try:
                            _t_ent = datetime.strptime(pos['t_entrada_iso'], "%Y-%m-%d %H:%M:%S")
                            if (ahora - _t_ent).total_seconds() >= TIME_STOP_MIN * 60:
                                motivo_salida = "TIME_STOP"
                        except Exception:
                            pass

                    if motivo_salida:
                        _osell = _vender_market(simbolo, pos['cantidad'])
                        pos['comisiones_usdt'] = pos.get('comisiones_usdt', 0.0) + _fee_de_orden(_osell)
                        cancelar_sl_real(simbolo)
                        registrar_trade_real(simbolo, pos, res, motivo_salida, ganancia, balance, ahora)
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

                    hora_utc = utcnow().strftime("%H:%M")
                    h_utc    = utcnow().hour
                    sesion   = "ASIATICA" if h_utc < 8 else ("EUROPEA" if h_utc < 16 else "AMERICANA")

                    pasa, bloqueos_str, motivo = evaluar_filtros_sniper(res, adn, sesion)

                    fill = None
                    if pasa:
                        # C3: entrada LIMIT post-only (maker). Si no llena → descarta señal.
                        if USAR_LIMIT_ENTRY:
                            fill = entrar_limit_maker(simbolo, balance * 0.95, res['p'])
                            if fill is None:
                                pasa = False
                                info_estado = "NO_FILL"
                        elif DRY_RUN:
                            _amt = (balance * 0.95) / res['p']
                            registrar_log(f"DRY_RUN compra market {simbolo} qty:{_amt:.6f} (no se coloca orden)")
                            fill = dict(fill_price=res['p'], fill_amount=_amt,
                                        fee_usdt=0.0, intended_price=res['p'], parcial=False)
                        else:
                            _orden = exchange.create_market_buy_order(simbolo, (balance * 0.95) / res['p'])
                            fill = dict(fill_price=res['p'], fill_amount=_orden['amount'],
                                        fee_usdt=0.0, intended_price=res['p'], parcial=False)

                    if pasa and fill:
                        p_fill         = fill['fill_price']
                        cantidad       = fill['fill_amount']
                        precio_sl_real = colocar_sl_real(simbolo, p_fill, cantidad)
                        intentado      = fill['intended_price']
                        slippage_pct   = round((p_fill - intentado) / intentado * 100, 4) if intentado else 0.0
                        btc_ent        = res.get('btc_trend_suav', res.get('btc_trend', '?'))

                        estado_bot["posiciones"][simbolo] = {
                            "precio_entrada":      p_fill,
                            "cantidad":            cantidad,
                            "sl_real":             precio_sl_real,
                            "t1_hecho":            False,
                            "be_activado":         False,
                            "trailing_stop":       SUELO_POST_T1,
                            "g_max":               0.0,
                            "g_min":               0.0,
                            "sesion":              sesion,
                            "motivo_entrada":      motivo,
                            "f_entrada_str":       ahora.strftime("%Y-%m-%d %H:%M"),
                            "t_entrada_iso":       ahora.strftime("%Y-%m-%d %H:%M:%S"),
                            "hora_utc_entrada":    hora_utc,
                            # C3 instrumentación
                            "precio_intentado":      intentado,
                            "precio_llenado":        p_fill,
                            "slippage_pct":          slippage_pct,
                            "comision_entrada_usdt": round(fill.get('fee_usdt', 0.0), 6),
                            "fill_parcial":          fill.get('parcial', False),
                            "notional_usdt":         round(p_fill * cantidad, 4),
                            "comisiones_usdt":       round(fill.get('fee_usdt', 0.0), 6),
                            "cantidad_orig":         cantidad,
                            "slope_entrada":       round(res.get('pendiente_7', 0), 4),
                            "slope_15m_entrada":   round(res.get('slope_ema5_15m', 0), 4),
                            "vol_r_entrada":       round(res.get('vol_r', 0), 2),
                            "gap_ema7_entrada":    round(res.get('gap_ema7', 0), 4),
                            "precio_sobre_ema7":   res.get('precio_sobre_ema7', False),
                            "cruce_15m_entrada":   res.get('cruce_15m', '-'),
                            "velas_cruce_entrada": res.get('velas_desde_cruce', -1),
                            "cruce_1h_entrada":    res.get('cruce_1h', '-'),
                            "btc_trend_entrada":   btc_ent,
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
                            f"P_intentado:{intentado:.4f} | P_llenado:{p_fill:.4f} | Slippage:{slippage_pct:+.4f}% | "
                            f"ComEnt:{fill.get('fee_usdt',0.0):.5f}USDT | Parcial:{fill.get('parcial',False)} | "
                            f"HORA:{hora_utc}UTC | SESION:{sesion} | "
                            f"K:{res.get('k',0):.1f} D:{res.get('d',0):.1f} | "
                            f"Slope1h:{res.get('pendiente_7',0):+.4f}% | "
                            f"Slope15m:{res.get('slope_ema5_15m',0):+.3f}% | "
                            f"VolR:{res.get('vol_r',0):.2f}x | "
                            f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | "
                            f"SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                            f"Cruce15m:{res.get('cruce_15m','-')} | "
                            f"VelasCruce15m:{res.get('velas_desde_cruce',-1)} | "
                            f"Cruce1h:{res.get('cruce_1h','-')} | "
                            f"BTC_suav:{btc_ent} | BTC:{res.get('btc_trend','?')} | "
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
                            f"Intent:{intentado:.4f} → Fill:{p_fill:.4f} ({slippage_pct:+.3f}%)\n"
                            f"K:{res.get('k',0):.1f} | Slope:{res.get('pendiente_7',0):+.3f}% | "
                            f"VolR:{res.get('vol_r',0):.1f}x | ATR15m:{res.get('atr_15m',0):.2f}%\n"
                            f"BTC:{btc_ent} | {sesion} {hora_utc}UTC"
                        )
                    elif info_estado != "NO_FILL":
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
# RESUMEN DIARIO COMBINADO (real + campeón + retador)
# ══════════════════════════════════════════════════════════════

def _leer_balance_json(path, default=0.0):
    try:
        with open(path) as f:
            return float(json.load(f).get('balance', default))
    except Exception:
        return default

def _stats_trades_hoy(path, etiqueta):
    """Cuenta trades del día y suma net% desde un archivo de registros TRADE."""
    import re
    hoy = datetime.now().strftime("%Y-%m-%d")
    n = wins = 0; net_sum = 0.0
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith(f"[{hoy}") and f"{etiqueta} " in ln and "net:" in ln:
                    m = re.search(r"net:([+-]?\d+\.?\d*)%", ln)
                    if m:
                        v = float(m.group(1)); n += 1; net_sum += v
                        if v > 0:
                            wins += 1
    except Exception:
        pass
    return n, wins, net_sum

def _btc_dia_pct():
    try:
        velas = exchange.fetch_ohlcv('BTC/USDT:USDT', '1d', limit=1)
        if velas:
            o = velas[-1][1]; c = velas[-1][4]
            return (c - o) / o * 100 if o else 0.0
    except Exception:
        pass
    return 0.0

def _fill_rate_hoy():
    """Tasa de fill de las entradas LIMIT del real hoy (ENTRADA vs NO_FILL)."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    fills = nofills = 0
    try:
        with open(RUTA_TRADES, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith(f"[{hoy}"):
                    if "ENTRADA [" in ln:
                        fills += 1
                    elif "NO_FILL " in ln:
                        nofills += 1
    except Exception:
        pass
    return fills, nofills

def resumen_diario_combinado(balance_real):
    bal_camp = _leer_balance_json(os.path.join(BASE_DIR, "estado_campeon.json"))
    bal_ret  = _leer_balance_json(os.path.join(BASE_DIR, "estado_retador.json"))
    nR, wR, netR = _stats_trades_hoy(RUTA_TRADES, "TRADE REAL")
    fills, nofills = _fill_rate_hoy()
    intentos = fills + nofills
    fill_str = f"{fills}/{intentos} ({100*fills/intentos:.0f}%)" if intentos else "—"
    nC, wC, netC = _stats_trades_hoy(os.path.join(BASE_DIR, "logs_campeon", "trades_campeon.txt"), "TRADE CAMPEON")
    nT, wT, netT = _stats_trades_hoy(os.path.join(BASE_DIR, "logs_retador", "trades_retador.txt"), "TRADE RETADOR")
    btc = _btc_dia_pct()
    def wr(n, w):
        return f"{100*w/n:.0f}%" if n else "—"
    delta = netR - netC
    enviar_telegram(
        f"📊 *RESUMEN DIARIO* — {datetime.now():%d/%m/%Y}\n"
        f"Régimen: BTC {btc:+.1f}% (día)\n\n"
        f"🔴 *REAL* (cerebro nuevo)\n"
        f"Bal: ${balance_real:.2f} | Trades: {nR} | WR: {wr(nR,wR)} | PnL neto: {netR:+.2f}%\n"
        f"Fills limit: {fill_str}\n\n"
        f"🔵 *CAMPEÓN* (paper, mismo cerebro)\n"
        f"Bal: ${bal_camp:.2f} | Trades: {nC} | WR: {wr(nC,wC)} | PnL neto: {netC:+.2f}%\n\n"
        f"Δ REAL vs CAMPEÓN: {delta:+.2f}pp (ejecución)\n"
        f"🟡 RETADOR: ${bal_ret:.2f} | {nT} trades | {netT:+.2f}%"
    )

# ══════════════════════════════════════════════════════════════
# ARRANQUE
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    time.sleep(3)

    # ── Banner de terminal ─────────────────────────────────────────────────
    print("💰 BOT MAESTRO V5.0 — Cerebro SIM + C1/C2/C3 — Capital Real Binance Futures")
    print("━" * 51)
    print(f"📊 T1={T1_TARGET}% | BE={BE_TRIGGER}% | SL={STOP_LOSS}% | BE_STOP={BE_STOP}%")
    print(f"🛡️  SL Real={SL_REAL_PCT}% | Trail={TRAILING_DIST}%→{TRAILING2_DIST}%@{TRAILING2_DESDE}% | BE_LOCK={BLOQUEO_SL_MIN}min")
    print(f"🔍 Cerebro SIM + mejoras:")
    print(f"   BTC_suav!=BAJISTA | Slope15m>{MIN_SLOPE_15M}% | Slope1H>{MIN_SLOPE_1H}% | Vol_R>={MIN_VOL_R}x")
    print(f"   F3 ASIA combo | F5 funding | C1 ATR15m>={MIN_ATR_15M}% | C2 time-stop {TIME_STOP_MIN}min")
    print(f"   C3 entrada LIMIT post-only (timeout {LIMIT_TIMEOUT_S}s, NO_FILL descarta)")
    print(f"🎯 Flota: {', '.join(s.split('/')[0] for s in CARTERA)} | 1 posición a la vez")
    print(f"⏱️  Escaneo: 5s fijo")
    print("━" * 51)

    # ── Log inmediato — antes del sync para garantizar que quede registrado ─
    registrar_log(
        f"=== BOT V5.0 INICIADO (cerebro SIM + C1/C2/C3) === "
        f"SL:{STOP_LOSS}% BE:{BE_TRIGGER}% BE_STOP:{BE_STOP}% T1:{T1_TARGET}% "
        f"Trail:{TRAILING_DIST}%->{TRAILING2_DIST}%@{TRAILING2_DESDE}% SL_Real:{SL_REAL_PCT}% BE_LOCK:{BLOQUEO_SL_MIN}min "
        f"C1:ATR15m>={MIN_ATR_15M}% C2:timestop{TIME_STOP_MIN}min C3:limit_maker(to{LIMIT_TIMEOUT_S}s) "
        f"Filtros: BTC_suav Slope1H>{MIN_SLOPE_1H}% VolR>={MIN_VOL_R}x Slope15m>{MIN_SLOPE_15M}% gap200<={MAX_GAP200}%"
    )

    # ── Sincronizar con Binance antes de arrancar ──────────────────────────
    _estado = cargar_estado()
    _estado = sincronizar_con_binance(_estado)

    enviar_telegram(
        f"*Bot V5.0 Online* (cerebro SIM + C1/C2/C3)\n"
        f"SL:{STOP_LOSS}% | BE:{BE_TRIGGER}% | T1:{T1_TARGET}% | BE_STOP:{BE_STOP}%\n"
        f"SL Real:{SL_REAL_PCT}% | BE_LOCK:{BLOQUEO_SL_MIN}min\n"
        f"C1 ATR15m>={MIN_ATR_15M}% | C2 timestop {TIME_STOP_MIN}min | C3 LIMIT maker\n"
        f"Filtros: BTC_suav | Slope1H>{MIN_SLOPE_1H}% | VolR>={MIN_VOL_R}x | gap200<={MAX_GAP200}%"
    )

    # Resumen diario combinado (real+campeón+retador) 1/día — sirve de heartbeat
    ultimo_resumen = time.time()
    while True:
        buscar_oportunidades()
        if time.time() - ultimo_resumen >= 86400:
            try:
                bal = float(exchange.fetch_balance()['total']['USDT'])
            except Exception:
                bal = _balance_cache
            resumen_diario_combinado(bal)
            ultimo_resumen = time.time()
        time.sleep(5)