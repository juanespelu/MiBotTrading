# -*- coding: utf-8 -*-
"""
datasets_io.py — Carga de los datasets parquet ya construidos.
Helper reutilizable para no re-parsear los logs.
"""
import os
import glob
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "datasets")


def load_scans(bot, columns=None):
    """Carga todos los scans de un bot ('real' o 'sim') concatenando las semanas."""
    files = sorted(glob.glob(os.path.join(DATA, f"scans_{bot}", "*.parquet")))
    parts = [pd.read_parquet(f, columns=columns) for f in files]
    return pd.concat(parts, ignore_index=True)


def load_events_scan_sim():
    return pd.read_parquet(os.path.join(DATA, "events_scan_sim.parquet"))


def load_events_results_sim():
    return pd.read_parquet(os.path.join(DATA, "events_results_sim.parquet"))


def load_events_trades_real():
    return pd.read_parquet(os.path.join(DATA, "events_trades_real.parquet"))
