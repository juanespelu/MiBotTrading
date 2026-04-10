# CONTEXTO DEL PROYECTO — Bots de Trading Binance Futures
**Última actualización:** 29 de marzo de 2026 — Sesión tarde
**Estado:** ✅ Ambos bots corriendo estables en PC local (Windows / VS Code / entorno virtual Python) | VPS Contabo en proceso de activación

---

## 1. VISIÓN Y META

### Visión
El objetivo es generar la mayor rentabilidad posible, en el menor tiempo posible — pero siempre ajustada al riesgo.

No se trata de disparar más trades sino de disparar los correctos. Cada decisión debe tener una razón técnica sólida, un riesgo controlado, y una expectativa matemática positiva demostrada con datos reales.

El camino hacia eso es un bot completamente autónomo que aprende de sus propios resultados, mejora con cada trade sin intervención manual, y opera 24/7 con disciplina profesional — sin emociones, sin excepciones, sin improvisar.

### Hoja de ruta
- **Fase 1 (ahora):** 200+ trades reales con contexto técnico completo — la base de datos de la que aprenderá todo lo demás
- **Fase 2:** Clasificador supervisado — solo entra cuando la probabilidad de éxito es alta y el riesgo está justificado
- **Fase 3:** Parámetros adaptativos — SL, T1 y trailing se ajustan automáticamente según las condiciones del mercado
- **Fase 4:** Agente RL autónomo — descubre y optimiza estrategias completas desde la experiencia acumulada

### Estado actual del sistema
Sistema de trading algorítmico para Binance Futures Perpetuos (USDT-M) compuesto por dos bots que corren en paralelo:

- **Bot Real (V4.0):** Ejecuta órdenes reales con dinero. Capital actual ~$22.65 USDT. Sin apalancamiento adicional (1x efectivo). Maneja **una sola posición a la vez**.
- **Simulador (V7.5):** Paper trading con precios reales del mercado. Balance simulado ~$17.41 USDT (ajustado tras cierre de posiciones zombie de 95h). Puede tener **múltiples posiciones abiertas simultáneamente** (una por símbolo).

**Infraestructura actual:** PC local Windows, VS Code, entorno virtual Python. VPS Contabo Cloud 20 ($8.39/mes, 6 vCPU / 12GB RAM / Ubuntu 24.04) **ordenado — pendiente activación** (1-3 días hábiles tras confirmación de pago).

---

## 2. ARCHIVOS DEL PROYECTO

```
bot_maestro_v4.py         — Bot real (lógica + ejecución de órdenes reales en Binance)
especialista_v3.py        — Análisis técnico exclusivo del bot real
bot_SNIPER_SIM.py         — Simulador paper trading
especialista_SNIPER.py    — Análisis técnico exclusivo del simulador
test_conexion.py          — Conexión ccxt a Binance (compartido por ambos bots)
estado_bot.json           — Estado posiciones bot real (max 1 posición)
estado_sniper_sim.json    — Estado posiciones simulador (N posiciones, 1 por símbolo)

logs_real/
  log_trades_real.txt           — Trades reales y eventos críticos (NUNCA rota)
  log_scans_2026-WXX.txt        — Scans del bot real (rota cada lunes, semana ISO)

logs_simulador/
  simulacion_sniper_resultados.txt  — Eventos de trades simulados (NUNCA rota)
  log_scans_2026-WXX.txt            — Scans + todos los eventos del simulador (rota cada lunes)

historial/
  bots/                     — Versiones anteriores de los bots (bot_maestro_v3.py, etc.)
  logs_desarrollo/          — Logs de desarrollo históricos (log_mejora_bot.txt, etc.)
  context/                  — Versiones anteriores del CONTEXT.md (11 backups)
```

---

## 3. CONEXIÓN A BINANCE (test_conexion.py) — Compartido

```python
exchange = ccxt.binance({
    'apiKey': '...',
    'secret': '...',
    'enableRateLimit': False,
    'timeout': 10000,
    'options': {
        'defaultType': 'future',
        'fetchMarkets': ['linear'],  # solo futuros lineales, evita llamadas a margin API
    }
})
```

**IP en Binance:** Binance obliga IP fija para permisos de Futuros. Configurada en Binance API Management. Al migrar al VPS hay que actualizar la IP registrada.

---

## 4. BOT REAL V4.0 — bot_maestro_v4.py

### 4.1 Parámetros
```
Pares:          SOL/USDT:USDT | ETH/USDT:USDT  (k_lim=45, ma=SMA, pri=1/2)
STOP_LOSS:      -1.00%
BE_TRIGGER:     +0.20%   → activa break-even
BE_STOP:        +0.10%   → nivel de cierre si retrocede con BE activo (se llama RETROCESO_BE)
T1_TARGET:      +0.35%   → cierra 50% de la posición
SL_REAL_PCT:    0.85%    → stop market en Binance al abrir (seguro ante crash del proceso)
TRAILING_DIST:  0.20%    → distancia base trailing post-T1 (hasta +0.35%)
SUELO_POST_T1:  0.20%    → piso mínimo post-T1, el trailing nunca baja de aquí
BLOQUEO_SL_MIN: 15 min   → bloqueado tras STOP_LOSS o RETROCESO_BE
Escaneo:        5s fijo (time.sleep(5) en el bucle principal)
Capital/trade:  95% del balance disponible
```

### 4.2 Trailing escalonado post-T1 (4 niveles)
La distancia del trailing se ajusta según ganancia actual:
```
Ganancia:         Distancia trailing:
0.00% → 0.35%    0.20%  (suelo = SUELO_POST_T1, deja crecer)
0.35% → 0.60%    0.08%  (aprieta moderado)
0.60% → 0.80%    0.06%  (aprieta fuerte)
> 0.80%          0.05%  (máximo ajuste, protege el pico)

trailing_actual = max(SUELO_POST_T1, ganancia - dist)
trailing nunca retrocede (solo sube)
```

### 4.3 Filtros de entrada — evaluar_filtros_sniper()
Todos deben pasar. Si falla alguno, se registra en log con el detalle:

