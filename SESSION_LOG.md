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

## Sesión 2 — MiBotTrading — 10 de abril de 2026
### Archivos creados
- .gitignore — Protección de archivos sensibles (.env, venv/, logs grandes)
- start_bot_real.sh — Script wrapper para cargar .env en systemd 
- start_bot_simulador.sh — Script wrapper para cargar .env en systemd
- /etc/systemd/system/bot-real.service — Servicio systemd para bot real
- /etc/systemd/system/bot-simulador.service — Servicio systemd para simulador
- GitHub repo privado: https://github.com/juanespelu/MiBotTrading.git

### Archivos modificados
- bot_SNIPER_SIM.py — Fix CIERRE_REINICIO (movido sincronizar_simulador), Telegram completo, limpieza terminal
- bot_maestro_v4.py — Variables de entorno con os.getenv para VPS
- estado_sniper_sim.json — Reset balance a $25 USDT
- .env — Creación en VPS con todas las variables

### Errores encontrados y soluciones
- **CIERRE_REINICIO infinito**: sincronizar_simulador() en main loop causaba reset diario infinito. Solución: moverlo solo al startup
- **Terminal spam anotar_evento()**: print statements llenaban terminal. Solución: comentar prints en anotar_evento()  
- **Variables .env en systemd**: systemd no carga .env automáticamente. Solución: scripts wrapper con export $(cat .env)
- **Binance IP restriction**: VPS IP 45.151.122.181 no autorizada. Solución: agregar IP en Binance API Management
- **Dependencias faltantes**: pandas/numpy/TA-Lib no instalados en VPS. Solución: pip install en venv

### Decisiones técnicas
- **Migración completa al VPS Contabo**: Bot Real + Simulador operando 24/7 con systemd auto-restart
- **Scripts wrapper**: Método elegido vs variables directas en systemd por limpieza y mantenibilidad
- **Servicios systemd**: ExecStart apunta a scripts wrapper que cargan .env y activan venv
- **GitHub privado**: Todo el código subido para backup y versionado
- **Credenciales seguras**: .env excluido de git, variables cargadas dinámicamente

### Aprendizajes
- **systemd + .env**: systemd no soporta archivos .env nativamente, requiere scripts wrapper o variables explícitas
- **SSH + comandos largos**: Heredocs y comandos Python multilinea se rompen al pegar. Usar echo línea por línea
- **Migración VPS**: IP debe agregarse a Binance antes de ejecutar bots para evitar restricciones API
- **Dependencias Python**: Verificar módulos antes de crear servicios systemd para evitar fails al startup

### Notas para la próxima sesión  
- **Sistema completamente operativo**: Ambos bots corriendo 24/7 en VPS con auto-restart
- **Monitoreo recomendado**: Revisar logs y funcionamiento las primeras 24-48 horas
- **Código sincronizado**: Cambios locales deben pushearse a GitHub y desplegarse en VPS
- **IP fija registrada**: VPS IP 45.151.122.181 agregada en Binance API Management

---

*A partir de aquí, cada sesión nueva se documenta con el formato completo.*
*Este archivo se actualiza automáticamente al final de cada sesión. Claude Code es responsable de mantenerlo.*

---

## Sesión — 4 de junio de 2026 (ciclo completo: análisis → transplante V5.0 → deploy → go-live)

Sesión larga. Cadena: migración SSH → análisis de estrategia (496 trades) → bug F2 → transplante de cerebro V5.0 + 3 bots → deploy al VPS → go-live → fix de Telegram → en vivo confirmado.

### 0. Infra — Migración de acceso al VPS a LLAVE SSH (al inicio de la sesión)
- Se generó una llave **ed25519 sin passphrase** en la máquina local.
- VPS endurecido a **solo-llave**: `PasswordAuthentication no` vía drop-in **`/etc/ssh/sshd_config.d/00-hardening.conf`**.
- **Backup** del config original: **`/etc/ssh/sshd_config.bak_20260604_210332`**.
- Acceso ahora: `ssh root@45.151.122.181` (sin contraseña). **Respaldo anti-lockout: consola web de Contabo.**
- Repo en el VPS: **`/root/trading/MiBotTrading`** (no `/root/MiBotTrading`).

