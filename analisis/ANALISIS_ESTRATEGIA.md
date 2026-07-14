# Análisis de Estrategia — MiBotTrading (Simulador V7.5)
**Fecha:** 4 de junio de 2026
**Universo:** 496 trades simulados completos, semanas ISO W15→W23 (10-abr a 4-jun 2026)
**Fuente:** `analisis/datasets/` (parquet validados; ver `REPORTE_SALUD_DATOS.md`)
**Alcance:** análisis de estrategia + recomendaciones para **probar en simulador**. NO se modificó ningún bot. NO es una configuración para dinero real.

---

## 0. Metodología y convenciones (leer antes que las cifras)

- **PnL ground-truth = multiplicador real del `balance_acumulado`** que aplicó el bot en cada cierre:
  - SALIDA completa (STOP_LOSS / BE_STOP / CORTE_EMA7): `ganancia` sobre el 100%.
  - CIERRE_TRAILING: dos patas sobre el 50% c/u → `(1+0.5·T1/100)·(1+0.5·trail/100)−1`. Verificado contra `0.5·(t1_pct+trail_pct)` (diferencia máx 0.0007pp).
  - **Validación de integridad:** los multiplicadores derivados reproducen exactamente el balance del bot en la era moderna (T1→×1.00125, trailing→×(1+0.5·trail/100), SALIDA→×(1+pnl/100)).
- **Todo en NETO**: comisión round-trip **0.10%** (0.05% entrada taker + 0.05% salida taker, supuesto del proyecto) + funding estimado (cruces de 00/08/16 UTC). El funding resultó **despreciable** (−0.03pp en 496 trades; solo 32 trades cruzaron un horario de funding). La comisión es la que manda.
- **Re-simulación validada:** se reconstruyó la lógica de salida del sim sobre la trayectoria de precios real (scans, ~2s) y **reproduce el resultado real en 99.6%** (494/496). Sobre ese motor se evalúan todos los contrafácticos como **regla aplicada a los 496 trades** (cuenta también cuando una regla agranda pérdidas).
- **Out-of-sample (OOS):** split temporal por fecha de entrada — TRAIN = primera mitad (10-abr→2-may), TEST = segunda mitad (2-may→4-jun).
- **⚠️ Caveat de capital con posiciones simultáneas:** el sim aplica el multiplicador de **cada** trade al balance compartido, **sin asignar capital por posición ni descontar al entrar**. Con SOL+ETH abiertos a la vez (52% de los trades se solapan con otro), cada uno compone como si tuviera el 100% del capital → la **curva de equity absoluta está sobreestimada** en los tramos de solapamiento. Por eso el análisis se basa en **expectativa por trade** (retorno sobre nocional), que es comparable entre tipos de salida, y se trata la curva de equity como indicativa, no literal.
- **⚠️ Caveat de régimen:** los 496 trades son de **~2 meses de mercado bajista/lateral**. Cada hallazgo que pueda depender del régimen está marcado con **[RÉGIMEN]**.
- **Bot real:** solo 7 trades (último 3-may), usado únicamente para contrastar el filtro K<45 (§5). Sin valor estadístico propio.

---

## 1. Línea base

**Composición (n=496):** entrada SNIPER 258 / ESTANDAR 238. Salida: **BE_STOP 217 (44%)**, **CIERRE_TRAILING 171 (34%)**, **CORTE_EMA7 79 (16%)**, **STOP_LOSS 29 (6%)**.

### 1.1 Resultado global (NETO)
| Métrica | Neto | Bruto |
|---|---|---|
| Win rate | **34.5%** | 77.4% |
| Expectativa / trade | **−0.110%** | −0.010% |
| Ganador medio | +0.161% | +0.163% |
| Perdedor medio | −0.252% | −0.600% |
| PnL total (suma) | **−54.4 pp** | −4.76 pp |
| Equity secuencial compuesto* | **−42%** | −4.9% |
| Max drawdown* | **−42%** | −13.5% |
| Peor racha perdedora | **17 trades seguidos** | — |

