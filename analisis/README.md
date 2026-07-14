# analisis/ — Módulo de análisis de datos de MiBotTrading

Parsea los logs crudos de los bots (real + simulador) a datasets estructurados
(parquet) reutilizables, para no re-parsear millones de líneas en cada análisis.
Base del futuro skill de análisis de trades.

## Entorno
- Python 3.12 (venv del proyecto: `../venv/Scripts/python.exe`)
- pandas 3.0, numpy 2.2, pyarrow 24  (ver `requirements.txt`)

## Flujo
```
python build.py          # logs crudos -> datasets/ (scans, eventos)   (~2 min, 2GB)
python build_trades.py   # eventos -> trades_sim.parquet / trades_real.parquet
python reconstruct.py    # análisis de salidas faltantes del sim
python quality.py        # VOL_R + continuidad de timestamps
```

## Módulos
| Archivo | Qué hace |
|---------|----------|
| `parse_lib.py` | Parsers de líneas SCAN (formato real y sim, distintos) |
| `parse_events.py` | Parsers de eventos: trades real, resultados sim, marcadores >>>/<<</SEÑAL |
| `build.py` | Orquesta el parseo de los logs a parquet (streaming, no carga 2GB en RAM) |
| `build_trades.py` | Reconcilia ENTRADA↔SALIDA por símbolo → tabla de trades (1 fila/operación) |
| `reconstruct.py` | Identifica y diagnostica las salidas faltantes del simulador |
| `quality.py` | Chequeos de calidad (VOL_R anómalo, continuidad temporal) |
| `datasets_io.py` | Carga de los parquet ya construidos (helper reutilizable) |

## Datasets producidos (`datasets/`)
| Dataset | Filas | Contenido |
|---------|-------|-----------|
| `scans_real/<W>.parquet` | 1.18M | 1 fila por scan del bot real |
| `scans_sim/<W>.parquet` | 1.97M | 1 fila por scan del simulador |
| `events_trades_real.parquet` | 14 | ENTRADA/SALIDA del bot real |
| `events_results_sim.parquet` | 2643 | ENTRADA/SALIDA/CIERRE/T1/BE del simulador |
| `events_scan_sim.parquet` | 44997 | >>>/<<</SEÑAL_BLOQUEADA (con ID) |
| `trades_sim.parquet` | 1561 | trades sim reconciliados (entrada+salida) |
| `trades_real.parquet` | 7 | trades reales reconciliados |
| `trades_sim_reconstructed.parquet` | 1552 | trades sim por ID con estado de reconstrucción |

## Uso típico
```python
import datasets_io as io
trades = io.load_scans("sim", columns=["dt","symbol","vol_r","k","slope1h"])
import pandas as pd
t = pd.read_parquet("datasets/trades_sim.parquet")
modernos = t[(t.estado=="COMPLETO") & (t.semana>=15)]   # 496 trades confiables
```

## Notas importantes
- **Fuente de datos:** `../analisis_VPS_2026-06-04/` (extracto del VPS, no se modifica).
- **W13 = era pre-VPS rota** (entradas fantasma) → excluir. Usar **W15→W23**.
- **PnL de CIERRE_TRAILING**: computar desde `t1_pct + trail_pct` (no hay campo PnL único).
- Ver `REPORTE_SALUD_DATOS.md` para el detalle de completitud y confiabilidad.
