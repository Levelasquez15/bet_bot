# Football Prediction System (Poisson + Elo)

Sistema base en Python para prediccion automatizada de futbol.

## Que incluye

- Extraccion de datos:
  - `ApiFootballDataSource` para resultados historicos y cuotas actuales (`/fixtures`, `/odds`).
  - Soporte de headers API-Sports y RapidAPI (`x-apisports-key`, `x-rapidapi-key`, `x-rapidapi-host`).
  - `ScrapingOddsDataSource` para scraping de cuotas con `requests + BeautifulSoup`.
- Modelado matematico:
  - Distribucion de Poisson para probabilidades `1X2` y `+2.5`.
  - Sistema Elo para ajustar calidad relativa de equipos.
- Decision de apuestas:
  - Comparacion de lineas entre casas.
  - Ranking por probabilidad y valor esperado (EV).
  - Generacion de combinadas (parlays) con probabilidad y cuota agregadas.
- Validacion:
  - Backtesting rolling con metricas: `Accuracy 1X2`, `LogLoss 1X2`, `Brier +2.5`.
- Interfaz:
  - Dashboard en Streamlit (`app_streamlit.py`).
  - Bot de Telegram (`telegram_bot.py`).

## Estructura

```text
.
|-- app_streamlit.py
|-- requirements.txt
|-- src/
|   |-- backtesting.py
|   |-- data_sources.py
|   |-- engine.py
|   `-- models/
|       |-- elo.py
|       `-- poisson.py
```

## Instalacion

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

O más fácil aún: simplemente ejecuta uno de estos según tu sistema:
- **Línea de comandos (CMD)**: Doble clic en `run.bat`
- **PowerShell**: `powershell -ExecutionPolicy Bypass -File run.ps1`

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
