# -*- coding: utf-8 -*-
"""
parse_events.py — Parsers de eventos (trades real, resultados sim, eventos de scan).

Complementa parse_lib.py (que tiene los parsers de líneas SCAN).
Aquí van los eventos discretos: ENTRADA/SALIDA de trades, y los marcadores
>>>/<<</SEÑAL_BLOQUEADA/POST_TRADE dentro del log de scans del simulador.
"""
import re
from parse_lib import _ts, _f


def _extract(line, fields):
    """fields = {nombre: (regex_compilado, cast)}. cast=None -> string crudo."""
    out = {}
    for name, (pat, cast) in fields.items():
        m = pat.search(line)
        if not m:
            out[name] = None
        elif cast is None:
            out[name] = m.group(1)
        else:
            try:
                out[name] = cast(m.group(1))
            except (ValueError, TypeError):
                out[name] = None
    return out


_TRUE = lambda x: x == "True"

# ---------------------------------------------------------------------------
# TRADES BOT REAL (log_trades_real.txt)
# ---------------------------------------------------------------------------

_TR_ENTRADA = {
    "precio":   (re.compile(r"\| P:([0-9.]+)"), float),
    "hora_utc": (re.compile(r"HORA:(\d{2}:\d{2})UTC"), None),
    "sesion":   (re.compile(r"SESION:(\w+)"), None),
    "k":        (re.compile(r"\| K:([0-9.]+)"), float),
    "d":        (re.compile(r"\bD:([0-9.]+)"), float),
    "slope1h":  (re.compile(r"Slope1h:([+\-]?[0-9.]+)%"), float),
    "slope15m": (re.compile(r"Slope15m:([+\-]?[0-9.]+)%"), float),
    "vol_r":    (re.compile(r"VolR:([0-9.]+)x"), float),
    "gap_ema7": (re.compile(r"GapEMA7:([+\-]?[0-9.]+)%"), float),
    "sobre_ema7": (re.compile(r"SobreEMA7:(True|False)"), _TRUE),
    "velas_cruce_15m": (re.compile(r"VelasCruce15m:([0-9]+)"), int),
    "btc_trend": (re.compile(r"\| BTC:(\w+)"), None),
    "gap200":   (re.compile(r"Gap200:([+\-]?[0-9.]+)%"), float),
    "atr_1h":   (re.compile(r"ATR_1H:([0-9.]+)%"), float),
    "atr_15m":  (re.compile(r"ATR_15M:([0-9.]+)%"), float),
    "atr_5m":   (re.compile(r"ATR_5M:([0-9.]+)%"), float),
    "funding":  (re.compile(r"Funding:([+\-]?[0-9.]+)"), float),
    "gap_vwap": (re.compile(r"GapVWAP:([+\-]?[0-9.]+)%"), float),
    "k15m":     (re.compile(r"K15m:([0-9.]+)"), float),
    "d15m":     (re.compile(r"D15m:([0-9.]+)"), float),
    "cuerpo_1h": (re.compile(r"Cuerpo1H:([0-9.]+)"), float),
    "obv_slope": (re.compile(r"OBV_slope:([+\-]?[0-9.]+)%"), float),
}

_TR_SALIDA = {
    "pnl":      (re.compile(r"PnL:([+\-]?[0-9.]+)%"), float),
    "p_entrada": (re.compile(r"P_entrada:([0-9.]+)"), float),
    "p_salida": (re.compile(r"P_salida:([0-9.]+)"), float),
    "max_pct":  (re.compile(r"Max:([+\-]?[0-9.]+)%"), float),
    "min_pct":  (re.compile(r"Min:([+\-]?[0-9.]+)%"), float),
    "sesion":   (re.compile(r"Sesion:(\w+)"), None),
    "btc_trend": (re.compile(r"\| BTC:(\w+)"), None),
    "motivo_entrada": (re.compile(r"Motivo:(\w+)"), None),
    "entrada_ts": (re.compile(r"Entrada:(\d{4}-\d{2}-\d{2} \d{2}:\d{2})"), None),
    "atr_1h_ent": (re.compile(r"ATR_1H_ent:([0-9.]+)%"), float),
    "atr_15m_ent": (re.compile(r"ATR_15M_ent:([0-9.]+)%"), float),
    "atr_1h_now": (re.compile(r"ATR_1H_now:([0-9.]+)%"), float),
    "atr_15m_now": (re.compile(r"ATR_15M_now:([0-9.]+)%"), float),
    "trail":    (re.compile(r"Trail:([+\-]?[0-9.]+)%"), float),
    "subida_post_t1": (re.compile(r"SubidaPostT1:([+\-]?[0-9.]+)%"), float),
}

