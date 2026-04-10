# SESSION LOG — MiBotTrading
## Registro técnico de sesiones de desarrollo

Este archivo es mantenido por Claude Code al final de cada sesión. Contiene el registro técnico de lo que se hizo, errores encontrados, soluciones aplicadas y lecciones aprendidas.

---

## Sesiones previas (12-20 de marzo de 2026)
*Nota: Estas sesiones se realizaron antes de la implementación del SESSION_LOG. Resumen consolidado del CONTEXT.md.*

### Lo que se construyó
- bot_maestro_v4.py — Bot real con órdenes en Binance
- especialista_v3.py — Análisis técnico multi-TF para bot real
- bot_SNIPER_SIM.py — Simulador paper trading
- especialista_SNIPER.py — Análisis técnico para simulador
- Sistema de logs separados (trades nunca rota, scans rota semanal)
- Trailing escalonado 4 niveles en bot real
- BTC multi-TF completo (1M/5M/15M) en especialista_v3.py
- 49 trades reales analizados estadísticamente

### Errores resueltos
- ccxt ssymbol/timesttamp → upgrade + fetchMarkets:['linear']
- sapi/v1/margin calls → fetchMarkets:['linear']
- fetch_balance mataba scans → aislado con try/except + cache
- Posición zombie en simulador → _guardar_estado_sim() inmediato
- Log arranque no registraba → movido antes del sync
- Error -4411 TradFi → alerta Telegram + pausa 300s

### Decisiones técnicas clave
- SL -1.00% real vs -0.85% simulador
- T1 0.35% real vs 0.25% simulador
- btc_trend_suav (N=5) en bot real vs btc_trend directo en simulador
- Logs separados: trades = histórico valioso, scans = volumen alto rotar semanal
- Funding bloquea solo ESTANDAR, no SNIPER

---

## Sesión 1 — 29 de marzo de 2026
### Archivos creados
- historial/bots/ — Nueva carpeta para bots obsoletos
- historial/logs_desarrollo/ — Nueva carpeta para logs de desarrollo

### Archivos modificados
- bot_maestro_v4.py — Implementada función actualizar_balance() con throttle 60s para evitar spam en logs cuando fetch_balance falla
- bot_SNIPER_SIM.py — Implementada función sincronizar_simulador() para cerrar posiciones ficticias al reiniciar + agregada importación de exchange

### Errores encontrados y soluciones
- Ningún error nuevo encontrado. Los cambios implementados resuelven problemas conocidos:
  - Spam de logs fetch_balance: resuelto con throttle 60s
  - Posiciones ficticias al reiniciar simulador: resuelto con sincronización al arranque

### Decisiones técnicas
- Reorganización de archivos: movidos archivos obsoletos a historial/bots/ e historial/logs_desarrollo/ sin borrar nada
- Conservación de estructura logs_real/ y logs_simulador/ sin modificaciones
- Implementación de throttle de 60s para fetch_balance mantiene operatividad con menos ruido en logs
- Sincronización automática del simulador garantiza P&L realista después de reiniciar

### Notas para la próxima sesión
- Ambos bots listos para operar con los fixes implementados
- Estructura de archivos reorganizada y limpia
- Inventario completo disponible para futuras referencias
- Pendiente migración a VPS para operación 24/7 (no relacionado con esta sesión)

---

*A partir de aquí, cada sesión nueva se documenta con el formato completo.*
*Este archivo se actualiza automáticamente al final de cada sesión. Claude Code es responsable de mantenerlo.*