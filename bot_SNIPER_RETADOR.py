"""
bot_SNIPER_RETADOR.py — Paper bot RETADOR ("más aire"), W24.

MISMA entrada que el real/campeón (importa el filtro), pero gestión de salida
más suelta: T1 más alto, trailing más ancho, SIN corte EMA7 rápido y SIN
time-stop → deja correr para juntar datos sobre montar tendencias de cara a un
cambio de régimen (analisis/ANALISIS_ESTRATEGIA.md, Bloque 4: el trailing es la
dimensión más dependiente del régimen). Solo paper, NO toca el real ni el campeón.
"""
import bot_maestro_v4 as real
from paper_engine import PaperBot

CFG = dict(
    name="RETADOR",
    state_file="estado_retador.json",
    logs_dir="logs_retador",
    trades_file="trades_retador.txt",
    # MISMA entrada que el real/campeón (incl C1) — solo cambia la gestión de salida
    evaluar=real.evaluar_filtros_sniper,
    # Gestión "más aire": dejar correr
    T1_TARGET=0.50,          # T1 más alto (vs 0.25)
    BE_TRIGGER=0.15,
    BE_STOP=0.10,
    STOP_LOSS=-0.85,
    SUELO_POST_T1=0.30,
    TRAILING_DIST=0.30,      # trailing base más suelto
    TRAILING2_DIST=0.20,
    TRAILING2_DESDE=0.80,    # aprieta mucho más tarde
    TIME_STOP_MIN=None,      # sin time-stop — dejar correr
    BLOQUEO_MIN=real.BLOQUEO_SL_MIN,
    USE_CORTE_EMA7=False,    # NO cortar rápido en EMA7 — dejar correr
    COMM_RT=0.04,
)

if __name__ == "__main__":
    PaperBot(CFG).run()
