import time, json, sys, os, requests, signal, atexit
from datetime import datetime, timezone
from especialista_SNIPER import analizar_sniper
from test_conexion import exchange 

# --- RUTAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Carpetas de logs ───────────────────────────────────────────────────────
LOGS_DIR_SIM = os.path.join(BASE_DIR, "logs_simulador")
os.makedirs(LOGS_DIR_SIM, exist_ok=True)

# ── Función para obtener la ruta del scan semanal ─────────────────────────
def _ruta_scan_semana():
    """Retorna la ruta del archivo de scans de la semana ISO actual.
    Ejemplo: logs_simulador/log_scans_2026-W12.txt
    Crea el archivo si no existe (con encabezado de fecha de inicio).
    """
    hoy = datetime.now()
    semana = hoy.isocalendar()          # (año, semana_iso, dia)
    nombre = f"log_scans_{semana[0]}-W{semana[1]:02d}.txt"
    ruta = os.path.join(LOGS_DIR_SIM, nombre)
    if not os.path.exists(ruta):
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"# Scans semana {semana[0]}-W{semana[1]:02d} "
                    f"— inicio {hoy.strftime('%Y-%m-%d %H:%M:%S')}\n")
    return ruta

RUTA_ESTADO_SIM    = os.path.join(BASE_DIR, "estado_sniper_sim.json")

def _guardar_estado_sim(estado):
    """Guarda el estado inmediatamente. Nunca falla silenciosamente."""
    try:
        with open(RUTA_ESTADO_SIM, 'w') as f:
            json.dump(estado, f, indent=4,
                      default=lambda x: bool(x.item()) if hasattr(x, "item") else str(x))
    except Exception as e_save:
        registrar_log_sim(f"ERROR GUARDANDO ESTADO: {e_save}")
ARCHIVO_RESULTADOS = os.path.join(LOGS_DIR_SIM, "simulacion_sniper_resultados.txt")

# --- TELEGRAM ---
TOKEN_TLG   = os.getenv('TELEGRAM_TOKEN', '')
CHAT_ID_TLG = os.getenv('TELEGRAM_CHAT_ID', '')

# --- CONFIGURACIÓN ---
# XAG y PAXG eliminados — backtest mostró <2% de trades con filtros activos
DNA_FLOTA = {
    "SOL/USDT:USDT": {"k_lim": 45, "ma": "SMA"},
    "ETH/USDT:USDT": {"k_lim": 45, "ma": "SMA"},
}
CARTERA = list(DNA_FLOTA.keys())
CAPITAL_INICIAL = 23.06

# --- PARÁMETROS V6.0 (Optimizados por backtest 2 años) ---
T1_TARGET       = 0.25   # Cierre 50% capital (era 0.60)
BE_TRIGGER      = 0.15   # Activa protección BE (era 0.35)
SL_COMISION     = 0.10   # BE_STOP nivel (0.05% entrada + 0.05% salida Binance)
TRAILING_DIST   = 0.20   # Trailing base hasta TRAILING2_DESDE (era 0.60)
TRAILING2_DIST  = 0.10   # Trailing apretado — activo desde TRAILING2_DESDE
TRAILING2_DESDE = 0.40   # Nivel donde aprieta trailing (precio sube media +0.68% post-T1)
STOP_LOSS_BASE  = -0.85  # Stop loss sin BE activado
SUELO_POST_T1   = T1_TARGET   # no puede caer bajo T1 despues de tocarlo

# --- FRECUENCIA ADAPTATIVA ---
SLEEP_LIBRE     = 3.0    # Sin posición: cada 3s — ahorra rate limit API
SLEEP_POSICION  = 0.5    # Con posición: cada 0.5s — reduce slippage en BE y T1

# --- FILTROS DE ENTRADA (optimizados por análisis de 49 trades reales) ---
FILTRO_BTC_BAJISTA  = True   # No entrar si BTC_TREND == BAJISTA
FILTRO_SLOPE_15M    = 0.05   # No entrar si SLOPE_EMA5_15M <= 0.05%
FILTRO_VOL_MIN      = 0.30   # F1: Vol_R mínimo — 33% WR sin volumen
FILTRO_SLOPE_1H_MIN = 0.10   # F2: Slope 1H mínimo — 17% WR por debajo
FILTRO_ASIA_STD_ALC = True   # F3: Bloquear ESTANDAR+ASIATICA+BTC:ALC — 42% WR
BLOQUEO_BE_MIN      = 15     # F4: Minutos bloqueado tras BE_STOP por símbolo

# --- BLOQUEO POST-BE_STOP por símbolo ---
from datetime import timedelta
bloqueo_be_stop = {}  # simbolo -> datetime hasta cuando está bloqueado

# --- VARIABLES DE RESUMEN DIARIO ---
ultimo_resumen_diario = time.time()
trades_hoy = 0
balance_inicio_dia = None

