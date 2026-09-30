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
- [x] Árboles de decisión heurísticos básicos para partidos en vivo
- [x] Estimación básica de distribución de goles con Poisson
- [ ] Integración real del sistema Elo con cálculo de ventaja local/visitante
- [ ] Cálculo de Valor Esperado ($EV > 0$ / Value Betting): Probabilidad del modelo vs Cuota real
- [ ] Filtro de confianza configurable por umbrales matemáticos
- [ ] Algoritmo generador de apuestas combinadas (Parlays de 2-3 selecciones con mejor value)

### 🔹 Módulo 3: Base de Datos y Persistencia (`src/db/`)
- [x] Almacenamiento básico en archivos JSON planos (`subscribers.json`, `picks_history.json`)
- [ ] Migración de archivos JSON a SQLite local / Supabase (PostgreSQL)
- [ ] Esquema relacional: tablas de `subscribers`, `picks`, `matches`, `bankroll`
- [ ] Operaciones transaccionales seguras sin riesgo de bloqueo o corrupción de archivos

### 🔹 Módulo 4: Verificación de Resultados y Gestión de Bankroll (`src/worker/`)
- [x] Tarea periódica de verificación de partidos finalizados (cada 10 min)
- [x] Evaluación automática de mercados de goles (Over 1.5, Over 2.5, Over 3.5, BTTS)
- [x] Notificación automática a suscriptores cuando un pick se gana o se pierde
- [ ] Verificación de mercados de córners y tarjetas (eliminar estado `NO_VERIFICABLE`)
- [ ] Cálculo de rentabilidad real: Unidades ganadas (+/- U), ROI / Yield %, racha actual

### 🔹 Módulo 5: Bot de Telegram Interactivo (`src/bot/`)
- [x] Comandos de administración básicos (`/start`, `/status`, `/historial`, `/stats`, `/pause`, `/resume`, `/debug`, `/debugodds`)
- [x] Servidor HTTP de salud integrado en segundo plano en puerto 8000 (`/` y `/health`)
- [x] Difusión automática de señales a suscriptores activos
- [ ] Menú interactivo con botones Inline (`InlineKeyboardMarkup`)
- [ ] Comando interactivo `/calendario` y `/jornada` para consultar partidos por fecha
- [ ] Comando `/combinada` para generar un ticket bajo demanda
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