\* Equity "1 posición equivalente" (cumprod de retornos por trade en orden de cierre), sin el apalancamiento de concurrencia. El balance bruto que el propio bot reportó en W15→W23 cayó **24.93 → 23.78 (−4.6%)** — incluso en bruto y con concurrencia, perdió.

### 1.2 EL hallazgo de la línea base: **la comisión es el 91% de la pérdida**
| Componente | pp sobre 496 trades |
|---|---|
| Bruto | −4.76 |
| Comisiones (0.10%/trade) | **−49.60** |
| Funding | −0.03 |
| **NETO** | **−54.39** |

En bruto la estrategia es **casi plana**. La pérdida neta es **transaccional**: 496 operaciones × 0.10% = 49.6pp de fricción. La estrategia opera en un margen **más fino que su propio costo de transacción**.

**Sensibilidad a la comisión** (mismo set de trades):
| Comisión/trade | Neto total | WR neto |
|---|---|---|
| 0.10% (taker actual) | −54.4 pp | 34.5% |
| 0.08% | −44.5 pp | 62.3% |
| 0.06% | −34.6 pp | 72.6% |
| 0.04% (maker/limit) | **−24.9 pp** | 75.6% |

El salto de WR de 34%→76% al bajar la comisión confirma que **una masa enorme de trades cierra a milímetros del breakeven**: el costo decide el signo.

### 1.3 Aporte por tipo de salida (NETO, pp)
| Salida | n | Aporte | Avg/trade |
|---|---|---|---|
| CIERRE_TRAILING | 171 | **+27.5** | +0.161% |
| BE_STOP | 217 | −4.1 | −0.019% (≈scratch) |
| STOP_LOSS | 29 | **−28.2** | −0.972% |
| CORTE_EMA7 | 79 | **−49.6** | −0.628% |

Los **sangradores son CORTE_EMA7 y STOP_LOSS** (108 trades, −77.8pp). Las 171 ganancias de trailing (+27.5pp) y los 217 BE scratch no alcanzan a compensarlos. **Asimetría neta: 1 perdedor = 1.57 ganadores** (en bruto, 1:3.7).

### 1.4 Cortes transversales (NETO)
- **Por símbolo:** SOL **−35.3pp** (WR 31.9%) peor que ETH **−19.1pp** (WR 37.2%).
- **Por sesión:** EUROPEA −31.2pp (n229, WR 32%) la peor; AMERICANA −18.3 (n184); ASIATICA −4.9 (n83, la menos mala). Todas negativas.
- **Por entrada:** SNIPER −25.9pp (WR 38.4%) ligeramente mejor que ESTANDAR −28.5pp (WR 30.3%).

### 1.5 Estabilidad temporal (OOS)
- **TRAIN −0.113%/trade vs TEST −0.106%/trade** → la pérdida neta es **estable fuera de muestra**, no artefacto de un tramo.
- **Las 9 semanas son negativas** (mean por semana de −0.02 a −0.16%). W16 y W19 las menos malas; W17 la peor (−15.8pp).

> **Conclusión Bloque 1:** en bruto la estrategia no tiene ni pierde edge; **neta, pierde de forma consistente y la causa dominante es la comisión por sobre-operar**, agravada por dos sangradores (CORTE_EMA7, STOP_LOSS). El resultado es robusto OOS.

---

## 2. Qué separa ganadores de perdedores (univariado)

### 2.1 En NETO: **ningún feature de entrada separa por sí solo**
Bucketizando cada variable (slope1h, vol_r, k, k15m, d15m, gap_ema7, velas_cruce, atr 1h/15m/5m, funding, gap_vwap, cuerpo_1h, obv, gap200, btc_trend, hora, día) en cuartiles: el **spread de expectativa neta entre buckets es de solo 0.04–0.10pp**, y **todos los buckets de todas las variables son negativos**. La comisión (0.10%) aplasta cualquier diferencia de entrada. **Implicación: no sirve agregar filtros de entrada finos — ninguno supera el costo de transacción.**