_SYM_REAL = re.compile(r"\] (?:ENTRADA|SALIDA) \[[A-Z0-9_]+\] (\S+) \|")


def parse_trade_real(line):
    if "] ENTRADA [" in line:
        rec = {"ts": _ts(line), "bot": "real", "evento": "ENTRADA"}
        rec["motivo"] = _f(re.compile(r"ENTRADA \[([A-Z0-9_]+)\]"), line, cast=None)
        rec["symbol"] = _f(_SYM_REAL, line, cast=None)
        rec.update(_extract(line, _TR_ENTRADA))
        return rec
    if "] SALIDA [" in line:
        rec = {"ts": _ts(line), "bot": "real", "evento": "SALIDA"}
        rec["motivo"] = _f(re.compile(r"SALIDA \[([A-Z0-9_]+)\]"), line, cast=None)
        rec["symbol"] = _f(_SYM_REAL, line, cast=None)
        rec.update(_extract(line, _TR_SALIDA))
        return rec
    return None


# ---------------------------------------------------------------------------
# RESULTADOS SIMULADOR (simulacion_sniper_resultados.txt)
# ---------------------------------------------------------------------------

_RS_ENTRADA = {
    "precio":   (re.compile(r": P:([0-9.]+)"), float),
    "h_1h":     (re.compile(r"H_1H:([0-9.]+)"), float),
    "l_1h":     (re.compile(r"L_1H:([0-9.]+)"), float),
    "h_15m":    (re.compile(r"H_15M:([0-9.]+)"), float),
    "l_15m":    (re.compile(r"L_15M:([0-9.]+)"), float),
    "slope1h":  (re.compile(r"Slope:([+\-]?[0-9.]+)%"), float),
    "vol_r":    (re.compile(r"Vol_R:([0-9.]+)x"), float),
    "k":        (re.compile(r"\| K:([0-9.]+)"), float),
    "gap_ema7": (re.compile(r"GapEMA7:([+\-]?[0-9.]+)%"), float),
    "sobre_ema7": (re.compile(r"SobreEMA7:(True|False)"), _TRUE),
    "velas_cruce_15m": (re.compile(r"VelasCruce15m:([0-9]+)"), int),
    "slope15m": (re.compile(r"Slope_15m:([+\-]?[0-9.]+)%"), float),
    "btc_trend": (re.compile(r"\| BTC:(\w+)"), None),
    "gap200":   (re.compile(r"Gap200:([+\-]?[0-9.]+)%"), float),
    "sesion":   (re.compile(r"SESION:(\w+)"), None),
    "atr_1h":   (re.compile(r"ATR_1H:([0-9.]+)%"), float),
    "atr_15m":  (re.compile(r"ATR_15M:([0-9.]+)%"), float),
    "atr_5m":   (re.compile(r"ATR_5M:([0-9.]+)%"), float),
    "funding":  (re.compile(r"Funding:([+\-]?[0-9.]+)"), float),
    "gap_vwap": (re.compile(r"GapVWAP:([+\-]?[0-9.]+)%"), float),
    "k15m":     (re.compile(r"K15m:([0-9.]+)"), float),
    "d15m":     (re.compile(r"D15m:([0-9.]+)"), float),
    "cuerpo_1h": (re.compile(r"Cuerpo1H:([0-9.]+)"), float),
    "obv_slope": (re.compile(r"OBV_slope:([+\-]?[0-9.]+)%"), float),
}

