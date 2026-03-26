# BetBot - Telegram Bot for Football Predictions

Sistema avanzado de predicción de fútbol usando modelos matemáticos (Poisson + Elo) integrado con soccerdata para datos en tiempo real.

## 🚀 Características principales

### 📅 Calendario y Fixtures
- **Obtención automática** de partidos usando **soccerdata** (FBref)
- **Selección por fecha**: Hoy, mañana, o fecha específica
- **Ligas top**: Big 5 European Leagues (Premier League, La Liga, Serie A, Bundesliga, Ligue 1)
- **Interfaz intuitiva** con botones inline de Telegram

### 🎯 Análisis de partidos
- **Modelo Poisson** para distribución de goles
- **Sistema Elo** para rating de equipos
- **Estadísticas avanzadas** de soccerdata (xG, forma reciente, head-to-head)
- **Múltiples tipos de apuesta**: 1X2, Over/Under 2.5, BTTS, etc.

### 💡 Recomendaciones inteligentes
- **Probabilidades calculadas** con alta precisión
- **Recomendaciones automáticas** basadas en umbrales de confianza
- **Explicación transparente** del razonamiento
- **Combinadas automáticas** con mejor value

### 🤖 Bot de Telegram
- **Comandos principales**:
  - `/calendario` - Ver y seleccionar partidos por fecha
  - `/jornada` - Análisis rápido de jornada
  - `/combinada` - Generar apuestas combinadas
- **Modos de análisis**: Automático (todos los partidos) o Manual (selección personalizada)
- **Respuestas formateadas** con emojis y HTML

## 🛠️ Tecnologías utilizadas

- **Python 3.12+**
- **soccerdata 1.8.8** - Para datos de fútbol de FBref
- **python-telegram-bot 21.6** - Framework del bot
- **pandas & numpy** - Manipulación de datos
- **scipy** - Distribuciones estadísticas
- **seleniumbase** - Web scraping (para soccerdata)

## 📦 Instalación

### 1. Clona el repositorio
```bash
git clone https://github.com/tu-usuario/bet.git
cd bet
```

### 2. Instala dependencias
```bash
# Dependencias principales
pip install -r requirements.txt

# Dependencias específicas del bot
pip install -r requirements.bot.txt
```

### 3. Configura variables de entorno
Crea un archivo `.env` con:
```env
TELEGRAM_BOT_TOKEN=tu_token_aqui
```

## 🚀 Uso del bot

### Iniciar el bot
```bash
python telegram_bot.py
```
O usa los scripts preparados:
- **Windows**: `run_telegram_bot.bat`
- **PowerShell**: `run_telegram_bot.ps1`

### Comandos disponibles
- `/start` - Iniciar el bot y ver ayuda
- `/calendario` - Seleccionar fecha y ver partidos
- `/jornada` - Análisis rápido de partidos del día
- `/combinada` - Generar combinadas automáticas
- `/help` - Ver todos los comandos disponibles

### Flujo típico de uso
1. **Seleccionar fecha**: Usa `/calendario` y elige "Hoy", "Mañana" o una fecha específica
2. **Ver partidos**: El bot muestra todos los partidos programados
3. **Elegir modo**:
   - **Automático**: Analiza todos los partidos
   - **Manual**: Selecciona partidos específicos
4. **Obtener recomendaciones**: Recibe análisis detallado con probabilidades y picks recomendados

## 📊 Ejemplo de respuesta

```
🎯 Análisis automático para 2026-03-26

🏟️ Real Madrid vs Barcelona
✅ Recomendación: Over 2.5 (67.3% de probabilidad)
📊 Probabilidades: 1: 45.2% | X: 24.1% | 2: 30.7%
💡 Razonamiento: Modelo Poisson + forma reciente

🎰 Combinada automática (3 legs):
Probabilidad combinada: 23.8% | Cuota estimada: 4.20
```

## 🔧 Configuración avanzada

### Ligas soportadas
Por defecto usa "Big 5 European Leagues Combined", pero puedes modificar en `src/soccerdata_fixtures.py`:
```python
leagues = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A", "GER-Bundesliga", "FRA-Ligue 1"]
```

### Temporadas
Configura la temporada actual en los handlers:
```python
seasons = "2526"  # Para 2025-2026
```

### Umbrales de confianza
Ajusta en `prediction_service.py`:
```python
min_prob = 0.55  # Mínima probabilidad para recomendaciones
```

## 🐛 Solución de problemas

### Error 403 en soccerdata
FBref bloquea requests automatizados. Soluciones:
1. **Usar VPN** o proxy
2. **Datos cacheados**: `force_cache=True`
3. **Temporada anterior**: Cambiar `seasons` a "2324"

### Dependencias conflictivas
Si hay problemas con urllib3:
```bash
pip install --upgrade --force-reinstall soccerdata==1.8.8 seleniumbase==4.38.2
```