### 1. Análisis de estrategia (496 trades sim, W15→W23) — `analisis/ANALISIS_ESTRATEGIA.md`
- PnL ground-truth desde `balance_acumulado`; todo NETO (comisión taker 0.10% + funding); validación OOS por tiempo; régimen marcado (2 meses bajista).
- **Hallazgo central:** en bruto la estrategia es plana (−0.01%/trade); **neta pierde −54.4pp / −42% compuesto, y la comisión es el 91% de la pérdida** (sobre-operar). OOS estable (las 9 semanas negativas).
- El mercado SÍ se movió (rango diario 3.76%, 67/114 días con corridas >1%) pero la correlación con el neto del bot es 0.13 → **la estrategia no captura la tendencia** (T1 diminuto + EMA7 + reentradas).
- Cortes (CORTE_EMA7/STOP_LOSS) mayormente aciertan; CORTE_EMA7 es buen guardián; ningún cambio de stop vuelve positivo. Trailing casi irrelevante en bajista (el "ATR×0.5" era sobreajuste a 18 trades).
- Filtros = buenos guardianes (bloquean perdedoras). K<45 ahorra por selectividad, no por edge.
- **Correcciones validadas (paquete R2):** C1 piso `ATR_15m≥0.45`, C2 time-stop 45min, C3 entradas LIMIT maker. R2 → ≈ breakeven (test OOS +2.7pp). Breakeven en bajista es buen resultado.

### 2. Bug F2 (filtro K15m) en el sim viejo
- `bot_SNIPER_SIM.py` leía `k_mayor_d_15m` / `k_d_diff_15m`, pero el especialista devuelve `k_15m_mayor_d` y NO devuelve `k_d_diff_15m` → defaults → `pasa_k15m` SIEMPRE True → **F2 nunca filtró (no-op)**. No invalida el análisis (los 496 son lo que el sim operó; F2 nunca apareció como bloqueador). El V5/campeón usan `especialista_v3` con claves correctas → **F2 ahora funciona** (decisión: dejarlo ON; efecto casi neutro, K no separa).

### 3. Transplante de cerebro V5.0 + 3 bots
- **`bot_maestro_v4.py` → V5.0 (REAL):** cuerpo intacto (órdenes reales, SL real stop_market, sync, 1 posición). Cerebro del sim (sin K<45, **BTC_suav**) + params sim (STOP −0.85, BE 0.15, T1 0.25, trailing 2 niveles) + **C1** (ATR15m≥0.45) + **C2** (time-stop 45min) + **C3** (LIMIT post-only al mejor bid, timeout 60s, NO_FILL descarta). Instrumentación: intentado vs llenado, slippage, comisión real, registro `TRADE REAL` completo, alerta por-trade, resumen diario combinado + fill-rate, heartbeat→1/día. Modo **`BOT_DRY_RUN=1`** (datos reales, cero órdenes).
- **`paper_engine.py`** (motor paper) + **`bot_SNIPER_CAMPEON.py`** (cerebro idéntico al real por importación; comisión maker; control del Δ ejecución) + **`bot_SNIPER_RETADOR.py`** (misma entrada, gestión suelta: T1 0.50, sin corte EMA7, dejar correr). Los 3: 1 posición, logs separados.
- `bot_SNIPER_SIM.py` **retirado** (servicio detenido; archivo + logs históricos intactos).

### 4. Fases 0–2 (build) + verificación offline
- **Fase 0:** `test_conexion.py` lee de `.env` (loader propio, sin hardcode); fix del **`\r`** con `isatty()` en real y sim (el `\r` inflaba el journal del VPS a 1.7G); runbook **`DEPLOY_W24.md`**.
- Verificado offline: los archivos compilan; campeón.params == real.params; C1/F1/F2/F3/F5 bloquean OK; `registrar_trade_real` da net correcto. **Lección:** un test escribió en `logs_real/log_trades_real.txt` (histórico) — se restauró bit-a-bit con `git checkout`. Nunca apuntar tests a rutas de logs reales.

### 5. Deploy al VPS (por SSH) + go-live
- Método **scp** (no `git pull`: el árbol del VPS tiene logs históricos modificados). Backups: `bot_maestro_v4.py.bak_W24`, `test_conexion.py.bak_W24`, `journald.conf.bak_W24`.
- **journald:** 1.7G → 162.9M, tope permanente `SystemMaxUse=200M`.
- Servicios: sim viejo retirado; **bot-campeon + bot-retador** active (paper, $25 c/u); **DRY_RUN** del real OK (datos+balance reales, 0 órdenes).
- **`.env` del VPS:** tenía la key vieja (`tXHYow…`); Juan la corrigió a la que funciona (`c1Uhqsv…`). Swap de `test_conexion.py` → **conexión a Binance EXITOSA, balance $22.10**.
- **Go-live:** Juan corrió `systemctl enable --now bot-real`. Bot V5.0 en vivo.