_RS_SALIDA = {
    "pnl":      (re.compile(r"PnL:([+\-]?[0-9.]+)%"), float),
    "p_entrada": (re.compile(r"P_entrada:([0-9.]+)"), float),
    "p_salida": (re.compile(r"P_salida:([0-9.]+)"), float),
    "p_max":    (re.compile(r"P_max:([0-9.]+)"), float),
    "max_pct":  (re.compile(r"\(max:([+\-]?[0-9.]+)%\)"), float),
    "p_min":    (re.compile(r"P_min:([0-9.]+)"), float),
    "min_pct":  (re.compile(r"\(min:([+\-]?[0-9.]+)%\)"), float),
    "dur_h":    (re.compile(r"Dur:([0-9.]+)h"), float),
    "sesion":   (re.compile(r"Sesion:(\w+)"), None),
    "btc_trend": (re.compile(r"\| BTC:(\w+)"), None),
    "motivo_entrada": (re.compile(r"Motivo:(\w+)"), None),
    "balance":  (re.compile(r"BALANCE:\$([0-9.]+)"), float),
}

_RS_CIERRE = {
    "t1_pct":   (re.compile(r"T1:([+\-]?[0-9.]+)%"), float),
    "trail_pct": (re.compile(r"Trail:([+\-]?[0-9.]+)%"), float),
    "subida_post_t1": (re.compile(r"SubidaPostT1:([+\-]?[0-9.]+)%"), float),
    "p_entrada": (re.compile(r"P_entrada:([0-9.]+)"), float),
    "p_t1":     (re.compile(r"P_t1:([0-9.]+)"), float),
    "p_salida": (re.compile(r"P_salida:([0-9.]+)"), float),
    "p_max":    (re.compile(r"P_max:([0-9.]+)"), float),
    "max_pct":  (re.compile(r"\(max:([+\-]?[0-9.]+)%\)"), float),
    "p_min":    (re.compile(r"P_min:([0-9.]+)"), float),
    "min_pct":  (re.compile(r"\(min:([+\-]?[0-9.]+)%\)"), float),
    "trail_stop": (re.compile(r"Trail_stop:([+\-]?[0-9.]+)%"), float),
    "dur_h":    (re.compile(r"Dur:([0-9.]+)h"), float),
    "sesion":   (re.compile(r"Sesion:(\w+)"), None),
    "btc_trend": (re.compile(r"\| BTC:(\w+)"), None),
    "motivo_entrada": (re.compile(r"Motivo:(\w+)"), None),
    "balance":  (re.compile(r"BALANCE:\$([0-9.]+)"), float),
}

_RS_SYM = re.compile(r"(?:ENTRADA \[[A-Z0-9_]+\]|SALIDA \[[A-Z0-9_]+\]|CIERRE_TRAILING|T1 ALCANZADO|BE ACTIVADO) (\S+):\s")


def parse_result_sim(line):
    if "] ENTRADA [" in line:
        rec = {"ts": _ts(line), "bot": "sim", "evento": "ENTRADA"}
        rec["motivo"] = _f(re.compile(r"ENTRADA \[([A-Z0-9_]+)\]"), line, cast=None)
        rec["symbol"] = _f(_RS_SYM, line, cast=None)
        rec.update(_extract(line, _RS_ENTRADA))
        return rec
    if "] SALIDA [" in line:
        rec = {"ts": _ts(line), "bot": "sim", "evento": "SALIDA"}
        rec["motivo"] = _f(re.compile(r"SALIDA \[([A-Z0-9_]+)\]"), line, cast=None)
        rec["symbol"] = _f(_RS_SYM, line, cast=None)
        rec.update(_extract(line, _RS_SALIDA))
        return rec
    if "] CIERRE_TRAILING " in line:
        rec = {"ts": _ts(line), "bot": "sim", "evento": "CIERRE_TRAILING", "motivo": "CIERRE_TRAILING"}
        rec["symbol"] = _f(_RS_SYM, line, cast=None)
        rec.update(_extract(line, _RS_CIERRE))
        return rec
    if "] T1 ALCANZADO " in line:
        rec = {"ts": _ts(line), "bot": "sim", "evento": "T1"}
        rec["symbol"] = _f(_RS_SYM, line, cast=None)
        rec["balance"] = _f(re.compile(r"BALANCE:\$([0-9.]+)"), line)
        return rec
    if "BE ACTIVADO " in line:
        rec = {"ts": _ts(line), "bot": "sim", "evento": "BE"}
        rec["symbol"] = _f(_RS_SYM, line, cast=None)
        return rec
    return None


