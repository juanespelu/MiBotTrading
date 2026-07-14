# -*- coding: utf-8 -*-
"""
parse_lib.py — Librería de parseo de logs de MiBotTrading.

Convierte las líneas de texto de los logs (bot real y simulador) en
diccionarios tipados. Cada formato tiene su parser porque los nombres de
campo difieren entre bot real y simulador.

Diseño robusto: cada campo se extrae con su propio regex anclado a la
etiqueta (LABEL:VALUE). Esto evita el problema de partir por '|' cuando
campos de texto libre (BLOCK, ESTADO) contienen pipes internos.

NO calcula métricas de estrategia. Solo estructura datos crudos.
"""
import re

# ---------------------------------------------------------------------------
# Helpers de extracción
# ---------------------------------------------------------------------------

_TS = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


def _ts(line):
    m = _TS.match(line)
    return m.group(1) if m else None


def _f(pattern, line, group=1, cast=float):
    """Extrae y castea el primer match de `pattern` en `line`, o None."""
    m = pattern.search(line)
    if not m:
        return None
    val = m.group(group)
    if cast is None:
        return val
    try:
        return cast(val)
    except (ValueError, TypeError):
        return None


def _bool(pattern, line):
    m = pattern.search(line)
    if not m:
        return None
    return m.group(1) == "True"


# ---------------------------------------------------------------------------
# SCAN — BOT REAL
# formato: SCAN {sym} | HORA:{}UTC | P:{} | Slope1h:{%} | VolR:{x} | K:{} | D:{} |
#   GapEMA7:{%} | SobreEMA7:{bool} | Cruce1h:{} | Slope15m:{%} | Cruce15m:{} |
#   VelasCruce15m:{n} | BTC:{} | BLOCK:{...} | Estado:{...} | ATR_1H:{%} |
#   ATR_15M:{%} | Funding:{} | FundAlto:{bool} | GapVWAP:{%} | K15m:{} | D15m:{} |
#   Cuerpo1H:{} | VelaAlc:{bool} | OBV:{%}
# ---------------------------------------------------------------------------

_R = {
    "symbol":   re.compile(r"SCAN (\S+) \|"),
    "hora_utc": re.compile(r"HORA:(\d{2}:\d{2})UTC"),
    "precio":   re.compile(r"\| P:([0-9.]+)"),
    "slope1h":  re.compile(r"Slope1h:([+\-]?[0-9.]+)%"),
    "vol_r":    re.compile(r"VolR:([0-9.]+)x"),
    "k":        re.compile(r"\| K:([0-9.]+)"),
    "d":        re.compile(r"\| D:([0-9.]+)"),
    "gap_ema7": re.compile(r"GapEMA7:([+\-]?[0-9.]+)%"),
    "slope15m": re.compile(r"Slope15m:([+\-]?[0-9.]+)%"),
    "velas_cruce_15m": re.compile(r"VelasCruce15m:([0-9]+)"),
    "atr_1h":   re.compile(r"ATR_1H:([0-9.]+)%"),
    "atr_15m":  re.compile(r"ATR_15M:([0-9.]+)%"),
    "funding":  re.compile(r"Funding:([+\-]?[0-9.]+)"),
    "gap_vwap": re.compile(r"GapVWAP:([+\-]?[0-9.]+)%"),
    "k15m":     re.compile(r"K15m:([0-9.]+)"),
    "d15m":     re.compile(r"D15m:([0-9.]+)"),
    "cuerpo_1h": re.compile(r"Cuerpo1H:([0-9.]+)"),
    "obv":      re.compile(r"OBV:([+\-]?[0-9.]+)%"),
}
_R_sobre = re.compile(r"SobreEMA7:(True|False)")
_R_velaalc = re.compile(r"VelaAlc:(True|False)")
_R_fundalto = re.compile(r"FundAlto:(True|False)")
_R_btc = re.compile(r"\| BTC:(ALCISTA|BAJISTA|LATERAL)")
_R_cruce1h = re.compile(r"Cruce1h:([^|]*?) \|")
_R_cruce15m = re.compile(r"Cruce15m:([^|]*?) \|")
_R_block = re.compile(r"\| BLOCK:(.*?) \| Estado:")
_R_estado = re.compile(r"\| Estado:(.*?) \| ATR_1H:")
# estado parseado
_R_open_pct = re.compile(r"OPEN\(([+\-][0-9.]+)%\)")


