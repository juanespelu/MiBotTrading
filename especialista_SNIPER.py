import pandas as pd
import numpy as np
from test_conexion import exchange

def analizar_sniper(simbolo, k_lim=45, ma_tipo="SMA"):
    # Diccionario inicial con todos los campos necesarios para el Bot Maestro
    res = {
        'p': 0, 'k': 0, 'd': 0,
        # 1h EMAs
        'ema5': 0, 'ema5_prev': 0, 'ema7': 0, 'ema7_prev': 0,
        'ma50': 0, 'ma200': 0, 'pendiente_7': 0, 'vol_r': 0, 'gap200': 0,
        # 15min EMAs
        'ema5_15m': 0, 'ema7_15m': 0,
        'slope_ema5_15m': 0,
        'cruce_15m': '',
        'velas_desde_cruce': -1,
        # ATR multi-timeframe (para SL y trailing dinámico)
        'atr_1h': 0,      # ATR(14) en 1H — para SL inicial
        'atr_15m': 0,     # ATR(14) en 15m — para trailing post-T1
        'atr_5m': 0,      # ATR(14) en 5m  — trailing fino (mercados volátiles)
        # OHLC de la vela actual — contexto del rango en curso
        'h_1h': 0,        # máximo de la vela 1H actual
        'l_1h': 0,        # mínimo de la vela 1H actual
        'h_15m': 0,       # máximo de la vela 15m actual
        'l_15m': 0,       # mínimo de la vela 15m actual
        # Funding rate — riesgo de saturación de longs (FILTRO activo)
        'funding_rate': 0.0,     # tasa actual (ej: 0.0003 = 0.03%)
        'funding_alto': False,   # True si |funding| > UMBRAL_FUNDING
        # VWAP del día — precio justo institucional (LOG)
        'vwap': 0.0,             # VWAP calculado con velas 1H del día
        'gap_vwap': 0.0,         # % sobre/bajo VWAP (positivo = por encima)
        # Estocástico 15m — velocidad del giro en TF corto (LOG)
        'k_15m': 50.0,
        'd_15m': 50.0,
        'k_15m_mayor_d': False,
        # Cuerpo de vela 1H (LOG) — calidad de la señal
        'cuerpo_1h': 0.0,        # |C-O|/(H-L): 1.0=vela perfecta, 0=doji
        'vela_alcista_1h': False,
        # OBV slope (LOG) — presión compradora acumulada
        'obv_slope': 0.0,
        # Contexto BTC
        'btc_precio': 0, 'btc_slope': 0, 'btc_trend': '',
        'block': '', 'error': False
    }
    try:
        # Fetch de velas (1h como tienes configurado)
        velas = exchange.fetch_ohlcv(simbolo, timeframe='1h', limit=250)
        df = pd.DataFrame(velas, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        c = df['c'].astype(float)
        v = df['v'].astype(float)
        
        # EMA7 y Pendiente (Diferencia porcentual entre última y penúltima EMA7)
        df['ema7'] = c.ewm(span=7, adjust=False).mean()
        p7 = ((df['ema7'].iloc[-1] - df['ema7'].iloc[-2]) / df['ema7'].iloc[-2]) * 100

        # EMA5 — para detectar cruces con EMA7 (señal de inicio/fin de impulso)
        df['ema5'] = c.ewm(span=5, adjust=False).mean()
        
        # Medias Móviles para filtros Macro
        df['ma50'] = c.rolling(window=50).mean()
        df['ma200'] = c.rolling(window=200).mean()
        
        # Volumen Relativo (Vol_R): Actual vs media de 20 periodos
        vol_media = v.rolling(window=20).mean()
        v_rel = v.iloc[-1] / vol_media.iloc[-1] if vol_media.iloc[-1] > 0 else 1.0

        # Estocástico (14, 3)
        low_min = df['l'].rolling(window=14).min()
        high_max = df['h'].rolling(window=14).max()
        df['k'] = 100 * (c - low_min) / (high_max - low_min)
        df['d'] = df['k'].rolling(window=3).mean()
        
        # Distancia a la MA200 (Gap200)
        precio_actual = c.iloc[-1]
        m200 = df['ma200'].iloc[-1]
        distancia_200 = ((precio_actual - m200) / m200) * 100 if m200 > 0 else 0

        # --- VWAP del día (LOG) — precio justo institucional ─────────────────
        # VWAP = suma(precio_típico × volumen) / suma(volumen) desde inicio del día
        # Calculado con las velas 1H que ya tenemos — 0 requests extra
        vwap = gap_vwap = 0.0
        try:
            from datetime import datetime as _dt
            hoy = _dt.utcnow().date()
            # filtrar solo velas del día actual UTC
            df_hoy = df[pd.to_datetime(df['t'], unit='ms').dt.date == hoy].copy()
            if len(df_hoy) < 1:
                df_hoy = df.tail(8)  # fallback: últimas 8 velas
            precio_tipico = (df_hoy['h'].astype(float) + df_hoy['l'].astype(float) + df_hoy['c'].astype(float)) / 3
            vol_hoy = df_hoy['v'].astype(float)
            sum_vol = vol_hoy.sum()
            vwap = round(float((precio_tipico * vol_hoy).sum() / sum_vol), 6) if sum_vol > 0 else precio_actual
            gap_vwap = round((precio_actual - vwap) / vwap * 100, 4) if vwap > 0 else 0.0
        except Exception:
            vwap = precio_actual
            gap_vwap = 0.0

        # --- Cuerpo de vela 1H + OBV (LOG) ─────────────────────────────────────
        cuerpo_1h = 0.0
        vela_alcista_1h = False
        obv_slope = 0.0
        try:
            o1h    = df['o'].astype(float)
            h1h    = df['h'].astype(float)
            l1h    = df['l'].astype(float)
            rango_v = h1h.iloc[-1] - l1h.iloc[-1]
            cuerpo_1h = round(abs(c.iloc[-1] - o1h.iloc[-1]) / rango_v, 4) if rango_v > 0 else 0.0
            vela_alcista_1h = bool(c.iloc[-1] > o1h.iloc[-1])
            # OBV — acumulado volumen direccional, pendiente de últimas 5 velas
            obv_dir = np.where(c.diff() > 0, v, np.where(c.diff() < 0, -v, 0))
            obv_series = pd.Series(obv_dir).cumsum()
            if len(obv_series) >= 5:
                obv_slope = round(float((obv_series.iloc[-1] - obv_series.iloc[-5]) / (abs(obv_series.iloc[-5]) + 1) * 100), 4)
        except Exception:
            pass

        # --- ATR(14) en 1H --- usando velas ya fetcheadas, 0 requests extra ---
        # ATR real = media de True Range(14): max(H-L, |H-Cprev|, |L-Cprev|)
        atr_1h = 0.0
        h_1h = l_1h = 0.0
        try:
            if len(df) >= 15:
                h1 = df['h'].astype(float)
                l1 = df['l'].astype(float)
                c1 = df['c'].astype(float)
                tr1 = pd.concat([
                    h1 - l1,
                    (h1 - c1.shift()).abs(),
                    (l1 - c1.shift()).abs()
                ], axis=1).max(axis=1)
                atr_raw_1h = tr1.rolling(window=14).mean().iloc[-1]
                atr_1h = round(float(atr_raw_1h) / precio_actual * 100, 4) if not pd.isna(atr_raw_1h) else 0.0
                h_1h = round(float(h1.iloc[-1]), 6)
                l_1h = round(float(l1.iloc[-1]), 6)
        except Exception:
            atr_1h = 0.0

        # --- ANÁLISIS 15 MIN (EMA5/EMA7 para detección de cruces ágiles) ---
        ema5_15m = ema7_15m = slope_ema5_15m = 0
        cruce_15m = ''
        velas_desde_cruce = -1
        atr_15m = h_15m = l_15m = 0.0
        k_15m = d_15m = 50.0
        k_15m_mayor_d = False
        cuerpo_15m = vela_alcista_15m = 0.0
        try:
            # params='future' fuerza el mercado correcto en conexiones de futuros
            velas_15m = exchange.fetch_ohlcv(simbolo, timeframe='15m', limit=100, params={'price': 'mark'})
            if not velas_15m or len(velas_15m) < 10:
                raise ValueError(f"Datos 15m insuficientes: {len(velas_15m) if velas_15m else 0} velas")
            df15 = pd.DataFrame(velas_15m, columns=['t', 'o', 'h', 'l', 'c', 'v'])
            c15 = df15['c'].astype(float)
            df15['ema5'] = c15.ewm(span=5, adjust=False).mean()
            df15['ema7'] = c15.ewm(span=7, adjust=False).mean()

            ema5_15m = df15['ema5'].iloc[-1]
            ema7_15m = df15['ema7'].iloc[-1]

            # Pendiente EMA5 en 15min
            slope_ema5_15m = ((ema5_15m - df15['ema5'].iloc[-2]) / df15['ema5'].iloc[-2]) * 100

            # Detectar cruce actual y contar velas desde el último cruce
            df15['encima'] = df15['ema5'] > df15['ema7']
            cruces = df15['encima'].diff().fillna(False)

            # Cruce en la última vela cerrada
            if cruces.iloc[-2]:
                cruce_15m = 'CRUCE_ALCISTA' if df15['encima'].iloc[-2] else 'CRUCE_BAJISTA'

            # Velas desde el último cruce (buscando hacia atrás)
            indices_cruce = cruces[cruces == True].index.tolist()
            if indices_cruce:
                ultimo_cruce_idx = indices_cruce[-1]
                pos_ultimo = df15.index.get_loc(ultimo_cruce_idx)
                velas_desde_cruce = len(df15) - 1 - pos_ultimo

            # ── K(14,3) en 15m — 0 requests extra ─────────────────────
            k_15m = d_15m = 50.0
            k_15m_mayor_d = False
            if len(df15) >= 14:
                low15  = df15['l'].astype(float).rolling(14).min()
                high15 = df15['h'].astype(float).rolling(14).max()
                rng15  = high15 - low15
                k_raw  = 100 * (c15 - low15) / rng15.replace(0, np.nan)
                d_raw  = k_raw.rolling(3).mean()
                k_15m  = round(float(k_raw.iloc[-1]), 2) if not pd.isna(k_raw.iloc[-1]) else 50.0
                d_15m  = round(float(d_raw.iloc[-1]), 2) if not pd.isna(d_raw.iloc[-1]) else 50.0
                k_15m_mayor_d = bool(k_15m > d_15m)

            # ── Cuerpo de vela 15m — calidad de señal ────────────────────
            cuerpo_15m = 0.0
            vela_alcista_15m = False
            if len(df15) >= 2:
                o15  = df15['o'].astype(float)
                h15v = df15['h'].astype(float)
                l15v = df15['l'].astype(float)
                rango_vela = h15v.iloc[-2] - l15v.iloc[-2]
                cuerpo_15m = abs(c15.iloc[-2] - o15.iloc[-2]) / rango_vela if rango_vela > 0 else 0.0
                vela_alcista_15m = bool(c15.iloc[-2] > o15.iloc[-2])

            # ATR(14) en 15m — mismas velas, 0 requests extra
            if len(df15) >= 15:
                h15 = df15['h'].astype(float)
                l15 = df15['l'].astype(float)
                c15_close = df15['c'].astype(float)
                tr15 = pd.concat([
                    h15 - l15,
                    (h15 - c15_close.shift()).abs(),
                    (l15 - c15_close.shift()).abs()
                ], axis=1).max(axis=1)
                atr_raw_15m = tr15.rolling(window=14).mean().iloc[-1]
                atr_15m = round(float(atr_raw_15m) / precio_actual * 100, 4) if not pd.isna(atr_raw_15m) else 0.0
                h_15m = round(float(h15.iloc[-1]), 6)
                l_15m = round(float(l15.iloc[-1]), 6)
        except Exception as e15:
            with open('log_sniper_sim.txt', 'a', encoding='utf-8') as _f:
                _f.write(f"[ERROR_15M] {simbolo}: {e15}\n")

        # --- CONTEXTO BTC ---
        btc_precio = btc_slope = 0
        btc_trend = ''
        try:
            if simbolo != 'BTC/USDT:USDT':
                import threading
                resultado_btc = [None]
                def _fetch_btc():
                    try:
                        resultado_btc[0] = exchange.fetch_ohlcv(
                            'BTC/USDT:USDT', timeframe='15m', limit=10
                        )
                    except Exception as e:
                        resultado_btc[0] = e
                t = threading.Thread(target=_fetch_btc, daemon=True)
                t.start()
                t.join(timeout=8)
                velas_btc = resultado_btc[0]
                if isinstance(velas_btc, Exception):
                    raise velas_btc
                if not velas_btc or len(velas_btc) < 5:
                    raise ValueError(f"Datos BTC insuficientes: {len(velas_btc) if velas_btc else 0} velas")
                df_btc = pd.DataFrame(velas_btc, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                c_btc = df_btc['c'].astype(float)
                df_btc['ema7'] = c_btc.ewm(span=7, adjust=False).mean()
                btc_precio = c_btc.iloc[-1]
                btc_slope = ((df_btc['ema7'].iloc[-1] - df_btc['ema7'].iloc[-2]) / df_btc['ema7'].iloc[-2]) * 100
                btc_trend = 'ALCISTA' if btc_slope > 0.02 else ('BAJISTA' if btc_slope < -0.02 else 'LATERAL')
        except Exception as ebtc:
            with open('log_sniper_sim.txt', 'a', encoding='utf-8') as _f:
                _f.write(f"[ERROR_BTC]: {ebtc}\n")

        # --- FUNDING RATE — señal de saturación de longs (FILTRO activo) ────
        # Alto funding = demasiados longs apalancados = rebotes sin continuación
        # Umbral: 0.05% por período (= 0.15%/día = muy caro mantener longs)
        # Bloquea entradas ESTANDAR cuando hay saturación. SNIPER puede seguir.
        UMBRAL_FUNDING = 0.0005   # 0.05% — ajustar cuando tengamos datos propios
        funding_rate = 0.0
        funding_alto = False
        try:
            fr_data = exchange.fetch_funding_rate(simbolo)
            if fr_data and 'fundingRate' in fr_data:
                funding_rate = round(float(fr_data['fundingRate']), 6)
                funding_alto = abs(funding_rate) > UMBRAL_FUNDING
        except Exception:
            funding_rate = 0.0
            funding_alto = False

        # --- ATR 5m — 1 fetch extra por símbolo, granularidad fina ---
        atr_5m = 0.0
        try:
            velas_5m_sym = exchange.fetch_ohlcv(simbolo, timeframe='5m', limit=20)
            if velas_5m_sym and len(velas_5m_sym) >= 15:
                df5 = pd.DataFrame(velas_5m_sym, columns=['t','o','h','l','c','v'])
                h5 = df5['h'].astype(float)
                l5 = df5['l'].astype(float)
                c5 = df5['c'].astype(float)
                tr5 = pd.concat([
                    h5 - l5,
                    (h5 - c5.shift()).abs(),
                    (l5 - c5.shift()).abs()
                ], axis=1).max(axis=1)
                atr_raw_5m = tr5.rolling(window=14).mean().iloc[-1]
                atr_5m = round(float(atr_raw_5m) / precio_actual * 100, 4) if not pd.isna(atr_raw_5m) else 0.0
        except Exception:
            atr_5m = 0.0

        # Actualización del diccionario de resultados
        res.update({
            'p': precio_actual, 
            'k': df['k'].iloc[-1], 
            'd': df['d'].iloc[-1],
            'ema5': df['ema5'].iloc[-1],
            'ema5_prev': df['ema5'].iloc[-2],
            'ema7': df['ema7'].iloc[-1],
            'ema7_prev': df['ema7'].iloc[-2],
            'ma50': df['ma50'].iloc[-1], 
            'ma200': m200, 
            'pendiente_7': p7,
            'vol_r': round(v_rel, 2),
            'gap200': round(distancia_200, 2),
            # EMA7 gap y cruce 1h
            'gap_ema7': round(((precio_actual - df['ema7'].iloc[-1]) / df['ema7'].iloc[-1]) * 100, 4) if df['ema7'].iloc[-1] > 0 else 0,
            'cruce_1h': 'CRUCE_ALCISTA' if (df['ema5'].iloc[-1] > df['ema7'].iloc[-1] and df['ema5'].iloc[-2] <= df['ema7'].iloc[-2]) else ('CRUCE_BAJISTA' if (df['ema5'].iloc[-1] < df['ema7'].iloc[-1] and df['ema5'].iloc[-2] >= df['ema7'].iloc[-2]) else ''),
            'precio_sobre_ema7': precio_actual > df['ema7'].iloc[-1],
            # 15min
            'ema5_15m': round(ema5_15m, 4),
            'ema7_15m': round(ema7_15m, 4),
            'slope_ema5_15m': round(slope_ema5_15m, 4),
            'cruce_15m': cruce_15m,
            'velas_desde_cruce': velas_desde_cruce,
            # BTC
            'btc_precio': round(btc_precio, 2),
            'btc_slope': round(btc_slope, 4),
            'btc_trend': btc_trend,
            # ATR multi-timeframe
            'atr_1h':  atr_1h,
            'atr_15m': atr_15m,
            'atr_5m':  atr_5m,
            # OHLC vela actual
            'h_1h': h_1h,   'l_1h': l_1h,
            'h_15m': h_15m, 'l_15m': l_15m,
            # Funding rate (FILTRO)
            'funding_rate':  funding_rate,
            'funding_alto':  funding_alto,
            # VWAP (LOG)
            'vwap':          vwap,
            'gap_vwap':      gap_vwap,
            # K(15m) (LOG — filtro pendiente calibración)
            'k_15m':         k_15m,
            'd_15m':         d_15m,
            'k_15m_mayor_d': k_15m_mayor_d,
            # Cuerpo de vela (LOG)
            'cuerpo_1h':     cuerpo_1h,
            'vela_alcista_1h': vela_alcista_1h,
            # OBV (LOG)
            'obv_slope':     obv_slope,
        })

        # --- CONSTRUCCIÓN DE BLOQUEOS ---
        bloqueos = []
        if res['p'] < res['ma50']: bloqueos.append("P<MA50")
        if res['p'] < res['ma200']: bloqueos.append("P<MA200")
        
        # Filtro de momentum (si la pendiente es baja, aplicamos estocástico estricto)
        if p7 < 0.10:
            if res['k'] > k_lim: bloqueos.append(f"K>{k_lim}")
            if res['k'] < res['d']: bloqueos.append("K<D")

        if res['p'] < res['ema7']: bloqueos.append("P<EMA7")
        if p7 <= 0.05: bloqueos.append("PLANA")
        # FUNDING_ALTO — no bloquea en el especialista, lo gestiona el bot
        # según tipo de señal (ESTANDAR bloqueado, SNIPER permitido)
        if funding_alto: bloqueos.append(f"FUNDING_ALTO:{funding_rate:.4f}")
        
        res['block'] = " | ".join(bloqueos)
        
    except Exception as e:
        res['error'] = True
        print(f"Error en especialista: {e}")
        
    return res