# --- TELEGRAM SIMULADOR ---
def enviar_telegram_sim(mensaje):
    """Envía notificación Telegram con prefijo SIM para diferenciación."""
    if not TOKEN_TLG or not CHAT_ID_TLG:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN_TLG}/sendMessage",
            json={"chat_id": CHAT_ID_TLG, "text": f"[SIM] {mensaje}", "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

def notificar_cierre_sim(motivo="Cierre inesperado"):
    """Notifica cuando el simulador se detiene."""
    try:
        enviar_telegram_sim(f"⚠️ *Simulador Detenido*\n{motivo} | {datetime.now().strftime('%d/%m %H:%M')} UTC")
    except:
        pass

def contar_trade_diario():
    """Incrementa contador de trades del día."""
    global trades_hoy
    trades_hoy += 1

def calcular_pnl_diario(balance_actual):
    """Calcula PnL del día vs balance inicial."""
    global balance_inicio_dia
    if balance_inicio_dia is None:
        return 0.0
    return ((balance_actual - balance_inicio_dia) / balance_inicio_dia) * 100

def resetear_contadores_diarios(balance_actual):
    """Reset contadores cuando cambia el día."""
    global trades_hoy, balance_inicio_dia, ultimo_resumen_diario
    trades_hoy = 0
    balance_inicio_dia = balance_actual
    ultimo_resumen_diario = time.time()

# Configurar handlers de cierre
atexit.register(lambda: notificar_cierre_sim("Cierre inesperado"))
signal.signal(signal.SIGINT, lambda s,f: (notificar_cierre_sim("Ctrl+C"), exit(0)))


# --- SEGUIMIENTO POST-TRADE ---
POST_TRADE_CHECKPOINTS = [0.5, 1, 3, 5, 15, 30, 60, 120]  # en minutos
seguimiento_post = {}

def iniciar_seguimiento(simbolo, motivo_salida, p_cierre):
    seguimiento_post[simbolo] = {
        "motivo":    motivo_salida,
        "p_cierre":  p_cierre,
        "t_cierre":  datetime.now(),
        "pendientes": list(POST_TRADE_CHECKPOINTS),
    }

def chequear_post_trade(simbolo, res):
    if simbolo not in seguimiento_post:
        return
    seg = seguimiento_post[simbolo]
    ahora = datetime.now()
    elapsed_min = (ahora - seg["t_cierre"]).total_seconds() / 60
    pendientes_restantes = []
    for cp in seg["pendientes"]:
        if elapsed_min >= cp:
            p_actual = res.get('p', 0)
            retorno  = ((p_actual - seg["p_cierre"]) / seg["p_cierre"]) * 100 if seg["p_cierre"] > 0 else 0
            fin_str  = " --- FIN SEGUIMIENTO" if cp == POST_TRADE_CHECKPOINTS[-1] else ""
            t_label  = f"{cp}min" if cp < 60 else f"{int(cp//60)}h"
            registrar_log_sim(
                f"POST_TRADE [{seg['motivo']}] {simbolo} | "
                f"t:{t_label} | "
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

def registrar_log_sim(mensaje):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(_ruta_scan_semana(), "a", encoding="utf-8") as f:
            f.write(f"[{ahora}] {mensaje}\n")
    except: pass


def anotar_evento(mensaje):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Comentado para terminal limpia en VPS - eventos se guardan en simulacion_sniper_resultados.txt
    # print(f"\n📢 {mensaje}")
    try:
        with open(ARCHIVO_RESULTADOS, "a", encoding="utf-8") as f:
            f.write(f"[{ahora}] {mensaje}\n")
        # Contar trade si es una entrada
        if mensaje.startswith("ENTRADA ["):
            contar_trade_diario()
    except: pass


def sincronizar_simulador(estado):
    """Al arrancar, cierra posiciones que quedaron abiertas
    mientras el bot estaba apagado."""
    posiciones_abiertas = list(estado.get("posiciones", {}).keys())
    if not posiciones_abiertas:
        return estado

    registrar_log_sim(f"SYNC: {len(posiciones_abiertas)} posición(es) abierta(s) al reiniciar — cerrando al precio actual")

    for simbolo in posiciones_abiertas:
        pos = estado["posiciones"][simbolo]
        try:
            ticker = exchange.fetch_ticker(simbolo)
            precio_actual = ticker['last']
            p_ent = pos['precio_entrada']
            ganancia = ((precio_actual - p_ent) / p_ent) * 100
            dur_h = round((datetime.now() - datetime.strptime(
                pos.get('f_entrada', datetime.now().strftime("%Y-%m-%d %H:%M")),
                "%Y-%m-%d %H:%M")).total_seconds() / 3600, 1)

            estado["balance_acumulado"] *= (1 + (ganancia / 100))
            anotar_evento(
                f"CIERRE_REINICIO {simbolo}: "
                f"PnL:{ganancia:+.2f}% | Bot apagado {dur_h}h | "
                f"P_entrada:{p_ent:.2f} | P_cierre:{precio_actual:.2f} | "
                f"BALANCE:${estado['balance_acumulado']:.2f}"
            )
            del estado["posiciones"][simbolo]
            registrar_log_sim(f"SYNC: {simbolo} cerrado | PnL:{ganancia:+.2f}% | dur:{dur_h}h")
        except Exception as e:
            registrar_log_sim(f"ERROR SYNC {simbolo}: {e}")

    _guardar_estado_sim(estado)
    return estado


def simular_sniper():
    try:
        if not os.path.exists(RUTA_ESTADO_SIM):
            with open(RUTA_ESTADO_SIM, "w") as f:
                json.dump({"posiciones": {}, "balance_acumulado": CAPITAL_INICIAL}, f, indent=4)

        with open(RUTA_ESTADO_SIM, 'r') as f:
            estado = json.load(f)

        hay_posicion = len(estado.get("posiciones", {})) > 0

        # ── Display terminal con PnL en tiempo real ──────────────────────
        if hay_posicion and estado.get("posiciones"):
            partes = []
            for sym, pos in estado["posiciones"].items():
                p_ent    = pos.get('precio_entrada', 0)
                p_actual = pos.get('precio_actual', p_ent)   # último precio conocido
                pnl_now  = ((p_actual - p_ent) / p_ent * 100) if p_ent else 0
                fase     = "T1+" if pos.get('t1_hecho') else ("BE+" if pos.get('be_activado') else "")
                signo    = "+" if pnl_now >= 0 else ""
                partes.append(f"{sym.split('/')[0]} {fase}{signo}{pnl_now:.2f}%")
            estado_display = "⚡ OPEN " + " | ".join(partes)
        else:
            estado_display = "Escaneando..."
        # Solo display en vivo si hay TTY. Bajo systemd no hay TTY: evita el
        # spam de '\r' que infló el journal del sistema a giga.
        if sys.stdout.isatty():
            sys.stdout.write(
                f"\r🕵️ [{datetime.now().strftime('%H:%M:%S')}] "
                f"Bal SIM ${estado['balance_acumulado']:.2f} | "
                f"{estado_display} "
            )
            sys.stdout.flush()

        for simbolo in CARTERA:
            adn = DNA_FLOTA[simbolo]
            res = analizar_sniper(simbolo, k_lim=adn['k_lim'], ma_tipo=adn['ma'])
            if res['error'] or res.get('p') is None:
                continue

            # ── Preparar variables para log ───────────────────────────────
            ema7_val  = res.get('ema7', 0)
            ema5_val  = res.get('ema5', 0)
            ema5_prev = res.get('ema5_prev', 0)
            ema7_prev = res.get('ema7_prev', 0)
            gap_ema7  = ((res['p'] - ema7_val) / ema7_val * 100) if ema7_val > 0 else 0
            g_emas    = ((ema5_val - ema7_val) / ema7_val * 100) if ema7_val > 0 else 0
            btc_trend = res.get('btc_trend', '-')
            slope_15m    = res.get('slope_ema5_15m', 0)
            k_15m        = res.get('k_15m', 50)
            d_15m        = res.get('d_15m', 50)
            k_d_diff_15m = res.get('k_d_diff_15m', 0)
            k_mayor_d_15m= res.get('k_mayor_d_15m', False)
            rsi_15m      = res.get('rsi_15m', 50)
            atr_1h       = res.get('atr_1h', 0)

            cruce = ""
            if ema5_prev > 0 and ema7_prev > 0:
                fue_alcista = ema5_prev > ema7_prev
                es_alcista  = ema5_val  > ema7_val
                if not fue_alcista and es_alcista:
                    cruce = "CRUCE_ALCISTA"
                elif fue_alcista and not es_alcista:
                    cruce = "CRUCE_BAJISTA"

            ahora_utc = datetime.now(timezone.utc)
            hora_utc  = ahora_utc.hour
            if 0 <= hora_utc < 8:    sesion = "ASIATICA"
            elif 8 <= hora_utc < 16: sesion = "EUROPEA"
            else:                    sesion = "AMERICANA"

            if simbolo in estado["posiciones"]:
                p_ent_log   = estado["posiciones"][simbolo].get('precio_entrada')
                pnl_actual  = ((res['p'] - p_ent_log) / p_ent_log * 100) if p_ent_log else 0
                _id_log     = estado["posiciones"][simbolo].get('id_trade', '?')
                estado_str  = f"EN_POSICION({pnl_actual:+.2f}%) ID:{_id_log}"
            else:
                estado_str = "LIBRE"

            # Evaluar filtros para mostrar en log
            pasa_btc  = not (FILTRO_BTC_BAJISTA and btc_trend == 'BAJISTA')
            pasa_15m  = slope_15m > FILTRO_SLOPE_15M
            bloqueos  = []
            if not pasa_btc: bloqueos.append("BTC_BAJISTA")
            if not pasa_15m: bloqueos.append(f"SLOPE_15M<={FILTRO_SLOPE_15M}%")
            filtros_str = " | ".join(bloqueos) if bloqueos else "OK"

            chequear_post_trade(simbolo, res)
            registrar_log_sim(
                f"SCAN {simbolo} | HORA:{ahora_utc.strftime('%H:%M')}UTC | SESION:{sesion} | "
                f"P:{res['p']:.4f} | H_1H:{res.get('h_1h',0):.4f} | L_1H:{res.get('l_1h',0):.4f} | H_15M:{res.get('h_15m',0):.4f} | L_15M:{res.get('l_15m',0):.4f} | Slope1h:{res['pendiente_7']:.3f}% | "
                f"Vol_R:{res.get('vol_r', 1.0):.2f}x | K:{res.get('k', 0):.1f} | D:{res.get('d', 0):.1f} | "
                f"EMA5:{ema5_val:.2f} | EMA7:{ema7_val:.2f} | "
                f"GapEMA7_1h:{gap_ema7:+.4f}% | SobreEMA7:{res.get('precio_sobre_ema7', False)} | "
                f"gEMAS:{g_emas:+.3f}% | "
                f"CRUCE_1H:{res.get('cruce_1h', '-') if res.get('cruce_1h') else '-'} | "
                f"EMA5_15M:{res.get('ema5_15m', 0):.4f} | EMA7_15M:{res.get('ema7_15m', 0):.4f} | "
                f"SLOPE_EMA5_15M:{slope_15m:+.4f}% | "
                f"CRUCE_15M:{res.get('cruce_15m', '-') if res.get('cruce_15m') else '-'} | "
                f"VELAS_CRUCE_15M:{res.get('velas_desde_cruce', -1)} | "
                f"BTC:{res.get('btc_precio', 0):.0f} | BTC_SLOPE:{res.get('btc_slope', 0):+.4f}% | "
                f"BTC_TREND:{btc_trend} | "
                f"MA50:{res.get('ma50', 0):.2f} | Gap200:{res.get('gap200', 0):+.2f}% | "
                f"BLOCK:{res['block'] if res['block'] else 'OK'} | "
                f"FILTROS:{filtros_str} | ESTADO:{estado_str} | "
                f"ATR_1H:{res.get('atr_1h',0):.4f}% | ATR_15M:{res.get('atr_15m',0):.4f}% | "
                f"Funding:{res.get('funding_rate',0):.5f} | FundAlto:{res.get('funding_alto',False)} | "
                f"GapVWAP:{res.get('gap_vwap',0):+.4f}% | "
                f"K15m:{res.get('k_15m',50):.1f} | D15m:{res.get('d_15m',50):.1f} | "
                f"Cuerpo1H:{res.get('cuerpo_1h',0):.3f} | VelaAlc:{res.get('vela_alcista_1h',False)} | "
                f"OBV:{res.get('obv_slope',0):+.4f}%"
            )

            # ── GESTIÓN DE POSICIÓN ABIERTA ───────────────────────────────
            if simbolo in estado["posiciones"]:
                pos      = estado["posiciones"][simbolo]
                p_ent    = pos.get('precio_entrada')
                ganancia = ((res['p'] - p_ent) / p_ent) * 100

                # Actualizar precio actual, máximo y mínimo
                pos['precio_actual'] = res['p']
                if res['p'] > pos.get('precio_max', 0):
                    pos['precio_max'] = res['p']
                if res['p'] < pos.get('precio_min', 99999):
                    pos['precio_min'] = res['p']

                # 1. Activar BE
                if ganancia >= BE_TRIGGER and not pos.get('be_activado'):
                    pos['be_activado'] = True
                    anotar_evento(
                        f"🛡️ BE ACTIVADO {simbolo}: "
                        f"P:{res['p']:.2f} | +{BE_TRIGGER:.2f}% alcanzado | "
                        f"SL sube de {STOP_LOSS_BASE:.2f}% a +{SL_COMISION:.2f}%"
                    )

                # 2. T1 alcanzado — cobro 50% capital
                if ganancia >= T1_TARGET and not pos.get('t1_hecho'):
                    pos['t1_hecho']      = True
                    pos['trailing_stop'] = max(SUELO_POST_T1, ganancia - TRAILING_DIST)
                    pos['precio_t1']     = res['p']
                    pos['g_en_t1']       = round(ganancia, 4)
                    pos['t_t1']          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    estado["balance_acumulado"] *= (1 + (T1_TARGET / 100 * 0.5))
                    anotar_evento(
                        f"T1 ALCANZADO {simbolo}: "
                        f"P_t1:{res['p']:.2f} | +{T1_TARGET:.2f}% sobre 50% capital | "
                        f"Trail activo: {TRAILING_DIST:.2f}% → {TRAILING2_DIST:.2f}% desde +{TRAILING2_DESDE:.2f}% | "
                        f"SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                        f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | "
                        f"Cruce15m:{res.get('cruce_15m','-') or '-'} | "
                        f"BTC:{res.get('btc_trend','?')} | "
                        f"BALANCE:${estado['balance_acumulado']:.2f}"
                    )
                    iniciar_seguimiento(simbolo + "_T1", "POST_T1", res['p'])

                # 3. Trailing dinámico después de T1
                if pos.get('t1_hecho'):
                    # Aprieta trailing al llegar a TRAILING2_DESDE
                    if ganancia >= TRAILING2_DESDE:
                        nuevo_trailing = ganancia - TRAILING2_DIST
                    else:
                        nuevo_trailing = ganancia - TRAILING_DIST

                    # El trailing nunca baja
                    if nuevo_trailing > pos.get('trailing_stop', -99):
                        pos['trailing_stop'] = nuevo_trailing

                    suelo = max(SUELO_POST_T1, pos['trailing_stop'])

                    if ganancia <= suelo:
                        estado["balance_acumulado"] *= (1 + (ganancia / 100 * 0.5))
                        p_max        = pos.get('precio_max', p_ent)
                        ganancia_max = ((p_max - p_ent) / p_ent) * 100
                        dur_h = round((datetime.now() - datetime.strptime(pos.get('f_entrada', datetime.now().strftime("%Y-%m-%d %H:%M")), "%Y-%m-%d %H:%M")).total_seconds() / 3600, 1)
                        subida_post_t1 = round(ganancia - pos.get('g_en_t1', T1_TARGET), 4) if pos.get('precio_t1') else 0
                        _id_cierre = pos.get('id_trade', '?')
                        registrar_log_sim(
                            f"<<< CIERRE_TRAILING {simbolo} | ID:{_id_cierre} | "
                            f"PnL_trail:{ganancia:+.2f}% | BAL:${estado['balance_acumulado']:.2f}"
                        )
                        registrar_log_sim(f"{'='*60}")
                        anotar_evento(
                            f"CIERRE_TRAILING {simbolo}: "
                            f"T1:+{T1_TARGET:.2f}%(50%) + Trail:{ganancia:+.2f}%(50%) | "
                            f"SubidaPostT1:{subida_post_t1:+.4f}% | "
                            f"P_entrada:{p_ent:.2f} | P_t1:{pos.get('precio_t1', p_ent):.2f} | "
                            f"P_salida:{res['p']:.2f} | P_max:{p_max:.2f} (max:{ganancia_max:+.2f}%) | "
                            f"P_min:{pos.get('precio_min', p_ent):.2f} (min:{((pos.get('precio_min', p_ent)-p_ent)/p_ent*100):+.2f}%) | "
                            f"Trail_stop:{pos.get('trailing_stop',-99):+.3f}% | Dur:{dur_h}h | "
                            f"Sesion:{pos.get('sesion','?')} | BTC:{pos.get('btc_trend','?')} | "
                            f"Motivo:{pos.get('motivo_entrada','?')} | "
                            f"GapEMA7:{pos.get('gap_ema7',0):+.4f}% | "
                            f"Cruce15m:{pos.get('cruce_15m','-')} | VelasCruce15m:{pos.get('velas_cruce_15m',-1)} | "
                            f"SobreEMA7:{pos.get('precio_sobre_ema7',False)} | "
                            f"ATR_1H_ent:{pos.get('atr_1h_entrada',0):.4f}% | ATR_15M_ent:{pos.get('atr_15m_entrada',0):.4f}% | ATR_5M_ent:{pos.get('atr_5m_entrada',0):.4f}% | "
                            f"ATR_1H_now:{res.get('atr_1h',0):.4f}% | ATR_15M_now:{res.get('atr_15m',0):.4f}% | "
                            f"BALANCE:${estado['balance_acumulado']:.2f}"
                        )
                        iniciar_seguimiento(simbolo, "CIERRE_TRAILING", res['p'])
                        del estado["posiciones"][simbolo]
                        _guardar_estado_sim(estado)  # guardado inmediato — evita posición zombie

                # 4. Salida antes de T1
                else:
                    sl_activo  = SL_COMISION if pos.get('be_activado') else STOP_LOSS_BASE
                    corte_ema7 = res['p'] < ema7_val and not pos.get('be_activado')
                    corte_sl   = ganancia <= sl_activo

                    if corte_ema7 or corte_sl:
                        motivo_salida = (
                            "BE_STOP"    if (corte_sl and pos.get('be_activado')) else
                            "STOP_LOSS"  if corte_sl else
                            "CORTE_EMA7"
                        )
                        estado["balance_acumulado"] *= (1 + (ganancia / 100))
                        p_max        = pos.get('precio_max', p_ent)
                        ganancia_max = ((p_max - p_ent) / p_ent) * 100
                        dur_h2 = round((datetime.now() - datetime.strptime(pos.get('f_entrada', datetime.now().strftime("%Y-%m-%d %H:%M")), "%Y-%m-%d %H:%M")).total_seconds() / 3600, 1)
                        _id_salida = pos.get('id_trade', '?')
                        registrar_log_sim(
                            f"<<< SALIDA [{motivo_salida}] {simbolo} | ID:{_id_salida} | "
                            f"PnL:{ganancia:+.2f}% | BAL:${estado['balance_acumulado']:.2f}"
                        )
                        registrar_log_sim(f"{'='*60}")
                        anotar_evento(
                            f"SALIDA [{motivo_salida}] {simbolo}: "
                            f"PnL:{ganancia:+.2f}% | P_entrada:{p_ent:.2f} | "
                            f"P_salida:{res['p']:.2f} | P_max:{p_max:.2f} (max:{ganancia_max:+.2f}%) | "
                            f"P_min:{pos.get('precio_min', p_ent):.2f} (min:{((pos.get('precio_min', p_ent)-p_ent)/p_ent*100):+.2f}%) | "
                            f"Dur:{dur_h2}h | Sesion:{pos.get('sesion','?')} | BTC:{pos.get('btc_trend','?')} | "
                            f"Motivo:{pos.get('motivo_entrada','?')} | "
                            f"GapEMA7:{pos.get('gap_ema7',0):+.4f}% | "
                            f"Cruce15m:{pos.get('cruce_15m','-')} | VelasCruce15m:{pos.get('velas_cruce_15m',-1)} | "
                            f"SobreEMA7:{pos.get('precio_sobre_ema7',False)} | "
                            f"ATR_1H_ent:{pos.get('atr_1h_entrada',0):.4f}% | ATR_15M_ent:{pos.get('atr_15m_entrada',0):.4f}% | ATR_5M_ent:{pos.get('atr_5m_entrada',0):.4f}% | "
                            f"ATR_1H_now:{res.get('atr_1h',0):.4f}% | ATR_15M_now:{res.get('atr_15m',0):.4f}% | "
                            f"BALANCE:${estado['balance_acumulado']:.2f}"
                        )
                        # Registrar bloqueo post-BE_STOP
                        if motivo_salida == 'BE_STOP':
                            bloqueo_be_stop[simbolo] = datetime.now() + timedelta(minutes=BLOQUEO_BE_MIN)
                            registrar_log_sim(
                                f"BE_LOCK activado {simbolo} | "
                                f"Bloqueado {BLOQUEO_BE_MIN}min hasta {bloqueo_be_stop[simbolo].strftime('%H:%M:%S')}"
                            )
                        iniciar_seguimiento(simbolo, motivo_salida, res['p'])
                        del estado["posiciones"][simbolo]
                        _guardar_estado_sim(estado)  # guardado inmediato — evita posición zombie

            # ── LÓGICA DE ENTRADA ─────────────────────────────────────────
            else:
                pendiente_alta = res['pendiente_7'] > 0.10
                vol_confirmado = res.get('vol_r', 0) > 1.3
                gap_ok         = res.get('gap200', 0) <= 4.0
                tecnica_limpia = res['block'] == ""

                motivo_entrada = ""
                if pendiente_alta and vol_confirmado:
                    motivo_entrada = "SNIPER"
                elif tecnica_limpia and res['pendiente_7'] > FILTRO_SLOPE_1H_MIN:
                    motivo_entrada = "ESTANDAR"

                # ── FILTROS CONFIRMADOS POR DATOS REALES ─────────────────
                # F1: Volumen mínimo
                pasa_vol     = res.get('vol_r', 0) >= FILTRO_VOL_MIN
                # F_K15M: K(15m) debe estar subiendo — más ágil que K(1h)
                pasa_k15m    = k_mayor_d_15m or k_d_diff_15m > -5
                # F2: Slope 1H mínimo (ya aplicado en motivo_entrada)
                # F3: Bloquear ESTANDAR+ASIATICA+BTC:ALC (42% WR histórico)
                pasa_combo   = not (
                    motivo_entrada == 'ESTANDAR' and
                    sesion == 'ASIATICA' and
                    btc_trend == 'ALCISTA' and
                    FILTRO_ASIA_STD_ALC
                )
                # F4: Bloqueo post-BE_STOP
                ahora_dt     = datetime.now()
                pasa_be_lock = simbolo not in bloqueo_be_stop or ahora_dt >= bloqueo_be_stop[simbolo]
                # F5: Funding rate — ESTANDAR bloqueado si mercado saturado de longs
                # SNIPER puede entrar igual (señal más fuerte, vale el riesgo)
                funding_alto = res.get('funding_alto', False)
                pasa_funding = not (funding_alto and motivo_entrada == 'ESTANDAR')

                # Log de señales bloqueadas por nuevos filtros
                if motivo_entrada and gap_ok and pasa_btc and pasa_15m:
                    bloqueadores_nuevos = []
                    if not pasa_vol:     bloqueadores_nuevos.append(f"VOL_R:{res.get('vol_r',0):.2f}x<{FILTRO_VOL_MIN}x")
                    if not pasa_combo:   bloqueadores_nuevos.append("ESTANDAR+ASIA+ALC")
                    if not pasa_be_lock: bloqueadores_nuevos.append(f"BE_LOCK:{simbolo}")
                    if not pasa_funding: bloqueadores_nuevos.append(f"FUNDING_ALTO:{res.get('funding_rate',0):.4f}")
                    if bloqueadores_nuevos:
                        registrar_log_sim(
                            f"SEÑAL_BLOQUEADA [{motivo_entrada}] {simbolo} | "
                            f"P:{res['p']:.4f} | Vol_R:{res.get('vol_r',0):.2f}x | "
                            f"GapEMA7:{res.get('gap_ema7',0):+.4f}% | "
                            f"VelasCruce:{res.get('velas_desde_cruce',-1)} | "
                            f"BTC:{btc_trend} | SESION:{sesion} | "
                            f"BLOQUEADO_POR:{' + '.join(bloqueadores_nuevos)}"
                        )

                if motivo_entrada and gap_ok and pasa_btc and pasa_15m and pasa_vol and pasa_combo and pasa_be_lock and pasa_k15m and pasa_funding:
                    _id_trade = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{simbolo.split('/')[0]}"
                    estado["posiciones"][simbolo] = {
                        "id_trade":       _id_trade,
                        "precio_entrada": res['p'],
                        "precio_max":     res['p'],
                        "precio_min":     res['p'],
                        "motivo_entrada": motivo_entrada,
                        "t1_hecho":       False,
                        "be_activado":    False,
                        "trailing_stop":  -99,
                        # Contexto de entrada para análisis posterior
                        "btc_trend":      btc_trend,
                        "slope_15m":      slope_15m,
                        "cruce_1h":       cruce if cruce else "-",
                        "sesion":         sesion,
                        "gap_ema7":       round(res.get('gap_ema7', 0), 4),
                        "cruce_15m":      res.get('cruce_15m', '-'),
                        "velas_cruce_15m": res.get('velas_desde_cruce', -1),
                        "precio_sobre_ema7": res.get('precio_sobre_ema7', False),
                        "slope_entrada":  round(res.get('pendiente_7', 0), 4),
                        "vol_r_entrada":  round(res.get('vol_r', 0), 2),
                        "gap200_entrada": round(res.get('gap200', 0), 2),
                        "f_entrada":      datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "h_1h_entrada":   round(res.get("h_1h", 0), 4),
                        "l_1h_entrada":   round(res.get("l_1h", 0), 4),
                        "h_15m_entrada":  round(res.get("h_15m", 0), 4),
                        "l_15m_entrada":  round(res.get("l_15m", 0), 4),
                        # ATR al momento de entrada — para calcular SL/trailing dinámico
                        "atr_1h_entrada":  round(res.get("atr_1h", 0), 4),
                        "atr_15m_entrada": round(res.get("atr_15m", 0), 4),
                        "atr_5m_entrada":  round(res.get("atr_5m", 0), 4),
                    }
                    registrar_log_sim(
                        f"{'='*60}"
                    )
                    registrar_log_sim(
                        f">>> ENTRADA [{motivo_entrada}] {simbolo} | ID:{_id_trade} | "
                        f"P:{res['p']:.4f} | {ahora_utc.strftime('%H:%M')}UTC | BAL:${estado['balance_acumulado']:.2f}"
                    )
                    anotar_evento(
                        f"ENTRADA [{motivo_entrada}] {simbolo}: "
                        f"P:{res['p']:.4f} | H_1H:{res.get('h_1h',0):.4f} | L_1H:{res.get('l_1h',0):.4f} | H_15M:{res.get('h_15m',0):.4f} | L_15M:{res.get('l_15m',0):.4f} | Slope:{res['pendiente_7']:.4f}% | "
                        f"Vol_R:{res.get('vol_r', 0):.2f}x | K:{res.get('k', 0):.1f} | "
                        f"GapEMA7:{res.get('gap_ema7', 0):+.4f}% | SobreEMA7:{res.get('precio_sobre_ema7',False)} | "
                        f"Cruce15m:{res.get('cruce_15m','-')} | VelasCruce15m:{res.get('velas_desde_cruce', -1)} | "
                        f"Slope_15m:{slope_15m:+.4f}% | BTC:{btc_trend} | "
                        f"CRUCE_1H:{cruce if cruce else '-'} | "
                        f"Gap200:{res.get('gap200', 0):+.2f}% | SESION:{sesion} | "
                        f"ATR_1H:{res.get('atr_1h',0):.4f}% | ATR_15M:{res.get('atr_15m',0):.4f}% | ATR_5M:{res.get('atr_5m',0):.4f}% | "
                        f"Funding:{res.get('funding_rate',0):.5f} | GapVWAP:{res.get('gap_vwap',0):+.4f}% | "
                        f"K15m:{res.get('k_15m',50):.1f} | D15m:{res.get('d_15m',50):.1f} | "
                        f"Cuerpo1H:{res.get('cuerpo_1h',0):.3f} | VelaAlc:{res.get('vela_alcista_1h',False)} | "
                        f"OBV_slope:{res.get('obv_slope',0):+.4f}%"
                    )

        with open(RUTA_ESTADO_SIM, 'w') as f:
            json.dump(estado, f, indent=4, default=lambda x: bool(x.item()) if hasattr(x, "item") else str(x))

        return len(estado.get("posiciones", {}))

    except Exception as e:
        registrar_log_sim(f"ERROR CRÍTICO: {e}")
        return 0


if __name__ == "__main__":
    print(f"\n🚀 LABORATORIO SNIPER V7.5 — OHLC completo + K(15m) + ATR + Multi-TF")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📊 T1={T1_TARGET}% | BE={BE_TRIGGER}% | SL={STOP_LOSS_BASE}%")
    print(f"📈 Trail={TRAILING_DIST}% → {TRAILING2_DIST}% desde +{TRAILING2_DESDE}%")
    print(f"🔍 Filtros activos:")
    print(f"   BTC!=BAJISTA | Slope15m>{FILTRO_SLOPE_15M}% | Slope1H>{FILTRO_SLOPE_1H_MIN}%")
    print(f"   Vol_R>={FILTRO_VOL_MIN}x | No ESTANDAR+ASIA+ALC | BE_LOCK={BLOQUEO_BE_MIN}min")
    print(f"🎯 Flota: {', '.join([s.split('/')[0] for s in CARTERA])}")
    print(f"⏱️  Escaneo: {SLEEP_LIBRE}s libre | {SLEEP_POSICION}s en posición")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # ── SINCRONIZACIÓN INICIAL (solo al arrancar) ──────────────────────────
    print("🔧 Sincronizando estado inicial...")
    if not os.path.exists(RUTA_ESTADO_SIM):
        with open(RUTA_ESTADO_SIM, "w") as f:
            json.dump({"posiciones": {}, "balance_acumulado": CAPITAL_INICIAL}, f, indent=4)

    with open(RUTA_ESTADO_SIM, 'r') as f:
        estado_inicial = json.load(f)

    # SINCRONIZAR SOLO UNA VEZ AL INICIO
    estado_inicial = sincronizar_simulador(estado_inicial)
    _guardar_estado_sim(estado_inicial)
    print("✅ Sincronización completa\n")

    # ── NOTIFICACIÓN DE ARRANQUE ───────────────────────────────────────────────
    balance_actual = estado_inicial.get("balance_acumulado", CAPITAL_INICIAL)
    resetear_contadores_diarios(balance_actual)
    enviar_telegram_sim(
        f"*Simulador V7.5 Online*\n"
        f"Balance: ${balance_actual:.2f}\n"
        f"T1:{T1_TARGET}% | BE:{BE_TRIGGER}% | SL:{STOP_LOSS_BASE}%\n"
        f"Filtros activos | {datetime.now().strftime('%d/%m %H:%M')} UTC"
    )

    while True:
        posiciones_abiertas = simular_sniper()

        # ── RESUMEN DIARIO (cada 24 horas) ─────────────────────────────────────
        if time.time() - ultimo_resumen_diario >= 86400:  # 24 horas
            try:
                with open(RUTA_ESTADO_SIM, 'r') as f:
                    estado_actual = json.load(f)
                balance_actual = estado_actual.get("balance_acumulado", CAPITAL_INICIAL)
                pnl_diario = calcular_pnl_diario(balance_actual)

                enviar_telegram_sim(
                    f"📊 *Resumen Diario Simulador*\n"
                    f"Balance: ${balance_actual:.2f}\n"
                    f"Trades hoy: {trades_hoy}\n"
                    f"PnL día: {pnl_diario:+.2f}%\n"
                    f"{datetime.now().strftime('%d/%m/%Y')}"
                )
                resetear_contadores_diarios(balance_actual)
            except:
                pass

        time.sleep(SLEEP_POSICION if posiciones_abiertas > 0 else SLEEP_LIBRE)