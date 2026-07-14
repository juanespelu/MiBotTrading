# -*- coding: utf-8 -*-
"""
quality.py — Chequeos de calidad de datos.
  1. Anomalía VOL_R ~0 (frecuencia, cuándo, correlación).
  2. Continuidad de timestamps (huecos = bot caído / reinicios) real y sim.
  3. Cadencia de escaneo.
NO calcula métricas de estrategia.
"""
import pandas as pd
import datasets_io as io

GAP_MIN = 5


def vol_r_anomaly(bot):
    sc = io.load_scans(bot, columns=["dt", "symbol", "vol_r", "semana", "hora_utc", "k"])
    n = len(sc)
    zero = sc["vol_r"] == 0.0
    tiny = sc["vol_r"] <= 0.01
    print(f"\n--- VOL_R anómalo [{bot}]  (n={n}) ---")
    print(f"  vol_r == 0.00 : {zero.sum():>7}  ({100*zero.mean():.2f}%)")
    print(f"  vol_r <= 0.01 : {tiny.sum():>7}  ({100*tiny.mean():.2f}%)")
    print(f"  vol_r nulo    : {sc['vol_r'].isna().sum():>7}")
    if tiny.sum():
        sub = sc[tiny]
        print("  por semana:", sub.groupby("semana").size().to_dict())
        print("  por símbolo:", sub.groupby("symbol").size().to_dict())
        # correlación con hora (¿coincide con un fetch específico/minuto?)
        sub = sub.copy()
        sub["min"] = sub["dt"].dt.minute
        top_min = sub["min"].value_counts().head(5).to_dict()
        print("  minutos del reloj más frecuentes (vol_r<=0.01):", top_min)
        # ¿el resto de la fila es válida? (precio/k presentes)
        print(f"  filas vol_r<=0.01 con K presente: {sub['k'].notna().mean()*100:.1f}% "
              f"(si ~100%, el resto del scan es válido; es solo el volumen)")
    return {"n": n, "zero": int(zero.sum()), "tiny": int(tiny.sum())}


def continuity(bot):
    sc = io.load_scans(bot, columns=["dt"])
    ts = sc["dt"].dropna().sort_values()
    diffs = ts.diff()
    gaps_mask = diffs > pd.Timedelta(minutes=GAP_MIN)
    gaps = pd.DataFrame({"ini": ts.shift(1)[gaps_mask].values, "fin": ts[gaps_mask].values})
    print(f"\n--- Continuidad [{bot}] ---")
    print(f"  rango: {ts.min()}  ->  {ts.max()}")
    print(f"  scans: {len(ts)} | cadencia mediana: {diffs.median().total_seconds():.2f}s "
          f"| p95: {diffs.quantile(0.95).total_seconds():.1f}s")
    print(f"  huecos > {GAP_MIN}min: {len(gaps)}")
    tot_down = 0.0
    for _, g in gaps.iterrows():
        h = (g["fin"] - g["ini"]).total_seconds() / 3600
        tot_down += h
        print(f"    {g['ini']}  ->  {g['fin']}   ({h:.1f}h)")
    print(f"  downtime total (huecos): {tot_down:.1f}h")
    return gaps


if __name__ == "__main__":
    print("=" * 64)
    print("CALIDAD DE DATOS")
    print("=" * 64)
    vol_r_anomaly("real")
    vol_r_anomaly("sim")
    continuity("real")
    continuity("sim")