# ---------------------------------------------------------------------------
# EVENTOS DENTRO DEL LOG DE SCANS DEL SIMULADOR
# ---------------------------------------------------------------------------

_EV_BAL = re.compile(r"BAL:\$([0-9.]+)")
_EV_ID = re.compile(r"ID:([0-9_A-Z]+)")


def parse_scan_event(line):
    if ">>> ENTRADA" in line:
        return {
            "ts": _ts(line), "tipo": "ENTRADA",
            "motivo": _f(re.compile(r">>> ENTRADA \[([A-Z0-9_]+)\]"), line, cast=None),
            "symbol": _f(re.compile(r">>> ENTRADA \[[A-Z0-9_]+\] (\S+) \|"), line, cast=None),
            "id_trade": _f(_EV_ID, line, cast=None),
            "precio": _f(re.compile(r"\| P:([0-9.]+)"), line),
            "balance": _f(_EV_BAL, line),
        }
    if "<<< SALIDA" in line:
        return {
            "ts": _ts(line), "tipo": "SALIDA",
            "motivo": _f(re.compile(r"<<< SALIDA \[([A-Z0-9_]+)\]"), line, cast=None),
            "symbol": _f(re.compile(r"<<< SALIDA \[[A-Z0-9_]+\] (\S+) \|"), line, cast=None),
            "id_trade": _f(_EV_ID, line, cast=None),
            "pnl": _f(re.compile(r"PnL:([+\-]?[0-9.]+)%"), line),
            "balance": _f(_EV_BAL, line),
        }
    if "<<< CIERRE_TRAILING" in line:
        return {
            "ts": _ts(line), "tipo": "CIERRE_TRAILING", "motivo": "CIERRE_TRAILING",
            "symbol": _f(re.compile(r"<<< CIERRE_TRAILING (\S+) \|"), line, cast=None),
            "id_trade": _f(_EV_ID, line, cast=None),
            "pnl": _f(re.compile(r"PnL_trail:([+\-]?[0-9.]+)%"), line),
            "balance": _f(_EV_BAL, line),
        }
    if "SEÑAL_BLOQUEADA" in line:
        return {
            "ts": _ts(line), "tipo": "SENAL_BLOQUEADA",
            "motivo": _f(re.compile(r"SEÑAL_BLOQUEADA \[([A-Z0-9_]+)\]"), line, cast=None),
            "symbol": _f(re.compile(r"SEÑAL_BLOQUEADA \[[A-Z0-9_]+\] (\S+) \|"), line, cast=None),
            "precio": _f(re.compile(r"\| P:([0-9.]+)"), line),
            "vol_r": _f(re.compile(r"Vol_R:([0-9.]+)x"), line),
            "gap_ema7": _f(re.compile(r"GapEMA7:([+\-]?[0-9.]+)%"), line),
            "btc_trend": _f(re.compile(r"\| BTC:(\w+)"), line, cast=None),
            "sesion": _f(re.compile(r"SESION:(\w+)"), line, cast=None),
            "bloqueado_por": _f(re.compile(r"BLOQUEADO_POR:(.+)$"), line, cast=None),
        }
    return None