| Filtro | Campo evaluado | Umbral | Activo |
|--------|---------------|--------|--------|
| BTC trend | btc_trend_suav (fallback: btc_trend) | != BAJISTA | Sí |
| Slope 1H | pendiente_7 | >= 0.10% | Sí |
| Slope 15M | slope_ema5_15m | >= 0.05% | Sí |
| Volumen | vol_r | >= 0.30x | Sí |
| Precio sobre EMA7 | precio_sobre_ema7 | == True | Sí |
| Gap EMA7 mínimo | gap_ema7 | >= -0.05% | Sí |
| Estocástico K | k | < 45 | Sí |
| Estocástico K>D | k > d | — | Sí |
| MA50 | P<MA50 en block | — | Sí |
| Funding ESTANDAR | funding_alto + motivo ESTANDAR | UMBRAL 0.05% | Sí |

**Tipo de señal** (después de pasar todos los filtros):
- **SNIPER:** pendiente_7 > 0.10% Y vol_r > 1.30x
- **ESTANDAR:** pendiente_7 >= 0.10% (sin requisito extra de volumen)

**El bot real NO tiene:**
- Filtro ESTANDAR+ASIATICA+BTC:ALC
- Bloqueo post-BE_STOP (solo bloquea post-STOP_LOSS y post-RETROCESO_BE)
- Filtro K(15M) explícito
- Límite de Gap200 en el filtro (solo en especialista como block)

### 4.4 Secuencia de gestión de posición (orden exacto por ciclo)

**Con posición abierta:**
1. Actualizar g_max y g_min
2. Si `t1_hecho`: calcular trailing escalonado → si toca → **CIERRE_TRAILING** (vende cantidad restante)
3. Si ganancia >= T1_TARGET y no t1_hecho → **T1** (vende 50%, actualiza SL real, activa trailing con suelo)
4. Si ganancia >= BE_TRIGGER y no be_activado → **BE_ACTIVADO** (solo registra, no vende)
5. Si no t1_hecho (evaluación de salidas):
   - be_activado y ganancia <= BE_STOP → **RETROCESO_BE** (vende 100%)
   - no be_activado y ganancia <= STOP_LOSS → **STOP_LOSS** (vende 100%)
   - precio < ema7 y no be_activado → **CORTE_EMA7** (vende 100%)

**Sin posición (no ocupado):**
1. Verificar bloqueo post-STOP_LOSS / post-RETROCESO_BE
2. evaluar_filtros_sniper() → si pasa: **ENTRADA** (compra 95% balance, coloca SL real)

### 4.5 Eventos registrados en log_trades_real.txt

| Evento | Descripción |
|--------|-------------|
| `=== BOT V4.0 INICIADO ===` | Arranque del bot |
| `SYNC OK/CON DIFERENCIAS` | Sincronización estado local ↔ Binance al arrancar |
| `ENTRADA [{SNIPER/ESTANDAR}]` | Compra ejecutada + contexto técnico completo |
| `SL_REAL colocado` | SL stop_market colocado en Binance |
| `SL_REAL cancelado` | SL cancelado (al cerrar posición o en T1) |
| `BE_ACTIVADO` | Break-even activado |
| `T1` | 50% vendido + nuevo SL real colocado |
| `SALIDA [CIERRE_TRAILING]` | 50% restante cerrado por trailing |
| `SALIDA [RETROCESO_BE]` | 100% cerrado por retroceso con BE activo |
| `SALIDA [STOP_LOSS]` | 100% cerrado por pérdida máxima |
| `SALIDA [CORTE_EMA7]` | 100% cerrado por precio bajo EMA7 |
| `BLOQUEO_SL` | Bloqueo activado post-STOP_LOSS |
| `BLOQUEO_BE` | Bloqueo activado post-RETROCESO_BE |
| `POST_TRADE [motivo]` | Checkpoints 0.5/1/3/5/15/30/60/120 min post-cierre |
| `WARN fetch_balance` | fetch_balance falló, usando cache |
| `ERROR` | Excepción general en buscar_oportunidades() |
| Heartbeat | Balance + hora cada 6h (solo Telegram, no al log) |

### 4.6 Campos del SCAN log — Bot Real
Formato exacto (log_scans_2026-WXX.txt), todo en una línea:
```
SCAN {simbolo} | HORA:{HH:MM}UTC | P:{precio} |
Slope1h:{%} | VolR:{x} | K:{} | D:{} |
GapEMA7:{%} | SobreEMA7:{bool} | Cruce1h:{-/CRUCE_ALCISTA/CRUCE_BAJISTA} |
Slope15m:{%} | Cruce15m:{} | VelasCruce15m:{n} |
BTC:{ALCISTA/BAJISTA/LATERAL} | BLOCK:{texto} |
Estado:{LIBRE/OPEN(+x%)/BLOQ_SL(Nmin)/DISPARANDO/ESPERA/BLOQ:{motivo}} |
ATR_1H:{%} | ATR_15M:{%} | Funding:{rate} | FundAlto:{bool} |
GapVWAP:{%} | K15m:{} | D15m:{} | Cuerpo1H:{} | VelaAlc:{bool} | OBV:{%}
```

**El scan del bot real NO incluye:** SESION, H_1H, L_1H, H_15M, L_15M, valores numéricos de EMA5/EMA7, MA50, Gap200, gEMAS, precio numérico de BTC, BTC_SLOPE numérico, texto FILTROS, ni ID_TRADE.

### 4.7 Campos del log de ENTRADA — Bot Real
```
ENTRADA [{motivo}] {simbolo} | P:{} | HORA:{}UTC | SESION:{} |
K:{} D:{} | Slope1h:{%} | Slope15m:{%} | VolR:{x} | GapEMA7:{%} | SobreEMA7:{bool} |
Cruce15m:{} | VelasCruce15m:{n} | Cruce1h:{} | BTC:{trend} | Gap200:{%} |
H_1H:{} | L_1H:{} | H_15M:{} | L_15M:{} |
ATR_1H:{%} | ATR_15M:{%} | ATR_5M:{%} |
Funding:{} | GapVWAP:{%} | K15m:{} | D15m:{} | Cuerpo1H:{} | VelaAlc:{bool} | OBV_slope:{%}
```