### 2.2 En la pregunta correcta (¿qué predice LLEGAR a T1 vs ser cortado?): **la volatilidad**
Comparando los 171 que llegaron a T1 (CIERRE_TRAILING) vs los 108 cortados (CORTE_EMA7+STOP_LOSS):
| Feature | T1_WIN | CUT | discrimina (|t|) |
|---|---|---|---|
| **ATR_5m** | 0.293 | 0.253 | **2.98** |
| **ATR_15m** | 0.426 | 0.375 | **2.78** |
| **ATR_1h** | 0.751 | 0.690 | **2.43** |
| **Vol_R** | 1.461 | 1.197 | **2.40** |
| slope15m | 0.185 | 0.160 | 1.88 |
| slope1h | 0.241 | 0.216 | 1.66 |
| k15m / k / velas_cruce / gap_vwap / cuerpo | ≈ | ≈ | <1.3 (sin poder) |

- Los trades que alcanzan +0.25% tienen **más volatilidad y más volumen**. En chop de baja volatilidad, +0.25% rara vez se toca y el precio oscila sobre EMA7 → CORTE_EMA7.
- El **único bucket con bruto positivo** en toda la muestra es **ATR_1h alto (>0.90%): p(T1)=44%, gross +0.063%**.
- **Hora UTC [TENTATIVO, N pequeño]:** horas 0 y 4 destacan (p(T1) 54–57%, gross +0.06/+0.09); horas 11, 14, 16, 19 las peores (gross negativo, p(T1)<30%). Útil como pista, no como filtro todavía.
- **velas_cruce 2–4** mantiene el mejor WR (43.8%, consistente con el análisis de 49 trades) pero sigue net-negativo.

> **Conclusión Bloque 2:** el poder predictivo real está en **la volatilidad (ATR/Vol_R)**, no en los osciladores. Pero ningún feature rescata la expectativa neta por sí solo — la palanca es **operar menos y solo cuando hay volatilidad**, no afinar entradas.

---

## 3. Autopsia de los cortes (CORTE_EMA7 / STOP_LOSS)

### 3.1 ¿Remontó el precio tras el corte? → **mayormente NO**
Siguiendo la trayectoria de los 108 cortes con los scans:
| Horizonte | Volvió a entrada | Alcanzó +T1 (0.25%) | MFE medio post-corte |
|---|---|---|---|
| 30 min | 7% | 5% | −0.369% |
| 60 min | 19% | 11% | −0.239% |
| 120 min | 32% | 20% | −0.062% |

Por tipo (60 min): CORTE_EMA7 volvió a entrada 23% / +T1 14%; STOP_LOSS 10% / 3%. **Los cortes en general aciertan**: el precio sigue cayendo, no rebota. Ensanchar stops mayormente **agrandaría pérdidas**, no salvaría trades.

### 3.2 Reglas de corte alternativas (evaluadas sobre los 496, NETO)
| Regla | Neto total | WR | Peor trade |
|---|---|---|---|
| **BASELINE** (CORTE_EMA7 + stop −0.85) | −54.7 | 34.5% | −0.98 |
| Quitar CORTE_EMA7 (solo stop −0.85) | **−60.8** | 37.1% | −0.99 |
| Sin corte + stop −1.5 | −54.8 | 39.9% | **−1.65** |
| Sin corte + stop −2.0 | −51.8 | 40.9% | **−2.20** |
| Sin corte + ATR stop k=1.0 (piso 0.30) | −49.7 | 32.1% | −0.87 |
| **Sin corte + stop −1.5 + time-stop 30min** | **−45.5** | 31.2% | −1.51 |

