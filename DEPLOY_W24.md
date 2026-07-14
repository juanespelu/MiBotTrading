# Runbook de deploy — Ciclo de aprendizaje W24 (cerebro nuevo en bot real)
**Fecha:** 4-jun-2026
**Estado:** ✅ DEPLOY EJECUTADO + DRY_RUN OK + **FRENADO**. ⛔ **NO está en vivo** — go-live gateado por Juan + cerebro.
**Path real del repo en VPS:** `/root/trading/MiBotTrading` (no `/root/MiBotTrading`).

---

## ✅ ESTADO EJECUTADO (5-jun ~05:14 UTC, vía SSH)
- **Método:** `scp` de los 4 archivos de código (NO git pull — el árbol del VPS tiene logs históricos modificados/sin trackear; git pull era riesgoso). `test_conexion.py` **NO** se deployó (ver abajo).
- **journald:** 1.7G → 162.9M; tope permanente `SystemMaxUse=200M` + `SystemMaxFileSize=20M` (backup en `journald.conf.bak_W24`).
- **Servicios:** `bot-simulador` retirado (stop+disable). `bot-real` **stop + disable** (no auto-arranca en reboot). `bot-campeon` y `bot-retador` **active + enabled** (paper, $25 c/u, escaneando datos reales OK).
- **DRY_RUN bot real:** corrido 1 vez (`BOT_DRY_RUN=1`, sin Telegram), datos+balance reales, cerebro V5 evaluando OK, **0 órdenes**. `estado_bot.json` limpio.
- **Backups:** `bot_maestro_v4.py.bak_W24`, `journald.conf.bak_W24`.

## ⛔ BLOQUEANTE para go-live — `.env` del VPS (acción de Juan)
El `.env` del VPS tiene la key vieja (`tXHYow…`); la que funciona (IP-autorizada) es la **hardcodeada hoy en `test_conexion.py`** (`c1Uhqsv…`). Por eso `test_conexion.py` NO se reemplazó (romperia el bot).
**Juan:** poné en `/root/trading/MiBotTrading/.env` los valores `BINANCE_API_KEY` y `BINANCE_SECRET_KEY` = los dos que están hardcodeados en el `test_conexion.py` ACTUAL del VPS. Avisá y se hace el swap del archivo (completa Fase 0 keys→.env).

## GO-LIVE (solo tras aprobación de Juan + cerebro)
1. (Si se aprobó keys→.env) Juan corrige `.env` → `scp test_conexion.py` nuevo.
2. Verificar Telegram en vivo (el dry-run no lo ejerció).
3. `sudo systemctl enable --now bot-real` ← **este es el paso que pone plata real. NO antes de aprobación.**

---
## (Referencia) Pasos originales del plan

Este archivo lista las acciones que **Juan corre en el VPS** (yo no tengo acceso) y el orden de despliegue. Las acciones de código ya están en el repo.

---

## ⚠️ Acción VPS #1 — Reconciliar el `.env` del VPS (credenciales)

**Contexto:** la key que el bot usa de verdad estaba **hardcodeada** en `test_conexion.py` (empieza `c1Uhqsv…`). El `.env` tenía OTRA key (`tXHYow…`) que el código nunca leía. Ahora `test_conexion.py` lee de `os.getenv` → **el `.env` del VPS debe tener la key en uso**, o al reiniciar el bot cambia de keypair y se rompe.

En el VPS, verificar que `.env` tenga EXACTAMENTE:
```
BINANCE_API_KEY=<VALOR_REAL_SOLO_EN_.env_DEL_VPS — NO commitear>
BINANCE_SECRET_KEY=<VALOR_REAL_SOLO_EN_.env_DEL_VPS — NO commitear>
```
Comando de chequeo (NO imprime el secreto entero):
```bash
grep BINANCE_API_KEY ~/MiBotTrading/.env | cut -c1-30
# Debe empezar:  BINANCE_API_KEY=c1Uhqsv
```
Si difiere, editar el `.env` del VPS con esos dos valores. (Las keys NO se regeneran esta sesión — se hará la próxima; cuenta chica, IP-locked.)

> Nota: el wrapper `start_bot_*.sh` ya exporta el `.env`; además `test_conexion.py` ahora trae un loader de `.env` propio, así que funciona aunque el wrapper no lo exporte.

---

## ⚠️ Acción VPS #2 — Capar journald (el `\r` infló el journal a 1.7 GB)

El fix de código (guard `isatty()`) evita que vuelva a pasar de acá en adelante. Para **recuperar el espacio ya ocupado** y poner un techo permanente:

**a) Recuperar espacio ahora (elegí uno o ambos):**
```bash
sudo journalctl --vacuum-size=200M     # deja como mucho 200 MB de journal
sudo journalctl --vacuum-time=7d        # borra entradas de más de 7 días
```

**b) Techo permanente** — editar `/etc/systemd/journald.conf`:
```ini
[Journal]
SystemMaxUse=200M
SystemMaxFileSize=20M
```
Aplicar:
```bash
sudo systemctl restart systemd-journald
```
Verificar:
```bash
journalctl --disk-usage     # debe reportar <= ~200M
```