### 4.8 Campos del log de SALIDA — Bot Real
```
SALIDA [{motivo}] {simbolo} | PnL:{%} | P_entrada:{} | P_salida:{} |
Max:{%} | Min:{%} | Sesion:{} | BTC:{trend_entrada} | Motivo:{SNIPER/ESTANDAR} |
GapEMA7:{entrada} | Cruce15m:{entrada} | VelasCruce15m:{entrada} |
Entrada:{fecha_hora} |
ATR_1H_ent:{%} | ATR_15M_ent:{%} | ATR_1H_now:{%} | ATR_15M_now:{%}
```
Para CIERRE_TRAILING se agrega: `Trail:{%} | SubidaPostT1:{%}`

### 4.9 Datos guardados en estado_bot.json al entrar
```
precio_entrada, cantidad, sl_real, t1_hecho, be_activado, trailing_stop,
g_max, g_min, sesion, motivo_entrada, f_entrada_str, hora_utc_entrada,
slope_entrada, slope_15m_entrada, vol_r_entrada, gap_ema7_entrada,
precio_sobre_ema7, cruce_15m_entrada, velas_cruce_entrada, cruce_1h_entrada,
btc_trend_entrada, gap200_entrada, k_entrada, d_entrada,
atr_1h_entrada, atr_15m_entrada, atr_5m_entrada,
h_1h_entrada, l_1h_entrada, h_15m_entrada, l_15m_entrada
```
**El bot real NO guarda id_trade, precio_max ni precio_min desde apertura.**

### 4.10 Funcionalidades exclusivas del bot real
- **Órdenes reales:** create_market_buy_order() / create_market_sell_order() en Binance
- **SL real en Binance:** stop_market order al 0.85% al entrar; se cancela y recoloca en T1 con la mitad
- **Telegram:** arranque, cada entrada, T1, trailing, salidas, heartbeat 6H, errores críticos
- **Sincronización al arrancar:** compara posiciones Binance vs estado local, limpia zombies, alerta huérfanas
- **Detección error -4411:** error acuerdo TradFi → alerta Telegram + pausa 300s
- **Una posición a la vez:** flag "ocupado" en estado_bot.json
- **fetch_balance con cache:** si falla el balance, usa el último valor conocido sin detener scans
- **Display terminal:** muestra estado en tiempo real con \r (sobreescribe la línea)

---

## 5. ESPECIALISTA BOT REAL — especialista_v3.py

### 5.1 Características técnicas
- **fetch_con_timeout():** TODOS los fetches usan threading con timeout de 8 segundos. TimeoutError si supera el límite.
- **Fetch 1H:** `fetch_ohlcv(simbolo, '1h', limit=210)` — via fetch_con_timeout
- **Fetch 15M:** `fetch_ohlcv(simbolo, '15m', limit=100, params={'price': 'mark'})` — via fetch_con_timeout
- **Fetch BTC 15M:** `fetch_ohlcv('BTC/USDT:USDT', '15m', limit=24)` — via fetch_con_timeout
- **Fetch BTC 1M:** `fetch_ohlcv('BTC/USDT:USDT', '1m', limit=10)` — via fetch_con_timeout
- **Fetch BTC 5M:** `fetch_ohlcv('BTC/USDT:USDT', '5m', limit=10)` — via fetch_con_timeout
- **Fetch ATR 5M símbolo:** `fetch_ohlcv(simbolo, '5m', limit=20)` — llamada directa (sin timeout)
- **Fetch Funding:** `exchange.fetch_funding_rate(simbolo)` — llamada directa

### 5.2 Contexto BTC — Bot Real (completo, multi-TF)
```
Variable global: _btc_slopes_hist = []  (persiste entre llamadas, N=5)

BTC 15M (base):
  - slope EMA7: btc_slope
  - suavizado N=5: btc_slope_suav → btc_trend_suav (FILTRO ACTIVO)
  - umbral: ±0.05%
  - tendencia: ALCISTA si > +0.05%, BAJISTA si < -0.05%, LATERAL

BTC 1M (LOG):
  - slope EMA7: btc_1m_slope
  - umbral: ±0.01%
  - btc_1m_trend: ALCISTA/BAJISTA/LATERAL

BTC 5M (LOG):
  - slope EMA7: btc_5m_slope
  - umbral: ±0.03%
  - btc_5m_trend: ALCISTA/BAJISTA/LATERAL

Score multi-TF (LOG):
  - s1 = ±1 según btc_1m_slope vs ±0.01%
  - s5 = ±1 según btc_5m_slope vs ±0.03%
  - s15 = ±1 según btc_slope_suav vs ±0.05%
  - btc_score = s1 + s5 + s15 → rango -3 a +3

Métricas adicionales (LOG):
  - btc_retorno_1h: retorno últimas 4 velas 15M
  - corr_btc: correlación símbolo vs BTC últimas 20 velas 15M (retornos pct)
  - divergencia_btc: pendiente_7(símbolo) - btc_5m_slope
```
**El filtro activo usa btc_trend_suav (suavizado), NO btc_trend directo.**

### 5.3 Campos devueltos por especialista_v3.py
```python
# Precio y estocástico 1H
'p', 'k', 'd'
# EMAs 1H
'ema5', 'ema5_prev', 'ema7', 'ema7_prev', 'ma50', 'ma200'
'pendiente_7', 'vol_r', 'gap200'
'gap_ema7', 'cruce_1h', 'precio_sobre_ema7'
# EMAs y análisis 15M
'ema5_15m', 'ema7_15m', 'slope_ema5_15m'
'cruce_15m', 'velas_desde_cruce'
'k_15m', 'd_15m', 'k_15m_mayor_d'
# ATR multi-TF
'atr_1h', 'atr_15m', 'atr_5m'
# OHLC vela actual
'h_1h', 'l_1h', 'h_15m', 'l_15m'
# Funding
'funding_rate', 'funding_alto'
# VWAP (LOG)
'vwap', 'gap_vwap'
# Cuerpo vela 1H (LOG)
'cuerpo_1h', 'vela_alcista_1h'
# OBV (LOG)
'obv_slope'
# BTC multi-TF
'btc_precio', 'btc_slope', 'btc_slope_suav'
'btc_1m_slope', 'btc_5m_slope'
'btc_trend', 'btc_trend_suav', 'btc_1m_trend', 'btc_5m_trend'
'btc_score', 'btc_retorno_1h', 'corr_btc', 'divergencia_btc'
# Bloqueos
'block', 'error'
```

