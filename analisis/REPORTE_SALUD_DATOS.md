# Reporte de Salud de Datos — MiBotTrading
**Fecha:** 4 de junio de 2026
**Fuente:** `analisis_VPS_2026-06-04/` (extracto íntegro del VPS, SHA256 verificado)
**Alcance:** completitud y confiabilidad de los datos. NO incluye métricas de estrategia (paso siguiente).

---

## 1. Muestra usable real

### Simulador
| Categoría | N | Nota |
|-----------|---|------|
| Marcadores de entrada (con ID) | 1552 | (1561 en el archivo de resultados) |
| **COMPLETO** (entrada + cierre explícito) | **503–512** | según fuente (scans/resultados) |
| RECUPERADO vía EN_POSICION | **0** | no aplica (ver §2) |
| DESCONOCIDO / sin posición real | **1049** | **todos en W13 (era pre-VPS)** |
| **Muestra moderna usable (W15→W23)** | **496** | **100% completa** |

### Bot real
| Categoría | N |
|-----------|---|
| Trades completos (entrada+salida) | **7** | 
| Última operación | 3 de mayo |

**Conclusión:** la muestra confiable del simulador es de **496 trades completos (W15→W23)**, más que suficiente para superar el umbral de 200 de la hoja de ruta. El bot real solo tiene 7.

---

## 2. ¿Los ~512 completos son muestra justa o sesgada? → **JUSTA (no sesgada)**

La intuición inicial ("512 completos de 1561 = muestra del 33%, posiblemente sesgada") **es incorrecta**. La realidad:

- Las **1049 entradas sin cierre están 100% concentradas en W13** (era pre-VPS, 24–29 marzo). En esa semana hubo **1056 marcadores `>>> ENTRADA` pero solo 7 posiciones reales** trackeadas/cerradas (0.7%). Las otras 1049 son **entradas "fantasma"** del logging de la versión vieja — no son trades reales con salida perdida, son artefactos de log. **No hay nada que reconstruir** (por eso RECUPERADO=0: no existían posiciones detrás).
- **Desde W15 (post-migración VPS, 10-abr): el 100% de las entradas tiene cierre explícito.** Cero faltantes en W15, W16, W17, W18, W19, W20, W21, W22, W23.

Por lo tanto los 496 trades modernos **no son una submuestra** de una población mayor: son la **población completa** de trades reales del simulador en la era confiable. **Sesgo de supervivencia: ninguno** en la era moderna.

**Recomendación:** excluir W13 del análisis (era obsoleta, distinta versión, datos rotos). Trabajar con W15→W23.

---

## 3. Diagnóstico de salidas faltantes → **SISTEMÁTICO (por era), no aleatorio**

- 100% de los faltantes en W13. Causa: versión pre-VPS con logging incompleto (registraba entradas pero casi nunca cierres ni tracking por ID), agravado por reinicios/apagones.
- Continuidad de timestamps confirma la frontera de era:
  - **Pre-VPS** (antes del 10-abr): intermitente. Downtime en huecos: **real 433h, sim 364h**. El hueco de **260h (29-mar→9-abr, 11 días apagado)** explica por qué **falta el archivo W14 del simulador** (el bot no corrió esa semana ISO completa).
  - **Post-VPS** (10-abr en adelante): **cero huecos > 5 min**. Cadencia mediana real 6.0 s, sim 2.0 s (coincide con el diseño: 5 s real, 3 s/0.5 s adaptativo sim).

---

## 4. Anomalía VOL_R ~0 → **explicada y benigna**

| Bot | vol_r == 0.00 | vol_r ≤ 0.01 |
|-----|---------------|--------------|
| Real | 0.56% | 1.93% |
| Sim | 0.54% | 1.87% |

- **Causa:** efecto de vela horaria nueva. `vol_r = volumen_actual / media_móvil_20`; al abrir cada vela 1H el volumen acumulado es ~0 → ratio ~0. Se concentra en el **minuto :00–:02 de cada hora** (distribución decae 21036 → 10418 → 3488 …) y se normaliza enseguida.
- **No es dato corrupto:** el 100% de esas filas tiene el resto del scan válido (precio, K, etc. presentes). Es solo el volumen, transitorio.
- **Implicación operativa (no de calidad):** el filtro `Vol_R ≥ 0.30x` rechaza entradas en los primeros ~2 min de cada hora por este artefacto. Afecta ~1.9% del tiempo. A tener en cuenta en el análisis de oportunidades.

---

## 5. Cobertura temporal

| Bot | Desde | Hasta | Semanas ISO | Huecos en era moderna |
|-----|-------|-------|-------------|------------------------|
| Real | 19-mar | 4-jun | W12–W23 (completas) | 0 |
| Sim | 24-mar | 4-jun | W13, **(W14 ausente)**, W15–W23 | 0 |

---

## 6. Split crudo Ganados/Perdidos — SOLO RECONCILIACIÓN (no conclusión de estrategia)

### Simulador modernos (W15→W23, 496 completos)
- Por tipo de cierre: **CIERRE_TRAILING 171** (llegaron a T1) | **SALIDA 325** (BE_STOP 217, CORTE_EMA7 79, STOP_LOSS 29).
- Split crudo de PnL (solo SALIDA, que tienen campo `PnL:`): **G=213 / P=112**.
  - ⚠️ Los 171 CIERRE_TRAILING **no tienen campo `PnL:` único** — su resultado se compone de `t1_pct` (50% a +T1) + `trail_pct` (50% al trailing). Para el análisis hay que **computar su PnL** desde esos dos componentes, no leerlo directo. (Esto NO es un problema de datos, es estructura del log.)

### Bot real (7 trades)
- Split crudo: **G=2 / P=5**. Ninguno llegó a T1. Última operación 3-may.

*(El análisis de rentabilidad, expectativa matemática y calibración de filtros es el paso siguiente.)*

---

## 7. Caveats de estructura para el análisis (no son errores)

1. **W13 = era obsoleta** → excluir.
2. **W14 ausente** = bot apagado, no pérdida de datos.
3. **PnL de CIERRE_TRAILING** = computar desde `t1_pct + trail_pct`.
4. **Formatos distintos real vs sim** (nombres de campo) → ya normalizados en los datasets parquet.
5. **API keys hardcodeadas** en `test_conexion.py` (hallazgo lateral de seguridad, no de datos) → revisar aparte.
