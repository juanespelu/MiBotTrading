# -*- coding: utf-8 -*-
"""
reconstruct.py — Reconstrucción de salidas faltantes del simulador.

Problema: 1561 ENTRADAS vs ~512 cierres registrados → ~1049 entradas sin SALIDA.
Estrategia:
  - clave = id_trade (presente en los marcadores >>> y <<< del log de scans)
  - cierres explícitos = eventos <<< SALIDA / <<< CIERRE_TRAILING
  - para entradas sin cierre: el último scan con ESTADO:EN_POSICION(+x%) ID:{id}
    da el último PnL conocido antes de que la posición desaparezca.
  - se clasifica si la desaparición coincide con un reinicio (hueco en timestamps).

Salida: datasets/trades_sim_reconstructed.parquet  + reporte por stdout.
"""
import os
import numpy as np
import pandas as pd
import datasets_io as io

OUT = io.DATA
GAP_MIN = 5            # un hueco > 5 min en los scans = bot caído/reinicio
NEAR_RESTART_MIN = 10  # "desaparición cerca de reinicio" si last_seen a < 10 min del hueco


def main():
    ev = io.load_events_scan_sim()
    entries = ev[ev["tipo"] == "ENTRADA"].copy()
    closes = ev[ev["tipo"].isin(["SALIDA", "CIERRE_TRAILING"])].copy()

    # --- dedupe por id (por si un id aparece 2 veces) ---
    entries = entries.sort_values("dt").drop_duplicates("id_trade", keep="first")
    closes = closes.sort_values("dt").drop_duplicates("id_trade", keep="first")

    n_entries = len(entries)
    closed_ids = set(closes["id_trade"].dropna())
    entry_ids = set(entries["id_trade"].dropna())

    # --- tracking EN_POSICION desde los scans ---
    sc = io.load_scans("sim", columns=["dt", "symbol", "estado_tipo", "pos_id", "pos_pnl"])
    pos = sc[sc["estado_tipo"] == "EN_POSICION"].dropna(subset=["pos_id"]).copy()
    pos = pos.sort_values("dt")
    track = pos.groupby("pos_id").agg(
        primer_scan=("dt", "first"),
        ultimo_scan=("dt", "last"),
        n_scans=("dt", "size"),
        pnl_ultimo=("pos_pnl", "last"),
        pnl_max=("pos_pnl", "max"),
        pnl_min=("pos_pnl", "min"),
    )
    tracked_ids = set(track.index)

    # --- huecos de reinicio en la línea de tiempo de scans ---
    ts = sc["dt"].dropna().sort_values().drop_duplicates()
    diffs = ts.diff()
    gaps = ts[diffs > pd.Timedelta(minutes=GAP_MIN)]
    gap_starts = ts.shift(1)[diffs > pd.Timedelta(minutes=GAP_MIN)].dropna()
    gap_list = pd.DataFrame({"gap_ini": gap_starts.values, "gap_fin": gaps.values})

    def cerca_de_reinicio(last_seen):
        if pd.isna(last_seen) or gap_list.empty:
            return False
        d = (gap_list["gap_ini"] - last_seen).dt.total_seconds()
        d = d[(d >= -60)]  # huecos que empiezan en/después del último visto
        return bool((d.abs() < NEAR_RESTART_MIN * 60).any())

    # --- construir tabla canónica de trades ---
    rows = []
    for _, e in entries.iterrows():
        idt = e["id_trade"]
        row = {
            "id_trade": idt, "symbol": e["symbol"], "ts_entrada": e["dt"],
            "precio_entrada": e["precio"], "bal_entrada": e["balance"], "motivo": e["motivo"],
        }
        if idt in closed_ids:
            c = closes[closes["id_trade"] == idt].iloc[0]
            row.update(estado="COMPLETO", fuente_cierre="evento_<<<",
                       ts_cierre=c["dt"], pnl=c["pnl"], motivo_cierre=c["motivo"])
        elif idt in tracked_ids:
            t = track.loc[idt]
            cerca = cerca_de_reinicio(t["ultimo_scan"])
            row.update(estado="RECUPERADO",
                       fuente_cierre="reinicio" if cerca else "trunco",
                       ts_cierre=t["ultimo_scan"], pnl=t["pnl_ultimo"], motivo_cierre=None,
                       pnl_max=t["pnl_max"], pnl_min=t["pnl_min"], n_scans_pos=t["n_scans"],
                       cerca_reinicio=cerca)
        else:
            row.update(estado="DESCONOCIDO", fuente_cierre=None, ts_cierre=pd.NaT,
                       pnl=np.nan, motivo_cierre=None)
        rows.append(row)
    trades = pd.DataFrame(rows)
    trades.to_parquet(os.path.join(OUT, "trades_sim_reconstructed.parquet"), index=False)

    # ----------------------------- REPORTE -----------------------------
    vc = trades["estado"].value_counts()
    n_comp = int(vc.get("COMPLETO", 0))
    n_rec = int(vc.get("RECUPERADO", 0))
    n_unk = int(vc.get("DESCONOCIDO", 0))
    print("=" * 64)
    print("RECONSTRUCCIÓN DE SALIDAS DEL SIMULADOR")
    print("=" * 64)
    print(f"Entradas con ID (scans):        {n_entries}")
    print(f"  COMPLETO   (cierre explícito <<<):  {n_comp}")
    print(f"  RECUPERADO (último EN_POSICION):    {n_rec}")
    print(f"  DESCONOCIDO(sin tracking):          {n_unk}")
    print(f"  -> usable (completo+recuperado):    {n_comp + n_rec}  ({100*(n_comp+n_rec)/n_entries:.1f}%)")
    print()
    rec = trades[trades["estado"] == "RECUPERADO"]
    if len(rec):
        cerca = int(rec["cerca_reinicio"].sum())
        print(f"De los {n_rec} RECUPERADOS:")
        print(f"  desaparición JUNTO a un reinicio: {cerca}  ({100*cerca/n_rec:.1f}%)")
        print(f"  desaparición sin reinicio cerca:  {n_rec - cerca}")
        print(f"  PnL último conocido — media {rec['pnl'].mean():.3f}% | "
              f"mediana {rec['pnl'].median():.3f}% | min {rec['pnl'].min():.2f}% | max {rec['pnl'].max():.2f}%")
        print(f"  ¿estaban en verde (pnl>0) al desaparecer?  "
              f"{int((rec['pnl']>0).sum())} sí / {int((rec['pnl']<=0).sum())} no")
    print()
    print(f"Huecos de reinicio detectados (>{GAP_MIN}min) en scans sim: {len(gap_list)}")
    if len(gap_list):
        print("  primeros 12 huecos (ini -> fin, duración):")
        for _, g in gap_list.head(12).iterrows():
            dur = (g["gap_fin"] - g["gap_ini"]).total_seconds() / 3600
            print(f"    {g['gap_ini']}  ->  {g['gap_fin']}   ({dur:.1f}h)")

    # distribución temporal de incompletos (para diagnóstico sistemático/aleatorio)
    inc = trades[trades["estado"].isin(["RECUPERADO", "DESCONOCIDO"])].copy()
    inc["sem"] = inc["ts_entrada"].dt.isocalendar().week
    comp = trades[trades["estado"] == "COMPLETO"].copy()
    comp["sem"] = comp["ts_entrada"].dt.isocalendar().week
    print()
    print("Entradas por semana ISO:  completas vs incompletas")
    allw = sorted(set(inc["sem"].dropna()) | set(comp["sem"].dropna()))
    for w in allw:
        c = int((comp["sem"] == w).sum())
        i = int((inc["sem"] == w).sum())
        tot = c + i
        print(f"  W{int(w):<2}:  total {tot:>4}  | completas {c:>4} ({100*c/tot:>5.1f}%) | incompletas {i:>4}")


if __name__ == "__main__":
    main()
