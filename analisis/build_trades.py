# -*- coding: utf-8 -*-
"""
build_trades.py — Tabla TRADES reconciliada (1 fila por operación).

Empareja ENTRADA -> (BE/T1) -> SALIDA/CIERRE por símbolo en orden cronológico.
Regla del sim: 1 posición por símbolo a la vez, así que el emparejado secuencial
por símbolo es correcto. Una ENTRADA seguida de otra ENTRADA del mismo símbolo
sin cierre intermedio = entrada sin cierre (fantasma de la era W13).

Salida: datasets/trades_sim.parquet, datasets/trades_real.parquet
NO calcula métricas de estrategia; el split G/P crudo es solo reconciliación.
"""
import os
import pandas as pd
import datasets_io as io

OUT = io.DATA

_ENTRY_CTX = ["precio", "slope1h", "slope15m", "vol_r", "k", "gap_ema7", "sobre_ema7",
              "velas_cruce_15m", "btc_trend", "gap200", "sesion", "atr_1h", "atr_15m",
              "atr_5m", "funding", "gap_vwap", "k15m", "d15m", "cuerpo_1h", "obv_slope",
              "h_1h", "l_1h", "h_15m", "l_15m"]
_EXIT_FIELDS = ["pnl", "p_entrada", "p_salida", "p_max", "max_pct", "p_min", "min_pct",
                "dur_h", "balance", "t1_pct", "trail_pct", "subida_post_t1", "trail_stop"]


def reconcile_sim():
    ev = io.load_events_results_sim().sort_values("dt").reset_index(drop=True)
    pend = {}   # symbol -> dict de la entrada abierta
    trades = []
    for _, e in ev.iterrows():
        sym, tipo = e["symbol"], e["evento"]
        if tipo == "ENTRADA":
            if sym in pend:
                # entrada previa sin cierre -> fantasma
                p = pend[sym]; p["estado"] = "SIN_CIERRE"; trades.append(p)
            pend[sym] = {"symbol": sym, "ts_entrada": e["dt"], "motivo": e["motivo"],
                         "be": False, "t1": False,
                         **{f"ent_{c}": e.get(c) for c in _ENTRY_CTX}}
        elif tipo == "BE" and sym in pend:
            pend[sym]["be"] = True
        elif tipo == "T1" and sym in pend:
            pend[sym]["t1"] = True
            pend[sym]["t1_balance"] = e.get("balance")
        elif tipo in ("SALIDA", "CIERRE_TRAILING") and sym in pend:
            p = pend.pop(sym)
            p["estado"] = "COMPLETO"
            p["evento_cierre"] = tipo
            p["motivo_cierre"] = e.get("motivo")
            p["ts_cierre"] = e["dt"]
            for f in _EXIT_FIELDS:
                p[f] = e.get(f)
            trades.append(p)
    for sym, p in pend.items():       # quedaron abiertas al final
        p["estado"] = "SIN_CIERRE"; trades.append(p)
    df = pd.DataFrame(trades)
    df["semana"] = df["ts_entrada"].dt.isocalendar().week.astype("Int64")
    df.to_parquet(os.path.join(OUT, "trades_sim.parquet"), index=False)
    return df


def reconcile_real():
    ev = io.load_events_trades_real().sort_values("dt").reset_index(drop=True)
    pend = {}
    trades = []
    for _, e in ev.iterrows():
        sym, tipo = e["symbol"], e["evento"]
        if tipo == "ENTRADA":
            pend[sym] = {"symbol": sym, "ts_entrada": e["dt"], "motivo": e["motivo"],
                         **{f"ent_{c}": e.get(c) for c in
                            ["precio", "slope1h", "slope15m", "vol_r", "k", "d", "gap_ema7",
                             "sobre_ema7", "velas_cruce_15m", "btc_trend", "gap200", "sesion",
                             "atr_1h", "atr_15m", "atr_5m", "funding", "gap_vwap", "k15m",
                             "d15m", "cuerpo_1h", "obv_slope"]}}
        elif tipo == "SALIDA" and sym in pend:
            p = pend.pop(sym)
            p["estado"] = "COMPLETO"
            p["motivo_cierre"] = e.get("motivo")
            p["ts_cierre"] = e["dt"]
            for f in ["pnl", "p_entrada", "p_salida", "max_pct", "min_pct"]:
                p[f] = e.get(f)
            trades.append(p)
    df = pd.DataFrame(trades)
    df.to_parquet(os.path.join(OUT, "trades_real.parquet"), index=False)
    return df


if __name__ == "__main__":
    print("== Reconciliación SIM ==")
    s = reconcile_sim()
    comp = s[s["estado"] == "COMPLETO"]
    sincierre = s[s["estado"] == "SIN_CIERRE"]
    print(f"  filas totales: {len(s)} | COMPLETO: {len(comp)} | SIN_CIERRE: {len(sincierre)}")
    modern = comp[comp["semana"] >= 15]
    w13 = comp[comp["semana"] == 13]
    print(f"  COMPLETO por era: W13={len(w13)} | W15+={len(modern)}")
    print(f"  SIN_CIERRE por semana: {sincierre['ts_entrada'].dt.isocalendar().week.value_counts().sort_index().to_dict()}")
    # split crudo G/P SOLO como reconciliación (no conclusión de estrategia)
    print(f"  [reconciliación] split crudo PnL en COMPLETO modernos (W15+): "
          f"G={int((modern['pnl']>0).sum())} / P={int((modern['pnl']<=0).sum())} "
          f"| nulos pnl={int(modern['pnl'].isna().sum())}")
    print("\n== Reconciliación REAL ==")
    r = reconcile_real()
    print(f"  trades: {len(r)} | COMPLETO: {int((r['estado']=='COMPLETO').sum())}")
    print(f"  [reconciliación] split crudo: G={int((r['pnl']>0).sum())} / P={int((r['pnl']<=0).sum())}")
    print("\nGuardado trades_sim.parquet y trades_real.parquet")