- **Quitar CORTE_EMA7 EMPEORA** (−60.8): es un **buen guardián** que sale antes de que la pérdida crezca.
- **Stops más anchos** mueven poco y **agrandan la cola** (peor trade −1.65/−2.20) → peor drawdown.
- **Lo único que mejora de forma consistente es un time-stop ~30 min** (matar trades muertos antes de que decaigan): +9pp vs baseline. Coherente con "trade >1h sin T1 = alta probabilidad de pérdida".
- **Ninguna regla de corte vuelve la estrategia positiva.** Mueven ±10pp; el piso de comisión (−49.6pp) domina.

> **Conclusión Bloque 3:** mantener CORTE_EMA7. No ensanchar stops. **Agregar un time-stop (~30–45 min)** es la única mejora robusta de salida — modesta.

---

## 4. Eficiencia del trailing

### 4.1 El trailing actual es casi irrelevante **en este régimen**
De los 171 que trailearon: pico medio post-T1 = **+0.108%** sobre T1; capturamos el **39%** de ese (ya pequeño) movimiento; dejamos +0.086% sobre la mesa. **Solo 9% de los trailing superó un pico de +0.50%; solo 1 trade superó +1.0%.**

### 4.2 Todas las variantes de trailing son indistinguibles (NETO, banda ±2pp)
| Variante | Neto total |
|---|---|
| Baseline (0.20→0.10 desde 0.40) | −54.7 |
| Fijo 0.40 (no apretar) | −53.7 |
| **ATR_15m × 0.50** | **−54.5** |
| ATR_15m × 1.0 | −53.4 |
| SUELO 0.30 | −53.4 |

⚠️ **El "trailing ATR_15M × 0.50" (que prometía +0.437% en la simulación de 18 trades) NO se materializa en 496** — es idéntico a baseline. **Era sobreajuste a pocos casos.**

> **Conclusión Bloque 4 [RÉGIMEN]:** en bajista/lateral el trailing no importa porque los movimientos no se extienden. **Es la dimensión más dependiente del régimen**: en mercado alcista con corridas grandes, un trailing más suelto/ATR sí capturaría mucho más. **Mantener el trailing simple ahora; re-evaluarlo con datos de mercado alcista.**

---

## 5. Oportunidades que no tomamos (el corazón)

### 5.1 El costo del filtro K<45
- En el **simulador solo 4 de 496 trades** tienen K<45 (el sim entra casi siempre con **K≥45**, a menudo >90 = sobrecomprado). El **bot real EXIGE K<45** → entra en el régimen opuesto (pullback en tendencia). Por eso el real hizo 7 trades y el sim 496.
- Aplicar K<45 al sim eliminaría **492 trades con netΣ = −54.0pp** → el filtro **AHORRA ~54pp**, pero **por selectividad extrema** (reduce a ~4 trades), **no porque K prediga mejores trades** (K no tiene poder predictivo sobre el resultado en los datos, §2).
- **Lectura:** dado que la comisión es el killer, la selectividad altísima del bot real (K<45) es un **rasgo protector, no un defecto**. Lo que el real consigue por accidente (operar poco) es exactamente lo que el sim necesita.
- *No se puede validar la calidad de entrada de K<45 directamente (solo 4 casos en sim).*

### 5.2 Señales bloqueadas: **todos los filtros son buenos guardianes**
401 episodios de SEÑAL_BLOQUEADA (deduplicados de 41.030 scans), simulando la entrada hipotética con las reglas de salida estándar (NETO):
| Filtro bloqueador | episodios | Neto si entrábamos | Veredicto |
|---|---|---|---|
| ASIA_COMBO (F3) | 79 | −0.110%/ep (−8.7pp) | bloquea perdedoras ✅ |
| BE_LOCK (cooldown 15min) | 173 | −0.113%/ep (−19.5pp) | bloquea perdedoras ✅ |
| VOL_R<0.30 | 149 | −0.118%/ep (−17.5pp) | bloquea perdedoras ✅ |
| **Todos** | 401 | **−45.7pp** | — |