### 5.4 Construcción del campo 'block' — especialista_v3.py
```
"P<MA50"         si precio < ma50
"P<MA200"        si precio < ma200
"K>{k_lim}"      si k > k_lim AND pendiente_7 < 0.10% (solo si pendiente baja)
"K<D"            si k < d AND pendiente_7 < 0.10% (solo si pendiente baja)
"P<EMA7"         si precio < ema7
"PLANA"          si pendiente_7 <= 0.05%
"FUNDING_ALTO:{rate}" si funding_alto (informativo; el filtro lo maneja el bot según tipo de señal)
```

---

## 6. SIMULADOR V7.5 — bot_SNIPER_SIM.py

### 6.1 Parámetros
```
Pares:            SOL/USDT:USDT | ETH/USDT:USDT  (k_lim=45, ma=SMA)
CAPITAL_INICIAL:  23.06 USDT (simulación matemática)
STOP_LOSS_BASE:   -0.85%
BE_TRIGGER:       +0.15%   → activa protección BE
SL_COMISION:      +0.10%   → nivel BE_STOP (cubre comisiones Binance 0.05% entrada + 0.05% salida)
T1_TARGET:        +0.25%   → cierra 50% del capital simulado
TRAILING_DIST:    0.20%    → trailing base hasta TRAILING2_DESDE
TRAILING2_DIST:   0.10%    → trailing apretado desde TRAILING2_DESDE
TRAILING2_DESDE:  0.40%    → nivel donde aprieta el trailing
SUELO_POST_T1:    T1_TARGET (0.25%) → nunca cierra por debajo de T1 post-T1
SLEEP_LIBRE:      3.0s     → sin posición
SLEEP_POSICION:   0.5s     → con posición (más reactivo para BE y T1)
Capital:          Simulación matemática (balance_acumulado *= (1 + ganancia/100))
```

### 6.2 Trailing de 2 niveles post-T1
```
Ganancia:          Trailing aplicado:
0.00% → 0.40%     ganancia - TRAILING_DIST (0.20%)
>= 0.40%          ganancia - TRAILING2_DIST (0.10%)
Suelo siempre:    max(SUELO_POST_T1=0.25%, trailing_stop)
trailing nunca retrocede (solo sube)
```

### 6.3 Filtros de entrada — Simulador

**Paso 1: Determinar motivo_entrada**
```
pendiente_alta = pendiente_7 > 0.10%
vol_confirmado = vol_r > 1.30x
tecnica_limpia = block == ""

Si pendiente_alta AND vol_confirmado  → motivo = "SNIPER"
Si tecnica_limpia AND pendiente_7 > 0.10%  → motivo = "ESTANDAR"
(SNIPER tiene prioridad; si hay vol_confirmado pero block != "" no entra como SNIPER)
```

**Paso 2: Filtros generales (bloquean antes de evaluar F1-F5)**
```
pasa_btc  = btc_trend != 'BAJISTA'  (usa btc_trend DIRECTO, NO suavizado)
pasa_15m  = slope_ema5_15m > 0.05%
gap_ok    = gap200 <= 4.0%
```

**Paso 3: Filtros específicos F1-F5 (solo si hay motivo y pasó paso 2)**
```
F1 pasa_vol     = vol_r >= 0.30x
F2 pasa_k15m    = k_mayor_d_15m OR k_d_diff_15m > -5
F3 pasa_combo   = NOT (ESTANDAR + ASIATICA + btc_trend==ALCISTA + FILTRO_ASIA_STD_ALC=True)
F4 pasa_be_lock = símbolo no en bloqueo_be_stop (15min post-BE_STOP)
F5 pasa_funding = NOT (funding_alto AND motivo==ESTANDAR)
```

**Señal bloqueada (log):** Si motivo existe, gap_ok, pasa_btc, pasa_15m pero falla F1-F5 → registra `SEÑAL_BLOQUEADA` con detalle del filtro que falló.

**Diferencias vs bot real:**
- Usa `btc_trend` directo (el bot real usa `btc_trend_suav`)
- Tiene F3 combo ESTANDAR+ASIATICA+ALC (el bot real no tiene este filtro)
- Tiene F4 bloqueo post-BE_STOP (el bot real bloquea solo post-STOP_LOSS y post-RETROCESO_BE)
- Tiene F2 filtro K(15M) explícito (el bot real no lo tiene)
- Puede abrir múltiples posiciones simultáneas (bot real: una a la vez)

### 6.4 Secuencia de gestión de posición — Simulador

**Con posición abierta:**
1. Actualizar precio_actual, precio_max, precio_min en estado
2. Si ganancia >= BE_TRIGGER y no be_activado → **BE ACTIVADO** (anotar_evento)
3. Si ganancia >= T1_TARGET y no t1_hecho → **T1 ALCANZADO** (anotar_evento, actualiza balance_acumulado 50%)
4. Si t1_hecho: calcular trailing 2 niveles → si toca suelo → **CIERRE_TRAILING** (anotar_evento + _guardar_estado_sim)
5. Si no t1_hecho:
   - be_activado y ganancia <= SL_COMISION → **BE_STOP**
   - no be_activado y ganancia <= STOP_LOSS_BASE → **STOP_LOSS**
   - precio < ema7 y no be_activado → **CORTE_EMA7**
   (cualquiera → anotar_evento + _guardar_estado_sim inmediato)

**Sin posición:**
1. Determinar motivo (paso 1 arriba)
2. Verificar filtros generales (paso 2)
3. Si log de señal bloqueada aplica → registrar_log_sim SEÑAL_BLOQUEADA
4. Si pasa todo F1-F5 → **ENTRADA** (anotar_evento + separadores en log)