### Bot no responde
1. Verifica el token de Telegram en `.env`
2. Asegúrate de que `allowed_updates` incluya `"callback_query"`
3. Revisa logs del bot

## 📈 Mejoras futuras

- [ ] Integración con APIs de cuotas en tiempo real
- [ ] Modelo de machine learning avanzado
- [ ] Análisis de lesiones y suspensions
- [ ] Estadísticas de jugadores individuales
- [ ] Backtesting histórico completo
- [ ] Notificaciones push para partidos importantes

## ⚠️ Descargo de responsabilidad

Este bot es para **fines educativos y de entretenimiento**. Las predicciones son estimaciones matemáticas y no garantizan resultados. El fútbol tiene incertidumbre inherente. **Apusta responsablemente** y nunca arriesgues más de lo que puedes permitirte perder.

## 📄 Licencia

MIT License - ver LICENSE para detalles.

## Ejecucion

```bash
streamlit run app_streamlit.py
```

O simplemente:
- **Windows**: Doble clic en `run.bat`
- **PowerShell**: `.\run.ps1`

La API key se carga automáticamente desde `.env`.

## Bot de Telegram

1. Crea un bot con `@BotFather` y copia tu token.
2. En `.env` define:

```bash
API_FOOTBALL_KEY=TU_API_KEY
TELEGRAM_BOT_TOKEN=TU_TELEGRAM_BOT_TOKEN
```

3. Ejecuta:

```bash
python telegram_bot.py
```

Atajos:
- CMD: doble clic en `run_telegram_bot.bat`
- PowerShell: `powershell -ExecutionPolicy Bypass -File run_telegram_bot.ps1`

Comandos del bot:
- `/start`
- `/status`
- `/setleague <league_id> <season>`
- `/predict <Local> | <Visitante>`
- `/analyze_next [n]`
- `/backtest [min_history]`

## Subir a GitHub

1. Inicializa git y crea el primer commit:

```bash
git init
git add .
git commit -m "Initial commit: football predictor + telegram bot"
```

2. Crea repo vacio en GitHub y conecta remoto:

```bash
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

`Nota`: `.env` ya esta ignorado por `.gitignore`, no se sube al repositorio.

## Despliegue en Azure (Container Apps)

La opcion recomendada para un bot 24/7 es Azure Container Apps.

### Paso 1: primer despliegue manual

Ejecuta (PowerShell):

```powershell
./scripts/azure_first_deploy.ps1 \
  -ResourceGroup "rg-bet-bot" \
  -Location "eastus" \
  -AcrName "betbotacr123" \
  -ContainerEnvName "betbot-env" \
  -ContainerAppName "bet-telegram-bot" \
  -ApiFootballKey "TU_API_FOOTBALL_KEY" \
  -TelegramBotToken "TU_TELEGRAM_BOT_TOKEN"
```

### Paso 2: habilitar despliegue continuo desde GitHub Actions

El workflow ya existe en `.github/workflows/deploy-azure-containerapp.yml`.

Configura en GitHub:

- `Secrets`:
  - `AZURE_CREDENTIALS` (service principal JSON de `az ad sp create-for-rbac`)
- `Repository Variables`:
  - `ACR_NAME`
  - `ACR_LOGIN_SERVER`
  - `AZURE_RESOURCE_GROUP`
  - `CONTAINER_APP_NAME`

Cada push a `main` va a:
1. construir imagen en ACR,
2. actualizar tu Container App,
3. mantener los secretos en Azure (`api-football-key`, `telegram-bot-token`).

## Costos con creditos de Azure

- Usa `min-replicas=1` para que el bot siempre este activo.
- Mantente en SKU basicos (`ACR Basic`, Container Apps consumo) para cuidar tus 200 USD.
- Monitorea consumo en Cost Management semanalmente.

## Probar conexion a API-Football

```bash
set API_FOOTBALL_KEY=TU_API_KEY
python scripts/test_api_connection.py
```

## Formato minimo del CSV

Columnas obligatorias:

- `date` (ISO, por ejemplo `2025-03-10` o `2025-03-10T18:00:00Z`)
- `home_team`
- `away_team`
- `home_goals`
- `away_goals`

Columnas opcionales para enriquecer analisis:

- `home_odds`
- `draw_odds`
- `away_odds`

## Notas

- El ajuste Elo se aplica sobre los lambdas base de Poisson para evitar que el modelo solo dependa de goles historicos.
- No existe margen de error cero en apuestas deportivas. El sistema reduce incertidumbre con validacion y filtros de EV, pero siempre hay riesgo estadistico.
- Para produccion, conviene:
  - calibrar hiperparametros (`k_factor`, `home_advantage`, `max_goals`),
  - guardar snapshots diarios de features/predicciones,
  - automatizar ejecucion con scheduler (Airflow/Cron/GitHub Actions).
