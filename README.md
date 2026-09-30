# 🤖 BetBot - AI & Statistical Football Predictions Engine

Motor inteligente de pronósticos deportivos en tiempo real para fútbol, combinando modelos matemáticos (Poisson, Elo, Value Betting), árboles de decisión heurísticos y recolección de datos de alta velocidad con 365scores, integrado con un Bot de Telegram interactivo.

---

## 📋 Roadmap Modular y Estado del Proyecto

> **Convención:**
> * `[x]` **Completado (con chulo):** Funcionalidad desarrollada, testeada y operativa.
> * `[ ]` **Pendiente:** Funcionalidad planificada para ser desarrollada en su módulo correspondiente.

### 🔹 Módulo 1: Ingestión de Datos y Scraping (`src/scraper/`)
- [x] Conexión asíncrona a la API web de 365scores con `httpx`
- [x] Detección de partidos del día y partidos de mañana
- [x] Separación de partidos en vivo (`statusGroup 2 y 3`) y próximos (`statusGroup 1`)
- [x] Manejo de zona horaria local (Bogotá UTC-5)
- [x] Conexión resiliente con reintentos automáticos (`AsyncHTTPTransport` retries=3)
- [x] Filtro y categorización por Ligas Top (`src/scraper/leagues.py`)
- [x] Descarte inteligente de partidos juveniles (Sub-17/19), reservas y ligas amateurs
- [x] Extracción y normalización robusta de cuotas 1X2 desde 365scores
- [x] Extracción de estadísticas en vivo avanzadas (tiros a puerta, posesión, córners, xG en tiempo real)

### 🔹 Módulo 2: Motor Matemático y Análisis Predictivo (`src/analyzer/`, `src/models/`)
- [x] Árboles de decisión heurísticos avanzados para partidos en vivo (xG, tiros a puerta, córners, posesión)
- [x] Distribución bivariada de Poisson para 1X2, Over/Under (1.5, 2.5, 3.5), Doble Oportunidad y BTTS
- [x] Integración real del sistema Elo con cálculo de ventaja local/visitante y calibración dinámica de goles esperados
- [x] Cálculo de Valor Esperado ($EV > 0$ / Value Betting): Probabilidad del modelo vs Cuota real del bookmaker
- [x] Dimensionamiento de apuesta inteligente con Criterio de Kelly fraccional (Stake 1 al 5)
- [x] Algoritmo generador de apuestas combinadas (Parlays de 2-3 selecciones optimizando cuota y probabilidad acumulada)

### 🔹 Módulo 3: Base de Datos y Persistencia (`src/db/`)
- [x] Base de datos relacional SQLite con modo concurrente WAL e índices optimizados
- [x] Migración transparente y retrocompatible desde archivos JSON antiguos (`subscribers.json`, `picks_history.json`)
- [x] Esquema relacional estructurado: tablas `subscribers`, `picks`, `parlays` y `bankroll_log`
- [x] Repositorios desacoplados (`SubscriberRepository`, `PickRepository`, `ParlayRepository`) con bloqueos seguros de concurrencia

### 🔹 Módulo 4: Verificación de Resultados y Gestión de Bankroll (`src/worker/`)
- [x] Tarea periódica de verificación de partidos finalizados (cada 10 min)
- [x] Verificación matemática de mercados: 1X2, Doble Oportunidad (1X, X2, 12), Goles (0.5 a 3.5), BTTS y Próximo Gol
- [x] Notificación automática a suscriptores con resultado y desglose de ganancia (+/- U)
- [x] Auditoría de Bankroll: cálculo automático de Unidades Ganadas (+/- U), ROI / Yield % y Racha Actual
- [ ] Verificación de mercados de córners y tarjetas mediante estadísticas finales avanzadas

### 🔹 Módulo 5: Bot de Telegram Interactivo (`src/bot/`)
- [x] Comandos de administración básicos (`/start`, `/status`, `/historial`, `/stats`, `/pause`, `/resume`, `/debug`, `/debugodds`)
- [x] Servidor HTTP de salud integrado en segundo plano en puerto 8000 (`/` y `/health`)
- [x] Difusión automática de señales a suscriptores activos
- [x] Comando `/combinada` y `/parlay` para generar un ticket inteligente bajo demanda con valor matemático
- [ ] Menú interactivo con botones Inline (`InlineKeyboardMarkup`)
- [ ] Comando interactivo `/calendario` y `/jornada` para consultar partidos por fecha
- [ ] Preferencias personalizadas por usuario (alertas de goles, cuota mínima deseada, etc.)

### 🔹 Módulo 6: Despliegue y Operación 24/7 (`deploy/`)
- [x] Contenedor Docker optimizado (`Dockerfile` con Python 3.12 y dependencias matemáticas)
- [x] Servidor de salud compatible con plataformas cloud (Render / Koyeb)
- [x] Soporte para variables `TELEGRAM_TOKEN` y `TELEGRAM_BOT_TOKEN`
- [x] Código sincronizado en GitHub (`main`)
- [ ] Despliegue activo en producción 24/7 en Render con monitor de UptimeRobot

---

## 🛠️ Tecnologías y Librerías

* **Python 3.12+**
* **python-telegram-bot 21.6+** (Framework asíncrono con JobQueue)
* **httpx** (Cliente HTTP asíncrono de alto rendimiento)
* **pandas & numpy** (Manipulación matricial de datos)
* **scipy** (Distribuciones Poisson y estadísticas)
* **Docker** (Empaquetado y aislamiento en contenedor)

---

## 🚀 Uso Rápido en Local

```bash
# 1. Clonar el repositorio
git clone https://github.com/Levelasquez15/bet_bot.git
cd bet_bot

# 2. Crear entorno virtual e instalar dependencias
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Agregar TELEGRAM_TOKEN=tu_token_aqui en .env

# 4. Iniciar el bot
py telegram_bot.py
```