### 6.5 Eventos en simulacion_sniper_resultados.txt (via anotar_evento)

| Evento | Descripción |
|--------|-------------|
| `ENTRADA [{SNIPER/ESTANDAR}]` | Apertura de posición simulada + contexto completo |
| `🛡️ BE ACTIVADO` | Break-even activado |
| `T1 ALCANZADO` | 50% cobrado + balance actualizado |
| `CIERRE_TRAILING` | 50% restante cerrado por trailing |
| `SALIDA [BE_STOP]` | Cierre por retroceso con BE (equivale a RETROCESO_BE del bot real) |
| `SALIDA [STOP_LOSS]` | Cierre por pérdida máxima |
| `SALIDA [CORTE_EMA7]` | Cierre por precio bajo EMA7 |

**Nombre de eventos diferente al bot real:** el simulador llama "BE_STOP" a lo que el bot real llama "RETROCESO_BE".

### 6.6 Campos del SCAN log — Simulador
El scan va al mismo archivo (log_scans_2026-WXX.txt) que todos los demás eventos:
```
SCAN {simbolo} | HORA:{HH:MM}UTC | SESION:{ASIATICA/EUROPEA/AMERICANA} |
P:{} | H_1H:{} | L_1H:{} | H_15M:{} | L_15M:{} | Slope1h:{%} |
Vol_R:{x} | K:{} | D:{} | EMA5:{} | EMA7:{} |
GapEMA7_1h:{%} | SobreEMA7:{bool} | gEMAS:{%} |
CRUCE_1H:{} | EMA5_15M:{} | EMA7_15M:{} | SLOPE_EMA5_15M:{%} |
CRUCE_15M:{} | VELAS_CRUCE_15M:{n} |
BTC:{precio_numérico} | BTC_SLOPE:{%} | BTC_TREND:{} |
MA50:{} | Gap200:{%} |
BLOCK:{} | FILTROS:{OK / BTC_BAJISTA / SLOPE_15M<=x%} |
ESTADO:{LIBRE / EN_POSICION(+x%) ID:{id_trade}} |
ATR_1H:{%} | ATR_15M:{%} | Funding:{} | FundAlto:{bool} |
GapVWAP:{%} | K15m:{} | D15m:{} | Cuerpo1H:{} | VelaAlc:{bool} | OBV:{%}
```

**El scan del simulador incluye más campos que el del bot real:** SESION, H_1H/L_1H/H_15M/L_15M, valores EMA5/EMA7, MA50, Gap200, gEMAS, precio BTC numérico, BTC_SLOPE numérico, FILTROS texto, ID_TRADE en el estado.

### 6.7 Eventos adicionales en log_scans del simulador
```
============================================================         ← delimitador visual
>>> ENTRADA [{motivo}] {simbolo} | ID:{id_trade} | P:{} | HH:MMUTC | BAL:${}
[scans con ESTADO:EN_POSICION(+x%) ID:{id_trade}]
<<< CIERRE_TRAILING {simbolo} | ID:{id_trade} | PnL_trail:{%} | BAL:${}
<<< SALIDA [{motivo}] {simbolo} | ID:{id_trade} | PnL:{%} | BAL:${}
============================================================         ← delimitador visual

SEÑAL_BLOQUEADA [{motivo}] {simbolo} | P:{} | Vol_R:{} | ... | BLOQUEADO_POR:{filtros}
BE_LOCK activado {simbolo} | Bloqueado 15min hasta HH:MM:SS
POST_TRADE [{motivo}] {simbolo} | t:{Nmin/Nh} | P_cierre:{} | P_ahora:{} | Retorno:{%} | ...
```

### 6.8 Campos del log de ENTRADA — Simulador (en simulacion_sniper_resultados.txt)
```
ENTRADA [{motivo}] {simbolo}:
P:{} | H_1H:{} | L_1H:{} | H_15M:{} | L_15M:{} | Slope:{%} |
Vol_R:{x} | K:{} | GapEMA7:{%} | SobreEMA7:{bool} |
Cruce15m:{} | VelasCruce15m:{n} | Slope_15m:{%} | BTC:{trend} |
CRUCE_1H:{} | Gap200:{%} | SESION:{} |
ATR_1H:{%} | ATR_15M:{%} | ATR_5M:{%} | Funding:{} | GapVWAP:{%} |
K15m:{} | D15m:{} | Cuerpo1H:{} | VelaAlc:{bool} | OBV_slope:{%}
```

### 6.9 Datos guardados en estado_sniper_sim.json al entrar
```
id_trade, precio_entrada, precio_max, precio_min,
motivo_entrada, t1_hecho, be_activado, trailing_stop,
btc_trend, slope_15m, cruce_1h, sesion,
gap_ema7, cruce_15m, velas_cruce_15m, precio_sobre_ema7,
slope_entrada, vol_r_entrada, gap200_entrada, f_entrada,
h_1h_entrada, l_1h_entrada, h_15m_entrada, l_15m_entrada,
atr_1h_entrada, atr_15m_entrada, atr_5m_entrada
```
**Diferencias vs bot real:** el simulador guarda id_trade, precio_max/min desde apertura. No guarda cantidad, sl_real, g_max/g_min, hora_utc_entrada, k_entrada, d_entrada.

### 6.10 Anti-zombie: guardado inmediato
Cada cierre de posición llama `_guardar_estado_sim(estado)` inmediatamente antes de continuar. Previene el bug del 18 Mar donde la posición se cerraba cientos de veces por no escribirse al disco.

### 6.11 Funcionalidades exclusivas del simulador
- Múltiples posiciones simultáneas (una por símbolo)
- ID_TRADE único: `YYYYMMDD_HHMMSS_SOL`
- Frecuencia adaptativa: 3s libre / 0.5s en posición
- Separadores `>>>`, `<<<`, `====` en log de scans
- Log SEÑAL_BLOQUEADA con detalle de qué filtro falló
- Sin Telegram, sin sync Binance, sin SL real, sin órdenes reales

---

## 7. ESPECIALISTA SIMULADOR — especialista_SNIPER.py

