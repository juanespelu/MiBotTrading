"""
paper_engine.py — Motor de paper-trading parametrizado (W24).

Una sola posición a la vez. PnL NETO de comisión maker. Registro completo por
trade. Usa especialista_v3 (btc_trend_suav, igual que el bot real) y el filtro
de entrada que se le inyecta (config['evaluar']), de modo que el CAMPEÓN corre
el MISMO cerebro de entrada que el bot real (analisis/ANALISIS_ESTRATEGIA.md).

Lo usan dos lanzadores:
  - bot_SNIPER_CAMPEON.py  → mismos params que el real (control del Δ ejecución)
  - bot_SNIPER_RETADOR.py  → gestión más suelta (montar tendencia)

NO coloca órdenes reales. NO toca el bot real ni sus logs.
"""
import time, json, os
from datetime import datetime, timezone, timedelta
from especialista_v3 import analizar_sniper

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

DNA_FLOTA = {
    "SOL/USDT:USDT": {"k_lim": 45, "ma": "SMA"},
    "ETH/USDT:USDT": {"k_lim": 45, "ma": "SMA"},
}
CARTERA = list(DNA_FLOTA.keys())
CAPITAL_INICIAL = 25.0
SLEEP_LIBRE    = 3.0
SLEEP_POSICION = 0.5