def parse_scan_real(line):
    if "SCAN " not in line:
        return None
    rec = {"ts": _ts(line), "bot": "real"}
    for k, pat in _R.items():
        cast = int if k == "velas_cruce_15m" else float
        rec[k] = _f(pat, line, cast=cast)
    rec["symbol"] = _f(_R["symbol"], line, cast=None)
    rec["hora_utc"] = _f(_R["hora_utc"], line, cast=None)
    rec["sobre_ema7"] = _bool(_R_sobre, line)
    rec["vela_alc"] = _bool(_R_velaalc, line)
    rec["fund_alto"] = _bool(_R_fundalto, line)
    rec["btc_trend"] = _f(_R_btc, line, cast=None)
    rec["cruce_1h"] = (_f(_R_cruce1h, line, cast=None) or "").strip()
    rec["cruce_15m"] = (_f(_R_cruce15m, line, cast=None) or "").strip()
    rec["block"] = (_f(_R_block, line, cast=None) or "").strip()
    estado = (_f(_R_estado, line, cast=None) or "").strip()
    rec["estado_raw"] = estado
    rec["estado_tipo"] = _clasificar_estado_real(estado)
    return rec


def _clasificar_estado_real(estado):
    if not estado:
        return None
    if estado.startswith("LIBRE"):
        return "LIBRE"
    if estado.startswith("OPEN"):
        return "OPEN"
    if estado.startswith("DISPARANDO"):
        return "DISPARANDO"
    if estado.startswith("ESPERA"):
        return "ESPERA"
    if "BLOQ_SL" in estado:
        return "BLOQ_SL"
    if estado.startswith("BLOQ"):
        return "BLOQ"
    return "OTRO"


# ---------------------------------------------------------------------------
# SCAN — SIMULADOR
# formato: SCAN {sym} | HORA:{}UTC | SESION:{} | P:{} | H_1H:{} | L_1H:{} |
#   H_15M:{} | L_15M:{} | Slope1h:{%} | Vol_R:{x} | K:{} | D:{} | EMA5:{} |
#   EMA7:{} | GapEMA7_1h:{%} | SobreEMA7:{bool} | gEMAS:{%} | CRUCE_1H:{} |
#   EMA5_15M:{} | EMA7_15M:{} | SLOPE_EMA5_15M:{%} | CRUCE_15M:{} |
#   VELAS_CRUCE_15M:{n} | BTC:{precio} | BTC_SLOPE:{%} | BTC_TREND:{} | MA50:{} |
#   Gap200:{%} | BLOCK:{...} | FILTROS:{...} | ESTADO:{...} | ATR_1H:{%} |
#   ATR_15M:{%} | Funding:{} | FundAlto:{bool} | GapVWAP:{%} | K15m:{} | D15m:{} |
#   Cuerpo1H:{} | VelaAlc:{bool} | OBV:{%}
# ---------------------------------------------------------------------------