### 7.1 Características técnicas
- **Sin fetch_con_timeout()** para fetches 1H y 15M del símbolo (llamadas directas que pueden bloquearse)
- **fetch_con_timeout() solo para BTC:** usa threading con timeout=8s exclusivamente para el fetch BTC 15M
- **Fetch 1H:** `exchange.fetch_ohlcv(simbolo, '1h', limit=250)` — llamada directa
- **Fetch 15M:** `exchange.fetch_ohlcv(simbolo, '15m', limit=100, params={'price': 'mark'})` — llamada directa
- **Fetch BTC 15M:** via threading con timeout=8s
- **Fetch ATR 5M símbolo:** `exchange.fetch_ohlcv(simbolo, '5m', limit=20)` — llamada directa
- **Fetch Funding:** `exchange.fetch_funding_rate(simbolo)` — llamada directa

### 7.2 Contexto BTC — Simulador (simple, solo 15M)
```
BTC 15M solamente:
  - slope EMA7: btc_slope
  - umbral: ±0.02% (más sensible que el bot real ±0.05%)
  - btc_trend: ALCISTA si > +0.02%, BAJISTA si < -0.02%, LATERAL
  - SIN suavizado, SIN multi-TF, SIN score, SIN correlación, SIN divergencia
```
**El filtro activo en el simulador usa `btc_trend` directo (más ruidoso que `btc_trend_suav` del bot real).**

### 7.3 Campos devueltos por especialista_SNIPER.py
Devuelve los mismos campos comunes (ver sección 8) **excepto** los campos multi-TF de BTC:
```
# NO devuelve: btc_slope_suav, btc_trend_suav, btc_1m_slope, btc_5m_slope,
#              btc_1m_trend, btc_5m_trend, btc_score, btc_retorno_1h,
#              corr_btc, divergencia_btc
# Solo devuelve: btc_precio, btc_slope, btc_trend
```

### 7.4 Construcción del campo 'block' — especialista_SNIPER.py
Idéntica al bot real (mismos criterios). Ver sección 5.4.

---

## 8. CAMPOS COMUNES A AMBOS ESPECIALISTAS

Calculados de la misma forma en ambos:

**Análisis 1H (0 fetches extra — usa velas 1H ya descargadas):**
- `p` — precio actual (cierre última vela)
- `k`, `d` — estocástico (14, 3)
- `ema5`, `ema5_prev`, `ema7`, `ema7_prev` — EMAs horarias
- `ma50`, `ma200` — medias móviles macro
- `pendiente_7` — ((EMA7[-1] - EMA7[-2]) / EMA7[-2]) × 100
- `vol_r` — volumen actual / media móvil 20 velas
- `gap200` — % distancia a MA200
- `gap_ema7` — % distancia precio a EMA7
- `cruce_1h` — CRUCE_ALCISTA / CRUCE_BAJISTA / '' (cruces EMA5/EMA7)
- `precio_sobre_ema7` — bool
- `atr_1h` — ATR(14) en % del precio (True Range de 14 velas 1H)
- `h_1h`, `l_1h` — máximo y mínimo de la última vela 1H
- `vwap`, `gap_vwap` — VWAP diario y distancia % (solo velas del día UTC actual)
- `cuerpo_1h` — |C-O|/(H-L), de 0 (doji) a 1 (vela perfecta)
- `vela_alcista_1h` — bool
- `obv_slope` — ((OBV[-1] - OBV[-5]) / |OBV[-5]|) × 100

**Análisis 15M (1 fetch por símbolo):**
- `ema5_15m`, `ema7_15m`, `slope_ema5_15m`
- `cruce_15m`, `velas_desde_cruce`
- `k_15m`, `d_15m`, `k_15m_mayor_d` — estocástico (14,3) en 15M
- `atr_15m` — ATR(14) en % del precio
- `h_15m`, `l_15m` — máximo y mínimo última vela 15M
- `cuerpo_15m`, `vela_alcista_15m` — calculados pero NO incluidos en res.update()

**ATR 5M (1 fetch extra por símbolo):**
- `atr_5m` — ATR(14) en % del precio

**Funding rate (1 fetch por símbolo):**
- `funding_rate` — tasa actual (ej: 0.0003 = 0.03%)
- `funding_alto` — bool, True si |funding_rate| > 0.0005 (0.05%)

**Bloqueos:**
- `block` — string con bloqueos técnicos concatenados
- `error` — bool, True si hubo excepción en el análisis

---

## 9. TABLA COMPARATIVA BOT REAL vs SIMULADOR

| Característica | Bot Real V4.0 | Simulador V7.5 |
|----------------|---------------|----------------|
| Órdenes | Reales en Binance | Simulación matemática |
| Posiciones simultáneas | 1 (flag ocupado) | N (1 por símbolo) |
| SL real en Binance | ✅ 0.85% stop_market | ❌ No |
| Telegram | ✅ Arranque/trades/heartbeat | ❌ No |
| Sync Binance al arrancar | ✅ Sí | ❌ No |
| STOP_LOSS | -1.00% | -0.85% |
| BE_TRIGGER | +0.20% | +0.15% |
| BE_STOP nivel | +0.10% | +0.10% (SL_COMISION) |
| BE salida se llama | RETROCESO_BE | BE_STOP |
| T1_TARGET | +0.35% | +0.25% |
| Trailing | 4 niveles escalonados | 2 niveles (base + apretado) |
| SUELO_POST_T1 | 0.20% | 0.25% (=T1) |
| Escaneo | 5s fijo | 3s libre / 0.5s en posición |
| BTC filtro | btc_trend_suav (N=5, ±0.05%) | btc_trend directo (±0.02%) |
| Filtro ESTANDAR+ASIA+ALC | ❌ No | ✅ Sí (F3) |
| Bloqueo post-BE_STOP | ❌ No | ✅ 15min (F4) |
| Bloqueo post-STOP_LOSS | ✅ 15min | ❌ No |
| Bloqueo post-RETROCESO_BE | ✅ 15min | ❌ No (lo bloquea F4 por BE_STOP) |
| Filtro K(15M) explícito | ❌ No | ✅ k_mayor_d_15m (F2) |
| Gap200 límite | ❌ (solo block) | ✅ gap_ok <= 4.0% |
| ID_TRADE | ❌ No | ✅ YYYYMMDD_HHMMSS_SIM |
| Separadores log | ❌ No | ✅ >>>, <<<, ==== |
| SEÑAL_BLOQUEADA log | ❌ No | ✅ Sí |
| fetch_con_timeout() | ✅ Todos los fetches | Solo fetch BTC |
| BTC multi-TF | ✅ 1M/5M/15M + suavizado | Solo 15M |
| BTC umbral | ±0.05% | ±0.02% |
| Anti-zombie | ✅ guardar_estado en main | ✅ _guardar_estado_sim() inmediato |
| Campos en scan log | Menos (sin SESION, OHLC, etc.) | Más (completo) |