> **Esto NO toca la data de trades.** Confirmado leyendo el código: `registrar_log()` escribe a **archivos** en `logs_real/` y `logs_simulador/`; el `\r` que infló el journal iba a **stdout** (capturado por journald), que es un sistema distinto. Los logs históricos del bot quedan intactos.

---

## Acción VPS #3 — Servicios systemd (3 procesos: real / campeón / retador)

El **sim viejo** (`bot_SNIPER_SIM.py`, multi-posición) **se retira**: detené y deshabilitá su servicio. El archivo y sus logs históricos (`logs_simulador/` W13–W23) **quedan intactos** (no borrar). En su lugar corre el **campeón** (1 posición, mismo cerebro que el real).

```bash
sudo systemctl stop bot-simulador && sudo systemctl disable bot-simulador   # retirar sim viejo
```

Crear wrappers (junto a los existentes `start_bot_*.sh`):
```bash
# start_bot_campeon.sh
#!/bin/bash
cd /root/MiBotTrading
export $(grep -v '^#' .env | xargs)
source venv/bin/activate
exec python bot_SNIPER_CAMPEON.py

# start_bot_retador.sh   (igual, pero exec python bot_SNIPER_RETADOR.py)
```
`chmod +x start_bot_campeon.sh start_bot_retador.sh`

Servicios `/etc/systemd/system/bot-campeon.service` (y `bot-retador.service` análogo):
```ini
[Unit]
Description=Bot SNIPER CAMPEON (paper, cerebro = real)
After=network.target
[Service]
Type=simple
WorkingDirectory=/root/MiBotTrading
ExecStart=/root/MiBotTrading/start_bot_campeon.sh
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-campeon bot-retador
```

---

## Orden de despliegue (cuando Fase 3 esté aprobada — NO antes)
1. `git pull` en el VPS.
2. Acción VPS #1 (.env), #2 (journald), #3 (servicios).
3. Reiniciar real: `sudo systemctl restart bot-real`.
4. Retirar sim viejo + arrancar campeón y retador (Acción #3).
5. Observar logs (`logs_real/`, `logs_campeon/`, `logs_retador/`) y Telegram las primeras horas.

## Fase 3 — VERIFICACIÓN sin plata real (correr en el VPS, antes de ir a vivo)

La API key es IP-locked al VPS → la verificación en vivo NO se puede hacer desde local (acá solo se validó compilación + lógica offline). En el VPS:

**1. Dry-run del bot real (datos reales, CERO órdenes):**
```bash
cd ~/MiBotTrading && export $(grep -v '^#' .env | xargs) && source venv/bin/activate
BOT_DRY_RUN=1 python bot_maestro_v4.py
```
Verificar en `logs_real/` y Telegram que:
- Arranca como "V5.0 (cerebro SIM + C1/C2/C3)".
- Los SCAN muestran `ATR_15M`, `BTC_suav`, filtros nuevos.
- Cuando hay señal: aparece `DRY_RUN entrada limit maker ...` y `DRY_RUN SL_REAL ...` (NO órdenes reales).
- Si dispara, registra `TRADE REAL | ... | net:...` al cerrar.
- Dejar correr un rato; confirmar que respeta 1 posición y los bloqueos.
- **Cortar con Ctrl-C.** Borrar `estado_bot.json` si el dry-run lo dejó "ocupado" antes de ir a vivo.

**2. Paper bots (campeón + retador) — corren reales (son paper, no necesitan dry-run):**
```bash
python bot_SNIPER_CAMPEON.py     # un rato, ver logs_campeon/ y estado_campeon.json
python bot_SNIPER_RETADOR.py     # un rato, ver logs_retador/
```
Confirmar SCAN/ENTRADA/TRADE en sus logs y que el campeón usa el mismo cerebro (mismos bloqueos que el real ante la misma señal).

**3. ⛔ FRENAR.** Avisar a Juan + cerebro. Revisión del build. **NO arrancar el real sin DRY_RUN hasta aprobación.**

Para ir a vivo (sólo tras aprobación): correr sin `BOT_DRY_RUN` (o `BOT_DRY_RUN=0`) vía el servicio systemd.

---

## Archivos del deploy W24
| Archivo | Rol |
|---------|-----|
| `bot_maestro_v4.py` (V5.0) | REAL — cerebro sim + C1/C2/C3, órdenes reales |
| `bot_SNIPER_CAMPEON.py` | CAMPEÓN paper — mismo cerebro que el real (control) |
| `bot_SNIPER_RETADOR.py` | RETADOR paper — misma entrada, gestión suelta |
| `paper_engine.py` | Motor paper compartido (campeón + retador) |
| `bot_SNIPER_SIM.py` | RETIRADO (queda por historial) |
| `estado_campeon.json` / `estado_retador.json` | Estado de cada paper bot |
| `logs_campeon/` `logs_retador/` | Logs separados (trades + scans semanales) |
