# -*- coding: utf-8 -*-
"""
build.py — Construye los datasets estructurados desde los logs crudos.

Lee de  analisis_VPS_2026-06-04/  (extracto del VPS, NO se modifica)
Escribe en  analisis/datasets/  (parquet)

Salidas:
  scans_real/<week>.parquet      — 1 fila por scan del bot real
  scans_sim/<week>.parquet       — 1 fila por scan del simulador
  events_trades_real.parquet     — ENTRADA/SALIDA del log de trades real
  events_results_sim.parquet     — ENTRADA/SALIDA/CIERRE/T1/BE del archivo de resultados
  events_scan_sim.parquet        — >>>/<<</SEÑAL_BLOQUEADA dentro de los scans del sim

Uso:  python build.py
Streaming por archivo para no cargar 2GB en RAM de golpe.
"""
import os
import io
import glob
import time
import re
import pandas as pd

import parse_lib as PL
import parse_events as PE

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "analisis_VPS_2026-06-04")
OUT = os.path.join(HERE, "datasets")

WEEK_RE = re.compile(r"(2026-W\d+)")


def _read_lines(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield line


def _to_df(records, ts_col="ts"):
    df = pd.DataFrame(records)
    if not df.empty and ts_col in df.columns:
        df["dt"] = pd.to_datetime(df[ts_col], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    return df


def build_scans(bot):
    parser = PL.parse_scan_real if bot == "real" else PL.parse_scan_sim
    subdir = "logs_real" if bot == "real" else "logs_simulador"
    outdir = os.path.join(OUT, f"scans_{bot}")
    os.makedirs(outdir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC, subdir, "log_scans_2026-W*.txt")))
    total = 0
    sim_events = []          # solo sim: >>> <<< SEÑAL_BLOQUEADA
    for path in files:
        week = WEEK_RE.search(path).group(1)
        t0 = time.time()
        scans = []
        for line in _read_lines(path):
            if "SCAN " in line:
                r = parser(line)
                if r:
                    r["semana"] = week
                    scans.append(r)
            elif bot == "sim" and (">>>" in line or "<<<" in line or "SEÑAL_BLOQUEADA" in line):
                ev = PE.parse_scan_event(line)
                if ev:
                    ev["semana"] = week
                    sim_events.append(ev)
        df = _to_df(scans)
        df.to_parquet(os.path.join(outdir, f"{week}.parquet"), index=False)
        total += len(df)
        print(f"  [{bot}] {week}: {len(df):>7} scans  ({time.time()-t0:.1f}s)")
    print(f"  [{bot}] TOTAL scans: {total}")
    if bot == "sim":
        dfe = _to_df(sim_events)
        dfe.to_parquet(os.path.join(OUT, "events_scan_sim.parquet"), index=False)
        print(f"  [sim] eventos de scan (>>>/<<</SEÑAL): {len(dfe)}")
    return total


def build_trades_real():
    path = os.path.join(SRC, "logs_real", "log_trades_real.txt")
    recs = [r for line in _read_lines(path) if (r := PE.parse_trade_real(line))]
    df = _to_df(recs)
    df.to_parquet(os.path.join(OUT, "events_trades_real.parquet"), index=False)
    print(f"  [real] eventos de trades (ENTRADA/SALIDA): {len(df)}")
    return df


def build_results_sim():
    path = os.path.join(SRC, "logs_simulador", "simulacion_sniper_resultados.txt")
    recs = [r for line in _read_lines(path) if (r := PE.parse_result_sim(line))]
    df = _to_df(recs)
    df.to_parquet(os.path.join(OUT, "events_results_sim.parquet"), index=False)
    print(f"  [sim] eventos de resultados: {len(df)}")
    print("        por tipo:", df["evento"].value_counts().to_dict())
    return df


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    print("== Eventos de trades real ==")
    build_trades_real()
    print("== Eventos de resultados sim ==")
    build_results_sim()
    print("== Scans bot real ==")
    build_scans("real")
    print("== Scans simulador (2GB, paciencia) ==")
    build_scans("sim")
    print(f"\nLISTO en {time.time()-t0:.1f}s. Datasets en {OUT}")