---

## 10. ANÁLISIS ESTADÍSTICO — 49 TRADES REALES (12-18 Mar 2026)

**Contexto:** Período bajista/lateral. Balance: $22.50 → $22.16 (-1.49%).

### Resultados generales
- Win rate: 69% (34 ganadores / 15 perdedores)
- PnL medio ganador: +0.181% | PnL medio perdedor: -0.509%
- Asimetría: 1 perdedor = 2.8 ganadores en tamaño → problema principal
- SNIPER: 8% loss rate (1/12) | ESTANDAR: 32% loss rate (12/37)

### Hallazgos clave
- **CORTE_EMA7 (13 trades):** PnL medio -0.453%. Max alcanzado solo +0.06%. Nunca llegaron a +0.20%. K medio 57.4 vs ganadores 79.8.
- **BTC Score +3:** 55% WR y -0.114% PnL — PEOR resultado (contraintuitivo — 3 TF alcistas = peor)
- **BTC Score 0 (lateral):** 100% WR y +0.236% PnL — MEJOR resultado
- **Hora 22-23 UTC:** 25-33% WR — peor ventana. Hora 04H y 15-16H UTC: 89-100% WR.
- **Duración CORTE_EMA7:** ~0.94h vs ganadores ~0.54h → trade > 1h sin T1 = alta probabilidad de pérdida
- **GapEMA7:** TRAILING promedio +0.563% vs CORTE_EMA7: +0.377% → Gap más alto = mejores resultados
- **Divergencia BTC < -0.05%:** 82% WR vs 40% global (pendiente confirmar 200+)
- **VelasCruce 2-4:** mejor zona. 0-1 sin confirmación = riesgo. 5+: colapso a 40% WR.
- **GapEMA7 < 0.20%:** 20-25% WR — zona a evitar

### Filtros ya implementados (confirmados por datos)
- Vol_R >= 0.30x ✅
- Slope_1H >= 0.10% ✅
- Bloqueo BE_STOP 15min (simulador) ✅
- Funding bloquea ESTANDAR ✅

### Pendiente de confirmar (necesita 200+ trades)
- Filtro VelasCruce 2-4
- Filtro hora UTC 22-23
- Umbral GapVWAP, K(15M), cuerpo vela 1H, OBV slope
- Trailing ATR_15M × 0.50 (+0.437% en simulación de 18 trades)
- Divergencia BTC < -0.05% como filtro
- Bloqueo BTC score <= -2

---

## 11. ESTADO DE ERRORES CONOCIDOS

| Error | Causa | Estado |
|-------|-------|--------|
| `ssymbol=SOLUSDT` (doble s en URL) | Bug interno ccxt al construir URL de futuros | ✅ RESUELTO — upgrade ccxt eliminó el error |
| `timesttamp` (doble t en URL) | Bug interno ccxt | ✅ RESUELTO — upgrade + fetchMarkets:['linear'] |
| `sapi/v1/margin` calls innecesarias | ccxt cargaba mercados de margen | ✅ RESUELTO — fetchMarkets:['linear'] |
| `fapi/v3/account` spam en log | fetch_balance fallaba cada 5s llenando el log | ✅ RESUELTO — actualizar_balance() con throttle 60s |
| Posición zombie al reiniciar simulador | Bot se apagaba con posiciones abiertas, al reiniciar aplicaba precio actual a posición vieja | ✅ RESUELTO — sincronizar_simulador() cierra posiciones al arrancar |
| Posición zombie mid-session (18 Mar sim) | json.dump fallaba silenciosamente | ✅ RESUELTO — _guardar_estado_sim() inmediato |
| Log arranque no registraba | registrar_log después del sync que podía fallar | ✅ RESUELTO — movido antes del sync |

---

## 12. HISTORIAL DE SESIONES

### Sesión 29 Mar 2026 — Tarde (Sesión 1 con Claude Code)
**Sistema establecido:**
- Flujo de trabajo definitivo: Claude.ai (diseño) + Claude Code terminal (ejecución)
- Tres terminales: bot real | simulador | Claude Code
- Protocolo CLAUDE.md + SESSION_LOG.md funcionando correctamente

**Corregido:**
- `actualizar_balance()` con throttle 60s en bot real — elimina spam de 481 WARNs
- `sincronizar_simulador()` al arrancar — cierra posiciones zombie de sesiones anteriores
- Reorganización de carpetas: historial/bots/, historial/logs_desarrollo/, historial/context/
- Error ssymbol confirmado resuelto — cero errores en logs W12 y W13 del simulador

**Estado tras correcciones:**
- Bot real: corriendo estable, Bal $22.65, scans normales
- Simulador: corriendo estable, Bal $17.41 (ajustado tras cierre zombie SOL -11% / ETH -8.23% de 95h apagado)

**Infraestructura:**
- VPS Contabo Cloud 20 ordenado ($8.39/mes) — pendiente activación y pago
- Flujo de migración al VPS definido en 7 pasos

**Diseñado (pendiente implementar):**
- Sistema de alertas Telegram inteligente para bot real (alertas por evento + resumen)
- Alertas mínimas para simulador (arranque + caída + resumen diario)

### Sesión 20 Mar 2026 — Tarde-noche
**Corregido:**
- Upgrade ccxt + fetchMarkets:['linear'] → elimina error margin API
- fetch_balance aislado en bot real con cache → scans no mueren por fallo de red
- Banner de terminal en bot real
- registrar_log antes del sync al arrancar
- _guardar_estado_sim() inmediato en simulador → anti-zombie
- ID_TRADE + separadores entrada/salida en scan log del simulador
- Error `ssymbol` aún intermitente → monitoreando