### 6. Fix de Telegram (Markdown / guiones bajos)
- Síntoma: no llegó el "Bot V5.0 Online". **Causa raíz:** `enviar_telegram` usaba `parse_mode: Markdown`; los nombres con **guion bajo** (`BE_STOP`, `RETROCESO_BE`, `CORTE_EMA7`, `STOP_LOSS`, `TIME_STOP`, `CIERRE_TRAILING`) rompían el Markdown → Telegram rechazaba el mensaje y el error se tragaba en silencio. **Afectaba las alertas por-trade de cierre** (bug latente desde V4). 
- **Fix:** `enviar_telegram` ahora en **texto plano** (sin `parse_mode`, con `.replace('*','')`) → entrega garantizada. Verificado: `RETROCESO_BE` entrega `ok:True`.
- Description del servicio actualizada V4.0 → V5.0. **Reinicio** de `bot-real` (sin posición → seguro) → arranque fresco V5.0, "Online" enviado con el código fixeado.

### Estado final
- **bot-real V5.0: en vivo, sano** (CPU ~3.6%), conectado a Binance (balance $22.10), escaneando con cerebro V5, `estado_bot.json` limpio, Telegram OK (online + por-trade + resumen diario).
- bot-campeon + bot-retador: paper, activos.
- bot-simulador: retirado.

### Pendientes / notas para próxima sesión
- **Ciclo de aprendizaje 2 semanas:** medir expectativa neta real vs baseline sim (−0.110%/trade), **tasa de fill de las limit (C3)**, Δ real-vs-campeón, drawdown/racha. Éxito = real≈sim + cerca de breakeven (NO "ganó plata"; es deploy para aprender, ~$20).
- **Rotar las API keys de Binance** la próxima sesión (estuvieron hardcodeadas/en git; esta sesión no se rotaron por ser cuenta chica + IP-lock).
- `DEPLOY_W24.md` quedó con el estado ejecutado + el GO-LIVE y las acciones del VPS.
- Los docs de estado (CONTEXT proyecto/especialista, MAESTRO, UNIVERSO_NOTAS) los actualiza **el cerebro** (no Claude Code).

---

## Sesión — 13 de julio de 2026 — Bitácora **2026-07-13-C** (puesta al día documental + respaldo — transición del Universo, Parte 2 paso 13)

**SESIÓN EN CURSO.** Última pieza de la transición del Universo (7→12-jul): este territorio se actualizó A PROPÓSITO al final, en sesión propia, por manejar dinero real. **Alcance acordado: SOLO documental y respaldo** — NO se toca estrategia, ni parámetros, ni el bot vivo del VPS (esta carpeta local no lo afecta), ni `.env`. Acta canónica: la escribe el cerebro en su ventana (acta única, mismo ID); acá va el detalle técnico. Todo cambio con gate de Juan.

### PARTE A — Renacimiento ✅ HECHA (gate de Juan aprobado)