class PaperBot:
    def __init__(self, cfg):
        self.cfg   = cfg
        self.name  = cfg["name"]
        base       = os.path.dirname(os.path.abspath(__file__))
        self.logs_dir = os.path.join(base, cfg["logs_dir"])
        os.makedirs(self.logs_dir, exist_ok=True)
        self.estado_path   = os.path.join(base, cfg["state_file"])
        self.trades_path   = os.path.join(self.logs_dir, cfg["trades_file"])  # nunca rota
        self.bloqueo       = {}   # BE_LOCK: simbolo -> datetime desbloqueo

    # ── logs ────────────────────────────────────────────────────────────────
    def _ruta_scan(self):
        s = utcnow().isocalendar()
        ruta = os.path.join(self.logs_dir, f"log_scans_{s[0]}-W{s[1]:02d}.txt")
        if not os.path.exists(ruta):
            with open(ruta, "a", encoding="utf-8") as f:
                f.write(f"# {self.name} scans {s[0]}-W{s[1]:02d}\n")
        return ruta

    def log_scan(self, msg):
        try:
            with open(self._ruta_scan(), "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
        except Exception:
            pass

    def log_trade(self, msg):
        try:
            with open(self.trades_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
                f.flush(); os.fsync(f.fileno())
        except Exception:
            pass

    # ── estado ──────────────────────────────────────────────────────────────
    def cargar(self):
        if not os.path.exists(self.estado_path):
            self.guardar({"posiciones": {}, "balance": CAPITAL_INICIAL})
        with open(self.estado_path) as f:
            return json.load(f)

    def guardar(self, e):
        with open(self.estado_path, "w") as f:
            json.dump(e, f, indent=2,
                      default=lambda x: bool(x.item()) if hasattr(x, "item") else str(x))

    # ── cierre de trade: PnL NETO + registro completo ─────────────────────────
    def cerrar(self, estado, simbolo, pos, res, motivo_salida, ganancia, ahora):
        p = self.cfg
        if motivo_salida == "CIERRE_TRAILING":
            gross = 0.5 * p["T1_TARGET"] + 0.5 * ganancia          # convención del análisis
        else:
            gross = ganancia                                       # salida completa sobre 100%
        net = gross - p["COMM_RT"]                                 # comisión maker round-trip
        estado["balance"] *= (1 + net / 100)

        p_ent = pos["precio_entrada"]
        try:
            t_ent = datetime.strptime(pos["t_entrada_iso"], "%Y-%m-%d %H:%M:%S")
            dur_min = round((ahora - t_ent).total_seconds() / 60, 1)
        except Exception:
            dur_min = -1
        # Registro COMPLETO por trade (entrada + salida + contexto + comisión + régimen)
        self.log_trade(
            f"TRADE {self.name} | {motivo_salida} | {simbolo} | "
            f"motivo_ent:{pos.get('motivo_entrada','?')} | "
            f"gross:{gross:+.4f}% | comision:{p['COMM_RT']:.3f}% | net:{net:+.4f}% | "
            f"P_ent:{p_ent:.4f} | P_sal:{res['p']:.4f} | "
            f"max:{pos.get('g_max',0):+.3f}% | min:{pos.get('g_min',0):+.3f}% | "
            f"dur_min:{dur_min} | sesion:{pos.get('sesion','?')} | "
            f"t1:{pos.get('t1_hecho',False)} | be:{pos.get('be_activado',False)} | "
            f"slope1h:{pos.get('slope_entrada',0):+.3f}% | vol_r:{pos.get('vol_r_entrada',0):.2f} | "
            f"atr15m:{pos.get('atr_15m_entrada',0):.3f}% | k:{pos.get('k_entrada',0):.1f} | "
            f"btc_suav:{pos.get('btc_trend_entrada','?')} | btc_score_ent:{pos.get('btc_score_ent',0)} | "
            f"btc_ret1h_now:{res.get('btc_retorno_1h',0):+.3f}% | "
            f"bal:{estado['balance']:.4f}"
        )
        if motivo_salida in ("STOP_LOSS", "RETROCESO_BE"):
            self.bloqueo[simbolo] = ahora + timedelta(minutes=p["BLOQUEO_MIN"])
        del estado["posiciones"][simbolo]
        self.guardar(estado)

    # ── un ciclo de scaneo ────────────────────────────────────────────────────
    def ciclo(self):
        p = self.cfg
        estado = self.cargar()
        ocupado = len(estado.get("posiciones", {})) > 0
        for simbolo in CARTERA:
            adn = DNA_FLOTA[simbolo]
            res = analizar_sniper(simbolo, k_lim=adn["k_lim"], ma_tipo=adn["ma"])
            if res.get("error") or not res.get("p"):
                continue
            ahora = datetime.now()
            h = utcnow().hour
            sesion = "ASIATICA" if h < 8 else ("EUROPEA" if h < 16 else "AMERICANA")

            # ── EN POSICIÓN ──────────────────────────────────────────────────
            if simbolo in estado["posiciones"]:
                pos = estado["posiciones"][simbolo]
                p_ent = pos["precio_entrada"]
                ganancia = ((res["p"] - p_ent) / p_ent) * 100
                pos["precio_actual"] = res["p"]
                if ganancia > pos.get("g_max", -999): pos["g_max"] = round(ganancia, 4)
                if ganancia < pos.get("g_min", 999):  pos["g_min"] = round(ganancia, 4)

                if pos.get("t1_hecho"):
                    dist = p["TRAILING2_DIST"] if ganancia >= p["TRAILING2_DESDE"] else p["TRAILING_DIST"]
                    nuevo = max(p["SUELO_POST_T1"], ganancia - dist)
                    if nuevo > pos.get("trailing_stop", -99): pos["trailing_stop"] = nuevo
                    if ganancia <= pos["trailing_stop"]:
                        self.cerrar(estado, simbolo, pos, res, "CIERRE_TRAILING", ganancia, ahora)
                        continue
                elif ganancia >= p["T1_TARGET"] and not pos.get("t1_hecho"):
                    pos["t1_hecho"] = True
                    pos["trailing_stop"] = max(p["SUELO_POST_T1"], ganancia - p["TRAILING_DIST"])
                    pos["g_en_t1"] = round(ganancia, 4)
                elif ganancia >= p["BE_TRIGGER"] and not pos.get("be_activado"):
                    pos["be_activado"] = True

                if simbolo in estado["posiciones"] and not pos.get("t1_hecho"):
                    ema7v = res.get("ema7", 0)
                    motivo_salida = None
                    if pos.get("be_activado") and ganancia <= p["BE_STOP"]:
                        motivo_salida = "RETROCESO_BE"
                    elif not pos.get("be_activado") and ganancia <= p["STOP_LOSS"]:
                        motivo_salida = "STOP_LOSS"
                    elif p["USE_CORTE_EMA7"] and ema7v > 0 and res["p"] < ema7v and not pos.get("be_activado"):
                        motivo_salida = "CORTE_EMA7"
                    elif p["TIME_STOP_MIN"] and not pos.get("be_activado") and pos.get("t_entrada_iso"):
                        try:
                            t_ent = datetime.strptime(pos["t_entrada_iso"], "%Y-%m-%d %H:%M:%S")
                            if (ahora - t_ent).total_seconds() >= p["TIME_STOP_MIN"] * 60:
                                motivo_salida = "TIME_STOP"
                        except Exception:
                            pass
                    if motivo_salida:
                        self.cerrar(estado, simbolo, pos, res, motivo_salida, ganancia, ahora)
                        continue

            # ── BUSCAR ENTRADA (1 posición global) ────────────────────────────
            elif not ocupado:
                if simbolo in self.bloqueo and ahora < self.bloqueo[simbolo]:
                    estado_str = "BE_LOCK"
                else:
                    if simbolo in self.bloqueo:
                        del self.bloqueo[simbolo]
                    pasa, blk, motivo = p["evaluar"](res, adn, sesion)
                    estado_str = "DISPARANDO" if pasa else f"BLOQ:{blk[:40]}"
                    if pasa:
                        estado["posiciones"][simbolo] = {
                            "precio_entrada": res["p"], "precio_actual": res["p"],
                            "t1_hecho": False, "be_activado": False, "trailing_stop": -99,
                            "g_max": 0.0, "g_min": 0.0,
                            "t_entrada_iso": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                            "sesion": sesion, "motivo_entrada": motivo,
                            "slope_entrada": round(res.get("pendiente_7", 0), 4),
                            "vol_r_entrada": round(res.get("vol_r", 0), 2),
                            "atr_15m_entrada": round(res.get("atr_15m", 0), 4),
                            "k_entrada": round(res.get("k", 0), 1),
                            "btc_trend_entrada": res.get("btc_trend_suav", res.get("btc_trend", "?")),
                            "btc_score_ent": res.get("btc_score", 0),
                        }
                        ocupado = True
                        self.log_trade(
                            f"ENTRADA {self.name} | {motivo} | {simbolo} | P:{res['p']:.4f} | "
                            f"sesion:{sesion} | slope1h:{res.get('pendiente_7',0):+.3f}% | "
                            f"vol_r:{res.get('vol_r',0):.2f} | atr15m:{res.get('atr_15m',0):.3f}% | "
                            f"k:{res.get('k',0):.1f} | btc_suav:{res.get('btc_trend_suav','?')}"
                        )
            self.log_scan(
                f"SCAN {simbolo} | {utcnow():%H:%M}UTC | P:{res['p']:.4f} | "
                f"slope1h:{res.get('pendiente_7',0):+.3f}% | vol_r:{res.get('vol_r',0):.2f} | "
                f"atr15m:{res.get('atr_15m',0):.3f}% | k:{res.get('k',0):.1f} | "
                f"btc_suav:{res.get('btc_trend_suav','?')} | bal:{estado['balance']:.3f}"
            )
        self.guardar(estado)
        return ocupado

    def run(self):
        print(f"🧪 {self.name} — paper, 1 posición, comisión maker {self.cfg['COMM_RT']}% RT")
        self.log_trade(
            f"=== {self.name} INICIADO === T1:{self.cfg['T1_TARGET']}% BE:{self.cfg['BE_TRIGGER']}% "
            f"SL:{self.cfg['STOP_LOSS']}% trail:{self.cfg['TRAILING_DIST']}->{self.cfg['TRAILING2_DIST']}@{self.cfg['TRAILING2_DESDE']} "
            f"corte_ema7:{self.cfg['USE_CORTE_EMA7']} timestop:{self.cfg['TIME_STOP_MIN']} comision:{self.cfg['COMM_RT']}%"
        )
        while True:
            try:
                ocupado = self.ciclo()
            except Exception as e:
                self.log_scan(f"ERROR ciclo: {e}")
                ocupado = False
            time.sleep(SLEEP_POSICION if ocupado else SLEEP_LIBRE)
