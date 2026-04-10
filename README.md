# MiBotTrading

Sistema de trading algorítmico para Binance Futures Perpetuos (USDT-M).

## Descripción

Proyecto de bots de trading automatizado con dos sistemas operando en paralelo:
- **Bot Real V4.0**: Opera con dinero real en Binance
- **Simulador V7.5**: Paper trading para pruebas y optimización

## Archivos Principales

### Bots
- `bot_maestro_v4.py` - Bot principal con órdenes reales
- `bot_SNIPER_SIM.py` - Simulador paper trading  
- `especialista_v3.py` - Análisis técnico para bot real
- `especialista_SNIPER.py` - Análisis técnico para simulador
- `test_conexion.py` - Conexión ccxt compartida

### Configuración
- `estado_bot.json` - Estado del bot real
- `estado_sniper_sim.json` - Estado del simulador
- `.env` - Variables de entorno (NO incluido en repo)

### Documentación
- `CLAUDE.md` - Reglas y configuración del proyecto
- `CONTEXT.md` - Estado completo del sistema
- `SESSION_LOG.md` - Registro de sesiones de desarrollo

## Configuración

### 1. Variables de Entorno
Crear archivo `.env` con:
```env
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_SECRET_KEY=tu_secret_key_aqui
TELEGRAM_TOKEN=tu_bot_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
```

### 2. Dependencias
```bash
pip install ccxt requests python-dotenv
```

### 3. Ejecutar
```bash
# Bot real (¡CUIDADO! Opera con dinero real)
python bot_maestro_v4.py

# Simulador
python bot_SNIPER_SIM.py
```

## Estructura

```
├── logs_real/              # Logs del bot real
├── logs_simulador/         # Logs del simulador  
├── historial/              # Archivos históricos
│   ├── bots/              # Versiones anteriores
│   └── logs_desarrollo/   # Logs de desarrollo
└── venv/                  # Entorno virtual (no en repo)
```

## Características

### Bot Real V4.0
- Órdenes reales en Binance
- Stop Loss real en exchange
- Notificaciones Telegram
- Una posición a la vez
- Trailing escalonado 4 niveles

### Simulador V7.5  
- Paper trading matemático
- Múltiples posiciones simultáneas
- Notificaciones Telegram mínimas
- Trailing 2 niveles
- Reset diario de estadísticas

## Seguridad

⚠️ **IMPORTANTE**: 
- Nunca subir archivo `.env` al repositorio
- Verificar API keys antes de usar bot real
- Probar siempre en simulador primero

## Estado del Proyecto

- ✅ Ambos bots operativos
- ✅ 49 trades reales analizados  
- ✅ Sistema de logging robusto
- ✅ Notificaciones Telegram implementadas
- 🔄 En migración a VPS Contabo

## Licencia

Proyecto privado - Uso personal únicamente.