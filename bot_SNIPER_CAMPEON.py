"""
bot_SNIPER_CAMPEON.py — Paper bot CAMPEÓN (control del experimento W24).

Corre el MISMO cerebro que el bot real (importa el filtro de entrada y TODOS
los parámetros de gestión desde bot_maestro_v4), en paper, una posición a la vez.
Comisión maker (ejecución ideal). El Δ REAL vs CAMPEÓN aísla la ejecución real
(fills de las limit + slippage). NO coloca órdenes reales.
"""
import bot_maestro_v4 as real
from paper_engine import PaperBot

CFG = dict(
    name="CAMPEON",
    state_file="estado_campeon.json",
    logs_dir="logs_campeon",
    trades_file="trades_campeon.txt",
    # MISMO cerebro de entrada que el real (incluye C1 piso ATR, F1-F5, BTC_suav)
    evaluar=real.evaluar_filtros_sniper,
    # MISMOS parámetros de gestión que el real
    T1_TARGET=real.T1_TARGET,
    BE_TRIGGER=real.BE_TRIGGER,
    BE_STOP=real.BE_STOP,
    STOP_LOSS=real.STOP_LOSS,
    SUELO_POST_T1=real.SUELO_POST_T1,
    TRAILING_DIST=real.TRAILING_DIST,
    TRAILING2_DIST=real.TRAILING2_DIST,
    TRAILING2_DESDE=real.TRAILING2_DESDE,
    TIME_STOP_MIN=real.TIME_STOP_MIN,     # C2
    BLOQUEO_MIN=real.BLOQUEO_SL_MIN,
    USE_CORTE_EMA7=True,
    COMM_RT=0.04,   # maker round-trip (0.02% x2) — ejecución ideal a comparar vs real
)

if __name__ == "__main__":
    PaperBot(CFG).run()