**Ningún filtro nos cuesta ganadoras.** Entrar en lo bloqueado habría perdido −45.7pp adicionales. En este régimen, **todo lo que reduce trading ayuda al neto**. El problema NO está en las señales que descartamos, sino en las que sí tomamos.

### 5.3 ¿El mercado se movió y no lo capturamos? → **SÍ, y esto es lo central**
- **El mercado NO estuvo muerto:** rango intradía medio **3.76%** (máx 8.83%); **67 de 114 días-símbolo tuvieron corridas alcistas >1%** desde la apertura.
- **Pero la correlación entre el mejor movimiento alcista del día y el neto del bot ese día es 0.13 (nula).**
  - 14-abr: disponible **+6.86%** → bot **+0.95%** neto (una rebanada).
  - 16-abr: disponible **+6.66%** → bot **−0.70% neto** (¡gross +1.90 comido por comisión en 26 trades!).
- **La estrategia es estructuralmente incapaz de montar la tendencia aunque exista y sea grande:** T1 corta a +0.25%, EMA7 la saca del resto, reentra y vuelve a pagar comisión. Hace scalping de rebanadas mientras pasan movimientos de 5–7% a su alrededor.

**Firma de los trades que SÍ pillaron un pico >0.5% (n=16, [TENTATIVO]):** mayor ATR_1h (0.80 vs 0.73) y mayor gap200; concentrados en sesión **AMERICANA** (10/16) y horas 18/23/0.

> **Conclusión Bloque 5:** los filtros actuales son correctos (bloquean perdedoras); el K<45 protege vía selectividad. **El verdadero costo de oportunidad no son las señales bloqueadas, sino el diseño de salida (T1 diminuto + EMA7 + reentradas) que no deja capturar los movimientos grandes que el mercado sí ofreció.**

---

## 6. Síntesis y correcciones propuestas (para PROBAR EN SIMULADOR)

### 6.1 Diagnóstico en una frase
La estrategia **no tiene un problema de entradas, tiene un problema de costos y de captura**: en bruto es plana, pero **opera demasiado** (la comisión se come 49.6pp) y **corta los ganadores demasiado pronto** para montar las tendencias que el mercado sí ofreció.

### 6.2 Qué NO hacer (refutado por los datos)
- ❌ **No agregar filtros de entrada finos** (osciladores, gap, cuerpo, OBV): ninguno supera el costo de transacción (§2).
- ❌ **No quitar filtros** (ASIA, BE_LOCK, VOL_R, CORTE_EMA7): todos bloquean perdedoras (§3, §5).
- ❌ **No ensanchar stops:** agrandan la cola sin mejorar el neto (§3).
- ❌ **No subir T1 en bajista:** lo empeora (T1=0.5 → −56.7pp, WR 14%) porque las entradas no son lo bastante limpias para llegar tan lejos [RÉGIMEN] (§6.4).
- ❌ **No esperar nada del trailing ATR×0.5:** sobreajuste a 18 trades, nulo en 496 (§4).

### 6.3 Correcciones propuestas (cada una con su expectativa neta estimada y OOS)
Evaluadas como regla sobre los 496, split TRAIN/TEST:

| # | Cambio | Neto total | WR | TRAIN | TEST | Confianza |
|---|---|---|---|---|---|---|
| C1 | **Piso de volatilidad: ATR_15m ≥ 0.45 en entrada** | −14.3pp (de −54.4) | 42.9% | −7.2 | −7.1 | **Alta** (OOS estable) |
| C2 | **Time-stop ~45 min** (cerrar si no pasó BE) | −47.7pp | 32.3% | −28.5 | −19.2 | Media |
| C3 | **Entradas limit/maker** (comisión 0.05→0.02 por lado) | −24.9pp | 75.6% | −13.4 | −11.5 | **Alta** (aritmético) |
| **R1** | **C1 + C2 juntos (taker actual)** | **−11.2pp** | 41.2% | −8.3 | **−2.8** | **Alta** |
| **R2** | **C1 + C2 + C3 (maker)** | **−0.3pp (breakeven)** | 76.4% | −3.0 | **+2.7** | Media-alta |
| R4 | ATR_15m≥0.50 + C2 + C3 (más selectivo) | −0.6pp | 75.2% | −1.4 | +0.9 | Media |

### 6.4 Configuración recomendada para el simulador
**Probar en el simulador (NO en real) esta configuración, en este orden de prioridad:**

1. **[PRIORIDAD 1] Piso de volatilidad en entrada — `ATR_15m ≥ 0.45`** (o `ATR_1h ≥ 0.60`). Es el cambio de **entrada** más sólido: reduce ~63% de los trades (los de baja volatilidad que solo pagaban comisión), sube WR a 43% y es **estable OOS** (train ≈ test). Solo o combinado, recorta la pérdida a la mitad o más.

2. **[PRIORIDAD 1] Reducir el costo por trade — pasar las entradas a órdenes limit (maker)** en lugar de market (taker). Baja la comisión de ~0.10% a ~0.04–0.05% round-trip. Es el **lever más grande y robusto** (aritmético, no depende del régimen). *Riesgo a vigilar: las limit pueden no ejecutarse en movimientos rápidos → medir la tasa de fill en el sim.*

3. **[PRIORIDAD 2] Time-stop ~40–45 min** para trades que no superaron BE (mantener CORTE_EMA7 y stop −0.85 como están). Mejora modesta y robusta; mata trades muertos.

4. **Mantener sin cambios:** todos los filtros guardianes (ASIA/BE_LOCK/VOL_R), CORTE_EMA7, stop −0.85, T1=0.25 y el trailing actual.

**Expectativa estimada del paquete (C1+C2+C3 = R2): de −0.110%/trade a ≈ 0.00%/trade (breakeven), con TEST OOS +2.7pp.**

### 6.5 Lectura honesta del resultado
- Con la **comisión taker actual, ninguna configuración es rentable**; la mejor robusta (R1) lleva de −54pp a **−11pp** — gran mejora, pero todavía sangra.
- **El breakeven exige bajar el costo de transacción (maker).** Llegar a breakeven en **2 meses de mercado bajista/lateral** es un **buen** resultado: implica que en un régimen neutro o alcista la misma configuración tendría sesgo positivo.
- **[RÉGIMEN]** Todo esto se midió en bajista. Las dos cosas que cambiarían a favor en un alcista: (a) subir T1 / aflojar trailing para **montar tendencias** (hoy contraproducente, mañana clave), y (b) más días con corridas >1% capturables. **Recomendación: re-correr este análisis completo cuando haya ≥200 trades en mercado alcista antes de tocar T1/trailing.**
- Próximo paso sugerido: implementar **C1 + C3 (+ C2)** en el simulador, dejar correr ≥200 trades, y comparar la expectativa neta real contra el −0.110%/trade de esta línea base.

---

### Apéndice — trazabilidad
- Universo y PnL: `trades_sim.parquet` filtrado `estado==COMPLETO & 15≤semana≤23` (n=496).
- Motor de re-simulación validado al 99.6% contra `motivo_cierre` real.
- Trayectorias post-corte y contrafácticos: `scans_sim/2026-W15..W23.parquet`.
- Señales bloqueadas: `events_scan_sim.parquet` (tipo SENAL_BLOQUEADA, W15→W23, 401 episodios deduplicados).
- Comisión 0.10% = supuesto del proyecto (`CONTEXT.md` §6.1, SL_COMISION). Sensibilidad reportada en §1.2.