**Discutido:**
- VPS Contabo $4.95/mes elegido sobre Hetzner (precio/specs para 3 proyectos)
- OpenClaw IA self-hosted → instalar después de estabilizar bots
- App aeronáutica Colombia → proyecto iniciado
- App supermercado nutrición → en concepción

### Sesión 19 Mar 2026 — Sesión 3
- ATR multi-TF, OHLC, Funding, VWAP, K(15M), cuerpo, OBV en ambos especialistas
- BTC multi-TF completo (1M/5M/15M) en especialista_v3.py
- Estructura logs: carpetas separadas, rotación semanal, trades nunca rota
- Simulación trailing ATR: ATR_15M × 0.50 = +0.437% en 18 CIERRE_TRAILING

### Sesión 19 Mar 2026 — Sesión 2
- Trailing escalonado 4 niveles en bot real
- Bloqueo post-RETROCESO_BE en bot real
- Fix ERROR_BTC en especialista_SNIPER (params BTC eliminado, threading timeout)

### Sesión 19 Mar 2026 — Sesión 1
- bot_maestro_v4.py creado
- Fix API key IP restriction Binance
- Fix bug zombie ETH y error -4411
- BTC multi-TF en especialista_v3.py

### Sesiones 12-13 Mar 2026
- Filtros V7.1/V7.3 simulador (Vol_R, Slope, combo Asia, bloqueo BE, trailing escalonado)
- Análisis 49 trades reales
- Post-trade monitoring

---

## 13. PENDIENTES ORDENADOS POR PRIORIDAD

### Inmediato
- [ ] Esperar email Contabo con credenciales SSH del VPS
- [ ] Implementar alertas Telegram mejoradas (diseñadas, pendiente prompt a Claude Code)

### Migración VPS (cuando lleguen credenciales)
- [ ] Conectarse por SSH al VPS
- [ ] Instalar Python, dependencias, entorno virtual
- [ ] Subir archivos activos (NO el historial)
- [ ] Configurar systemd para reinicio automático de ambos bots
- [ ] Actualizar IP en Binance API Management
- [ ] Arrancar bots y verificar Telegram
- [ ] Apagar bots en PC local

### Con 200+ trades (~3-4 semanas)
- [ ] Calibrar VelasCruce, hora UTC, GapVWAP, K(15M), cuerpo, OBV
- [ ] Confirmar divergencia BTC como filtro
- [ ] Activar trailing ATR_15M × 0.50
- [ ] Evaluar bloqueo BTC score <= -2
- [ ] Análisis en mercado alcista

### Largo plazo
- [ ] Clasificador ML prob > 65% (1000+ trades)
- [ ] Tamaño posición dinámico según calidad de señal
- [ ] App aeronáutica Colombia
- [ ] App supermercado / nutrición

---

## 14. DECISIONES TOMADAS Y RAZÓN

| Decisión | Razón |
|----------|-------|
| SL -1.00% real vs -0.85% sim | Backtest: corta 6.6% ganadores pero reduce pérdidas netas; sim más agresivo para explorar |
| T1 0.35% real vs 0.25% sim | Sim 55% de trades llegan a T1 (0.25%) vs 31% con 0.35% |
| Trailing 4 niveles (real) vs 2 (sim) | Real captura movimientos grandes; sim explora la versión más simple |
| Vol_R >= 0.30x | 33% WR sin volumen mínimo — confirmado 49 trades |
| btc_trend_suav N=5 en bot real | Slope instantáneo 83% ruido; suavizado elimina señales falsas |
| BTC umbral ±0.05% (real) vs ±0.02% (sim) | 0.02% genera cambios de tendencia cada 1.3min |
| Logs separados trades/scans | Trades = histórico valioso; scans = volumen alto, rotar semanal |
| Funding bloquea solo ESTANDAR | SNIPER tiene señal más fuerte, vale el riesgo del funding alto |
| No filtro VelasCruce todavía | 49 trades insuficientes para calibrar sin sobreoptimizar |
| No filtrar hora UTC todavía | Mismo motivo |
| No bloquear BTC score +3 todavía | Contraintuitivo — necesita confirmación con 200+ antes de actuar |
| _guardar_estado_sim() inmediato | Bug zombie del 18 Mar: guardado al final del ciclo es insuficiente |
| fetchMarkets:['linear'] | Evita que ccxt cargue mercados de margen y llame sapi/v1/margin |
| fetch_balance con cache | Bot sigue escaneando aunque falle el balance de red |

---

## 15. PRÓXIMA SESIÓN — QUÉ HACER PRIMERO

1. **Verificar email de Contabo** — credenciales SSH del VPS (IP, usuario root, contraseña)
2. **Si VPS listo:** conectarse por SSH y ejecutar guía de migración en 7 pasos
3. **Antes de migrar:** implementar sistema de alertas Telegram mejorado (diseñado en sesión 29-Mar)
4. **Actualizar IP en Binance** — con la IP del VPS nuevo al migrar

---

---

## 16. NOTA PARA EL UNIVERSO

*29 de marzo de 2026*

Esta es la primera sesión en que MiBotTrading opera formalmente como nodo de El Universo. El sistema de documentación (CLAUDE.md + CONTEXT.md + SESSION_LOG.md + UNIVERSO_NOTAS.md) está activo y funcionando correctamente — el protocolo de inicio y cierre de sesión se ejecutó por primera vez hoy con Claude Code.

El nodo está en una etapa crítica: los bots están corriendo y generando datos reales, el VPS está en camino, y la infraestructura base está limpia y organizada. El siguiente gran paso es la autonomía 24/7 en la nube.

Si el Universo puede ayudar en algo — coordinar con otros nodos, recordar decisiones que afecten a este proyecto, o simplemente tener contexto de en qué estamos — este CONTEXT.md es la puerta de entrada.

Estamos conectados.

*— MiBotTrading (Especialista: Trader)*