1. **`CLAUDE.md` reemplazado** por el borrador aprobado (`../el-universo/historial-legado/transicion-2026-07/auditoria/CLAUDE_MiBotTrading_PROPUESTO.md`, redactado por el cerebro 11-jul), header con fecha real 13-jul-2026:
   - El protocolo ya NO vive copiado acá: se **hereda por import** (`@../el-universo/cerebro/PROTOCOLO_SESION.md` + `@../el-universo/especialistas/trader/PERFIL.md`).
   - Mueren las 3 rutas absolutas rotas (`Desktop\el-universo\...`) y la descripción vieja "V4.0 + Simulador V7.5" (estado en documentos de reglas: nunca más).
   - Reglas de seguridad (dinero real) y operativas conservadas VERBATIM, con 2 micro-ajustes aprobados por Juan: "simulador" → "simulador/paper" (realidad post-W24).
   - Secciones nuevas: MI TERRITORIO · LO QUE NUNCA HAGO · regla `MBT-L#` · puntero a `ERRORES_CONOCIDOS.md` con graduación (#N65) · CUÁNDO LEO QUÉ.
   - **Respaldo del CLAUDE saliente (27-may, nunca commiteado):** `historial/CLAUDE_2026-07-13_2357.md` (hash verificado idéntico). Si Juan lo considera redundante, se descarta en la revisión del commit (Parte B).
2. **`.claude/settings.json` creado** (no existía; `settings.local.json` intacto): `additionalDirectories: ["../el-universo"]` + hook `SessionStart:compact` de re-anclaje (C.5-ter).
3. **Verificaciones previas al reemplazo:** anexo del borrador = 7/7 errores, comparados fila a fila contra la tabla del CLAUDE viejo → idénticos · los 2 imports resuelven a archivos existentes · `.claude/settings.json` no existía.

**→ PARTE A HECHA, SIGUE PARTE B.** Juan reinicia la ventana: renazco con el CLAUDE nuevo + protocolo heredado + settings puestos. Este LOG es mi continuidad.

### PARTE B — PENDIENTE (todo con gate de Juan a la vista)

4. **`ERRORES_CONOCIDOS.md`** (nace — #N65): los 7 errores del anexo del borrador VERBATIM, organizados por subsistema, header con puntero a la spec #N65. Verificar conteo 7/7 contra el anexo.
5. **Fix §6 del CONTEXT de rol** (`../el-universo/especialistas/trader/CONTEXT.md`): la tabla "MCPs disponibles (globales): GitHub, Vercel" es FALSA (#N54) — no hay MCPs globales; GitHub va por git CLI directo; no hay MCP de exchange (Binance va por ccxt en el código). Método #N51: leerlo COMPLETO antes de tocar.
6. **Decisiones locales `MBT-L#`**: numerar con Juan las decisiones de CONTEXT.md §14 como MBT-L1, MBT-L2… (viven en el CONTEXT; la bitácora canónica las enlaza; jamás compiten con las #N).
7. **README ❄️ en `historial/`**: igual al de los otros 7 historiales congelados (referencia: `../el-universo/cerebro/historial/README_CONGELADO.md`).
8. **EL COMMIT DE PUESTA AL DÍA** (corazón de la sesión): `git status` completo a la vista de Juan → revisar los ~28 archivos sin trackear UNO POR UNO antes de agregar (⛔ verificar que `.gitignore` proteja `.env` y que NINGÚN secreto/llave entre — regla 9) → gate → commit → proponer esquema de tags contra el historial real (estado actual como v5.0.0; retroactivos solo donde existan commits que los soporten — OJO: el repo tiene UN solo commit, `bafaec9` "Initial commit: MiBotTrading V4.0") → gate → push.
9. **Cierre por el protocolo nuevo** (§6, los 8 pasos, checklist a la vista): LOG completo · CONTEXT del proyecto verificado (soy su escritor primario — #N66) · destilado al CONTEXT de rol (declarar N aprendizajes aunque N=0) · reporte final con el checklist visible, jamás un "listo" opaco.

**Reglas innegociables de la sesión:** dinero real ⛔ (API keys/secretos/parámetros: ni tocarlos) · el bot vivo del VPS no se toca (ni deploys ni systemd) · nada de análisis de estrategia (si aparece la tentación: se anota y se agenda aparte) · secretos jamás en un documento ni en git.

### PARTE B — avance (continuación 14-jul-2026, misma bitácora 2026-07-13-C)

**Hito B.1 — piezas documentales creadas (a la vista de Juan en la revisión del commit):**
- **Paso 4 ✅ `ERRORES_CONOCIDOS.md` NACE (#N65):** los 7 errores del anexo del borrador VERBATIM, organizados en 3 subsistemas (Estado y persistencia ×4 · Logs y terminal ×2 · Binance/cuenta ×1). Conteo verificado **7/7** contra el anexo. Header con la spec #N65 (lectura COMPLETA al arrancar cada sesión; graduación a reglas solo con gate; errores cruzados → CONTEXT de rol).
- **Paso 5 ✅ Fix §6 del CONTEXT de rol** (`../el-universo/especialistas/trader/CONTEXT.md`): leído COMPLETO antes de tocar (#N51). La tabla falsa "MCPs disponibles (globales): GitHub, Vercel" reemplazada por la realidad (#N54): no hay MCPs globales; GitHub va por git CLI directo; sin MCP de exchange (Binance vía ccxt en el código). Header actualizado conservando la referencia W24. El repo `el-universo` queda con este cambio para el commit del cerebro (acta única / territorio).
- **Paso 7 ✅ `historial/README_CONGELADO.md` creado:** texto de referencia (`cerebro/historial/README_CONGELADO.md`) adaptado mínimamente a este historial (bots viejos, logs de desarrollo, copias timestamped de CONTEXT/CLAUDE), fecha 14-jul y paso 13.
- **Paso 6 ⏳ MBT-L#:** propuesta de numeración presentada a Juan (gate pendiente).
- **Paso 8 ⏳ Commit de puesta al día:** git status + barrido de secretos preparados; revisión archivo por archivo con Juan pendiente.

**Hito B.2 — pre-chequeo de seguridad del commit (paso 8, regla 9) — TODO VERDE:**
- `.env` ignorado por git (check-ignore ✓ vía `.gitignore:3 *.env`). El tarball del extract VPS **NO contiene `.env`** (tar -tzf ✓: solo logs + estados JSON + logs de runtime).
- **Cero secretos hardcodeados en `*.py`** (grep de patrones clave=valor-largo: 0 matches). `test_conexion.py` leído completo: credenciales 100% desde entorno con loader `.env` local, aborta si faltan.
- Menciones `tXHYow…`/`c1Uhqsv…` en `SESSION_LOG.md` y `DEPLOY_W24.md`: verificado con grep -o que son **solo prefijos truncados de 6-7 chars** (identificación, no valores) — dentro de la regla de secretos.
- Strings largos en logs (`log_trades_real.txt` local ya trackeado desde abril + copia VPS + `log_mejora_bot.txt`): son **firmas HMAC por-request** en URLs logueadas, NO API keys. Ojo: la key vieja completa sí vive en la **historia** de git (bafaec9, test_conexion.py de abril, ya pusheado a GitHub privado desde entonces) → refuerza la **rotación de keys pendiente** (agendada, sesión aparte).
- Hallazgos de higiene: (a) línea `error_esp.txt` del `.gitignore` **ROTA por comentario inline** (git no los soporta → el patrón no matchea nada); (b) `analisis_VPS_2026-06-04/` pesa **2.1 GB** (~20 archivos >20MB — inviable para GitHub, límite 100MB/archivo) y `analisis/datasets/` **171 MB** de parquets derivados regenerables; (c) log W15 local modificado: +8 scans del 9-abr 23:00 (el bot local siguió escaneando ~30 min tras el commit inicial — **solo agrega**, histórico intacto ✓); (d) `.claude/` ignorado entero → el `settings.json` del renacimiento quedaría solo-local (decisión para Juan).
- Propuestas presentadas a Juan (gates): contenido del commit (8 modificados + 39 nuevos, exclusiones vía .gitignore), settings.json versionado sí/no, tags v4.0.0 retro + v5.0.0 + push, esquema MBT-L#.

**Hito B.3 — los 4 gates de Juan APROBADOS (opción recomendada en los 4) + aplicación:**
- Gate commit ✓ (tal cual: 8 modificados + ~40 nuevos revisados, exclusiones, fix .gitignore) · Gate settings ✓ (versionar `.claude/settings.json` — verificado sin secretos: solo additionalDirectories + hook re-anclaje) · Gate tags/push ✓ (v4.0.0 retro en bafaec9 + v5.0.0 + push) · Gate MBT-L# ✓ (L1–L29 en orden de tabla + marcas `→` en L12/L13/L14).
- Aplicado: CONTEXT §14 numerado **MBT-L1–L29** con intro de convención (numeración estable, jamás se renumera, `→` = no se aplica) y 3 marcas `→` · CONTEXT header + §2 (+`ERRORES_CONOCIDOS.md`, +`analisis/`, +extract VPS como NO-git) + §12 (entrada de la sesión) · `ERRORES_CONOCIDOS.md` +1 error nuevo (Git/repositorio: patrón roto por comentario inline) · **destilado al CONTEXT de rol: 3 aprendizajes** (gitignore inline rompe patrón · barrido pre-commit de secretos en 4 pasos · límite GitHub 100MB) · `.gitignore` arreglado y ampliado (línea rota → línea propia; +`analisis_VPS_2026-06-04/` +`analisis/datasets/`; `.claude/*` con excepción `!settings.json`).

### CIERRE de la continuación 14-jul (protocolo §6 — checklist)
1. **SESSION_LOG completo ✓** — esta entrada; hitos B.1/B.2/B.3 escritos al momento, no al final.
2. **CONTEXT del proyecto verificado ✓** — refleja el estado final del día (header, §2, §12, §14). El estado del BOT no cambió: no se tocó ni el VPS ni un parámetro.
3. **Destilado al CONTEXT de rol ✓ — N=3 aprendizajes** (transferibles a cualquier proyecto del rol).
4. **ERRORES_CONOCIDOS.md ✓** — +1 error del día (Git/repositorio). Graduación al CLAUDE: no aplica (es dato técnico cruzado → destilado al rol; no nace conducta de proyecto nueva).
5. **INFORME_TECNICO:** no existe en proyectos del Trader (PERFIL: el CONTEXT es exhaustivo) — no aplica.
6. **INFRAESTRUCTURA.md:** sin cambios de infra (VPS intocado) — no aplica.
7. **Git:** commit único de puesta al día → tag **v4.0.0** (retroactivo, bafaec9) + **v5.0.0** (el commit nuevo) → push a GitHub privado. Resultado confirmado en el reporte de cierre del chat; si algo falla, se AGREGA acá la corrección. "Build": py_compile de los .py como equivalente local (el código real corre vivo e intacto en el VPS desde el 5-jun).
8. **Reporte de cierre con checklist a la vista → en el chat.** El acta canónica la escribe el cerebro (acta única, ID 2026-07-13-C); este LOG es el detalle técnico federado.

---

## Sesión — 15 de julio de 2026 — Bitácora **2026-07-15-E** (la herencia real: #N71 + #N72 — documental + settings; el bot NO se tocó)

**Alcance acordado:** documental + `.claude/settings.json` — NADA del bot vivo, NADA de estrategia, CERO secretos (la rotación de las keys de Binance sigue agendada para su sesión dedicada). Acta canónica: la escribe el cerebro (acta única — sesión con cerebro abierto); acá el detalle técnico federado.

**El porqué (las dos leyes del día, llegadas del cerebro):**
- **#N72 — la herencia real:** el catch del Programador (test conductual del día — de los grandes) destapó que los `@import` con `../` de los CLAUDEs de las islas NO expanden: fallan EN SILENCIO. **Confirmado en carne propia en este arranque:** las líneas `@../...` de mi CLAUDE llegaron como texto literal; ni el PROTOCOLO ni mi PERFIL estaban en mi contexto (los leí a mano para esta sesión). Mi blindaje local sostuvo el territorio desde el 13-jul. Detalle canónico: `el-universo/ERRORES_CONOCIDOS.md` (nació hoy).
- **#N71 — el CREDO:** en sesiones largas las reglas pierden saliencia; nace `CREDO.md` (destilado de las reglas de sangre) inyectado a CADA turno por hook `UserPromptSubmit`, al final del contexto, donde la atención es máxima.

### Cambios aplicados (paquete aprobado por Juan, pieza por pieza)
1. **`CLAUDE.md` — cirugía:** retiradas las 2 líneas `@../el-universo/...`; el párrafo en cursiva reemplazado por la anatomía nueva (PROTOCOLO+PERFIL inyectados por SessionStart, CREDO por turno, los CONTEXT se LEEN); bump del header (15-jul, #N71+#N72). **+1 fix de integridad (§9: referencia muerta que dejaba la cirugía):** en MI TERRITORIO, "(heredados arriba)" apuntaba a los imports retirados → "(inyectados por hook SessionStart — #N72)".
2. **`.claude/settings.json`:** entrada `SessionStart` SIN matcher (inyecta PROTOCOLO+PERFIL vía `chcp 65001 >nul & type ...` — comando PLANO: lección del día, jamás `cmd /c` anidado) antes del bloque `compact` (conservado INTACTO) + evento `UserPromptSubmit` nuevo (inyecta `CREDO.md`). JSON validado ✓.
3. **`CREDO.md` NACE (#N71):** texto aprobado por Juan VERBATIM — línea de gobernanza + 7 puntos + checkpoint. Cero números que envejecen adentro ✓ (nace por decisión: no es deriva de catálogo).
4. **`.claude/commands/cierre.md` NACE:** `/cierre` fuerza la RELECTURA del §6 en su única casa y lo corre a la vista — jamás copia los pasos (#N36).
5. **`.gitignore`:** `+!.claude/commands/` (el `!.claude/settings.json` ya estaba de la 13-C; la base `.claude/*` con asterisco es la forma que permite excepciones ✓).

### Verificaciones (efecto observable, no intención — regla 12 del rol)
- JSON de settings parseado OK: 2 entradas `SessionStart` (sin-matcher + compact) · 1 `UserPromptSubmit`.
- Smoke test del comando EXACTO de cada hook (vía cmd, cwd del proyecto): SessionStart → exit 0, 234 líneas, PROTOCOLO completo (incluye §6) + PERFIL concatenados, UTF-8 correcto; UserPromptSubmit → exit 0, CREDO íntegro (emoji ⚓ y #N70 presentes).
- `git check-ignore` del grupo: solo `settings.local.json` sigue ignorado; `settings.json`, `commands/cierre.md` y `CREDO.md` entran al repo ✓.
- **Pendiente estructural (lección del día): la verificación REAL de la herencia va en el PRÓXIMO arranque — confirmar PROTOCOLO+PERFIL contenido-EN-contexto, jamás ruta-existe.** Los hooks nuevos cargan recién en sesión nueva; el smoke de hoy solo garantiza que el comando no está roto.

### Observaciones cacheadas (reportadas a Juan en el chat)
- El hook `compact` heredado dice "relee el PROTOCOLO_SESION **heredado**" — palabra vieja (ahora es *inyectado*). Se dejó INTACTO como pidió el paquete (además: los edits a hooks no recargan en caliente). Ajuste candidato para otra sesión, no urgente — y de yapa: la entrada sin matcher también corre en compact, así que el protocolo llega FRESCO justo antes del aviso de re-anclaje; se refuerzan.
- El ID **E** del día ya aparece en `el-universo/ERRORES_CONOCIDOS.md` ligado al test del Programador → se asume que E es el EVENTO del día (rollout de la herencia real) y cubre a los especialistas en paralelo (acta única). Si me tocaba otra letra, corregir acá.
- El header de mi CLAUDE decía desde el 13-jul "el protocolo se HEREDA vía import" — estuvo 2 días describiendo una herencia que nunca operó; el bump de hoy lo deja honesto.

### Cierre §6 (checklist RELEÍDO del PROTOCOLO — sesión documental, sin build/tag: no se tocó código)
1. **SESSION_LOG completo ✓** — esta entrada (abre con el ID de bitácora).
2. **CONTEXT del proyecto verificado ✓** — header + §2 (CREDO.md, `.claude/`) + §12 (entrada de la sesión) al día; el estado del BOT no cambió (ni VPS, ni parámetros, ni `.env`).
3. **Destilado al CONTEXT de rol ✓ — N=1 aprendizaje:** herencia inter-repo por hook (jamás `@import` con `../`; comando plano en Windows; hooks editados no recargan en caliente; verificación = contenido-en-contexto en sesión fresca).
4. **ERRORES_CONOCIDOS.md del proyecto — 0 errores nuevos DEL PROYECTO:** el error del día es de PLATAFORMA y su casa canónica es `el-universo/ERRORES_CONOCIDOS.md` (nació hoy allá, escrito por el cerebro); el saber cruzado quedó destilado al CONTEXT de rol (micro-test 2 del router). Graduación al CLAUDE: no aplica (la conducta nueva ya quedó instalada por el propio paquete #N71/#N72).
5. **INFORME_TECNICO** — no existe en proyectos del Trader (el CONTEXT es exhaustivo, PERFIL): no aplica.
6. **INFRAESTRUCTURA.md** — sin cambios de infra (VPS intocado): no aplica.
7. **Git:** commit documental de las 6 piezas (CLAUDE, settings, CREDO, cierre.md, .gitignore, CONTEXT+LOG) → status limpio · build/tag: N/A (sin código) · **push: GATE DE JUAN pendiente** (se pregunta en el chat). El fix del CONTEXT de rol queda en el repo `el-universo` para el commit del cerebro (acta única / territorio). Resultado del commit confirmado en el reporte del chat; si algo falla, se AGREGA acá la corrección.
8. **Confirmación con el checklist a la vista → en el chat**, incluyendo "CONTEXT al día ✓".