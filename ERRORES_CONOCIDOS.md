# ERRORES CONOCIDOS — MiBotTrading
## Registro de errores específicos de este proyecto — spec: decisión **#N65** (`UNIVERSO_NOTAS.md`)
## Nace: 14-jul-2026 (sesión 2026-07-13-C, Parte B paso 4 — los 7 errores fundacionales vienen VERBATIM del anexo del borrador del cerebro, verificados 7/7)

**Cómo se usa (#N65):** se lee **COMPLETO al arrancar cada sesión de trabajo** (protocolo §1). Al cierre de sesión se agregan los errores nuevos del día, organizados por subsistema. Si un error generó una conducta permanente ("jamás X" / "siempre Y") → se **PROPONE su graduación** a MIS REGLAS ESPECÍFICAS del `CLAUDE.md` (gate de Juan — el CLAUDE solo crece con aprobación). Si un error reapareció desde OTRO proyecto → gradúa al `CONTEXT` de rol del Trader (saber cruzado).

Los errores cruzados (ccxt margin calls, fetch_balance con cache, systemd con .env, SSH con heredocs, dependencias VPS) viven en el CONTEXT del Trader y aplican a cualquier futuro proyecto del rol. Aquí solo los específicos de MiBotTrading:

---

## Estado y persistencia (simulador/paper)

| Error | Causa raíz | Solución | Sesión |
|-------|-----------|----------|--------|
| Posición zombie en simulador (18 Mar) | json.dump fallaba silenciosamente al cerrar | `_guardar_estado_sim()` inmediato después de cada cierre | S1 (Mar) |
| Posición zombie al reiniciar simulador | Bot apagado con posiciones abiertas aplicaba precio actual a posición vieja | `sincronizar_simulador()` cierra posiciones al arrancar | S1 (Mar) |
| CIERRE_REINICIO infinito | `sincronizar_simulador()` en main loop reseteaba diariamente | Mover llamada solo al startup, no en el loop principal | S2 (Abr) |
| Balance simulador inflado por zombies | Posiciones zombie de sesiones apagadas distorsionaban el balance | Reset manual a $25 + sync al arrancar | S2 (Abr) |

## Logs y terminal

| Error | Causa raíz | Solución | Sesión |
|-------|-----------|----------|--------|
| Log arranque no registraba | `registrar_log` estaba después del sync que podía fallar | Mover llamada antes del sync | S1 (Mar) |
| Terminal spam por anotar_evento() | Print statements llenaban la terminal del bot | Comentar prints en `anotar_evento()` | S2 (Abr) |

## Binance / cuenta

| Error | Causa raíz | Solución | Sesión |
|-------|-----------|----------|--------|
| Error -4411 Binance (acuerdo TradFi) | Cuenta requería aceptar acuerdo TradFi en Binance | Alerta Telegram + pausa 300s para que Juan acepte | S1 (Mar) |

## Git / repositorio

| Error | Causa raíz | Solución | Sesión |
|-------|-----------|----------|--------|
| Patrón de `.gitignore` roto: `error_esp.txt` no se ignoraba | Comentario inline en la línea del patrón — git NO soporta comentarios a mitad de línea: el patrón queda literal (con el `#` y los espacios incluidos) y no matchea nada | Comentario SIEMPRE en línea propia; verificar cobertura con `git check-ignore -v <ruta>` | 2026-07-13-C (jul) |