_S = {
    "symbol":   re.compile(r"SCAN (\S+) \|"),
    "hora_utc": re.compile(r"HORA:(\d{2}:\d{2})UTC"),
    "precio":   re.compile(r"\| P:([0-9.]+)"),
    "h_1h":     re.compile(r"H_1H:([0-9.]+)"),
    "l_1h":     re.compile(r"L_1H:([0-9.]+)"),
    "h_15m":    re.compile(r"H_15M:([0-9.]+)"),
    "l_15m":    re.compile(r"L_15M:([0-9.]+)"),
    "slope1h":  re.compile(r"Slope1h:([+\-]?[0-9.]+)%"),
    "vol_r":    re.compile(r"Vol_R:([0-9.]+)x"),
    "k":        re.compile(r"\| K:([0-9.]+)"),
    "d":        re.compile(r"\| D:([0-9.]+)"),
    "ema5":     re.compile(r"\| EMA5:([0-9.]+)"),
    "ema7":     re.compile(r"\| EMA7:([0-9.]+)"),
    "gap_ema7": re.compile(r"GapEMA7_1h:([+\-]?[0-9.]+)%"),
    "gemas":    re.compile(r"gEMAS:([+\-]?[0-9.]+)%"),
    "ema5_15m": re.compile(r"EMA5_15M:([0-9.]+)"),
    "ema7_15m": re.compile(r"EMA7_15M:([0-9.]+)"),
    "slope15m": re.compile(r"SLOPE_EMA5_15M:([+\-]?[0-9.]+)%"),
    "velas_cruce_15m": re.compile(r"VELAS_CRUCE_15M:([0-9]+)"),
    "btc_precio": re.compile(r"\| BTC:([0-9.]+)"),
    "btc_slope": re.compile(r"BTC_SLOPE:([+\-]?[0-9.]+)%"),
    "ma50":     re.compile(r"MA50:([0-9.]+)"),
    "gap200":   re.compile(r"Gap200:([+\-]?[0-9.]+)%"),
    "atr_1h":   re.compile(r"ATR_1H:([0-9.]+)%"),
    "atr_15m":  re.compile(r"ATR_15M:([0-9.]+)%"),
    "funding":  re.compile(r"Funding:([+\-]?[0-9.]+)"),
    "gap_vwap": re.compile(r"GapVWAP:([+\-]?[0-9.]+)%"),
    "k15m":     re.compile(r"K15m:([0-9.]+)"),
    "d15m":     re.compile(r"D15m:([0-9.]+)"),
    "cuerpo_1h": re.compile(r"Cuerpo1H:([0-9.]+)"),
    "obv":      re.compile(r"OBV:([+\-]?[0-9.]+)%"),
}
_S_sesion = re.compile(r"SESION:(ASIATICA|EUROPEA|AMERICANA)")
_S_btc_trend = re.compile(r"BTC_TREND:(ALCISTA|BAJISTA|LATERAL)")
_S_cruce1h = re.compile(r"CRUCE_1H:([^|]*?) \|")
_S_cruce15m = re.compile(r"CRUCE_15M:([^|]*?) \|")
_S_block = re.compile(r"\| BLOCK:(.*?) \| FILTROS:")
_S_filtros = re.compile(r"\| FILTROS:(.*?) \| ESTADO:")
_S_estado = re.compile(r"\| ESTADO:(.*?) \| ATR_1H:")
_S_enpos = re.compile(r"EN_POSICION\(([+\-][0-9.]+)%\) ID:(\S+)")


def parse_scan_sim(line):
    if "SCAN " not in line:
        return None
    rec = {"ts": _ts(line), "bot": "sim"}
    for k, pat in _S.items():
        cast = int if k == "velas_cruce_15m" else float
        rec[k] = _f(pat, line, cast=cast)
    rec["symbol"] = _f(_S["symbol"], line, cast=None)
    rec["hora_utc"] = _f(_S["hora_utc"], line, cast=None)
    rec["sesion"] = _f(_S_sesion, line, cast=None)
    rec["sobre_ema7"] = _bool(re.compile(r"SobreEMA7:(True|False)"), line)
    rec["vela_alc"] = _bool(re.compile(r"VelaAlc:(True|False)"), line)
    rec["fund_alto"] = _bool(re.compile(r"FundAlto:(True|False)"), line)
    rec["btc_trend"] = _f(_S_btc_trend, line, cast=None)
    rec["cruce_1h"] = (_f(_S_cruce1h, line, cast=None) or "").strip()
    rec["cruce_15m"] = (_f(_S_cruce15m, line, cast=None) or "").strip()
    rec["block"] = (_f(_S_block, line, cast=None) or "").strip()
    rec["filtros"] = (_f(_S_filtros, line, cast=None) or "").strip()
    estado = (_f(_S_estado, line, cast=None) or "").strip()
    rec["estado_raw"] = estado
    m = _S_enpos.search(estado)
    if m:
        rec["estado_tipo"] = "EN_POSICION"
        rec["pos_pnl"] = float(m.group(1))
        rec["pos_id"] = m.group(2)
    elif estado.startswith("LIBRE"):
        rec["estado_tipo"] = "LIBRE"
        rec["pos_pnl"] = None
        rec["pos_id"] = None
    else:
        rec["estado_tipo"] = "OTRO"
        rec["pos_pnl"] = None
        rec["pos_id"] = None
    return rec
