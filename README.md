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
- [x] Verificación de mercados de córners y tarjetas mediante estadísticas finales avanzadas de 365scores
- [x] Notificación automática a suscriptores con resultado y desglose de ganancia (+/- U)
- [x] Auditoría de Bankroll: cálculo automático de Unidades Ganadas (+/- U), ROI / Yield %, racha actual y comando `/bankroll`

### 🔹 Módulo 5: Bot de Telegram Interactivo (`src/bot/`)
- [x] Comandos de administración básicos (`/start`, `/menu`, `/status`, `/historial`, `/stats`, `/pause`, `/resume`, `/debug`, `/debugodds`)
- [x] Servidor HTTP de salud integrado en segundo plano en puerto 8000 (`/` y `/health`)
- [x] Difusión automática de señales a suscriptores activos filtrada por preferencias de modalidad
- [x] Comando `/combinada` y `/parlay` para generar un ticket inteligente bajo demanda con valor matemático
- [x] Comando `/bankroll` para auditoría financiera en vivo con desglose por modalidad (Live vs Pre)
- [x] Menú interactivo táctil con botones Inline (`InlineKeyboardMarkup` y `CallbackQueryHandler`)
- [x] Comando interactivo `/jornada` y `/partidos` para consultar partidos en vivo y destacados de hoy
- [x] Preferencias personalizadas por usuario: alternar alertas Live, Pre-partido o Pausa global con botones interactivos

### 🔹 Módulo 6: Despliegue y Operación 24/7 (`deploy/`)
- [x] Contenedor Docker optimizado (`Dockerfile` ligero con Python 3.12 y arranque ultra-rápido)
- [x] Servidor de salud HTTP en segundo plano en puerto 8000 con telemetría en vivo (`/` y `/health`)
- [x] Soporte para variables `TELEGRAM_TOKEN` y `TELEGRAM_BOT_TOKEN`
- [x] Código sincronizado en GitHub (`main`) con auto-despliegue continuo en Render
- [x] Arquitectura 100% gratuita 24/7 lista para monitor de UptimeRobot (ping cada 5 min a `/health`)

### 🔹 Módulo 7: Motor de Decisión con Grafo de Agentes y LLM Supervisor (`src/graph/`)
- [x] **Arquitectura de Grafo de Estados (Decision Graph / StateGraph):**
  - Encapsular los 8 árboles heurísticos en **Nodos Especialistas** independientes (Nodo Momentum, Nodo Asedio & xG, Nodo Poisson/Elo +EV, Nodo Disciplinario/Tarjetas).
  - Enrutamiento dinámico según el contexto del partido (minuto, marcador, posesión y estado numérico de jugadores).
- [x] **Agente Supervisor / Director Técnico IA (LLM):**
  - Integración de modelo de inferencia ultrarrápido (Google Gemini Flash vía `GEMINI_API_KEY`) con Supervisor Determinista de respaldo 100% resiliente.
  - Resolución inteligente de conflictos entre nodos contradictorios (ej. nodo de asedio alcista vs nodo de rojas/lesiones bajista).
  - Redacción de veredicto táctico natural y explicable para los suscriptores de Telegram.
- [x] **Arquitectura en Cascada (Gatekeeper de Costo $0 y Anti-Saturación):**
  - Filtro local previo: el scraping y las matemáticas corren en local a costo $0 y velocidad de milisegundos.
  - El LLM solo se invoca cuando el grafo detecta una oportunidad real de valor (+EV confirmado o alta confianza), limitando el tráfico a llamadas controladas.
  - Compatible 100% con el Free Tier de Render (inferencia remota ultraligera consumiendo <150MB de RAM en el contenedor).
- [x] **Comandos de Telegram Extendidos:**
  - Comando `/analizar [partido]` y botón interactivo `🧠 Analizar Partido (IA)` en el menú principal para solicitar al Grafo un informe táctico profundo con IA bajo demanda.

---

## 🛠️ Tecnologías y Librerías

* **Python 3.12+**
* **python-telegram-bot 21.6+** (Framework asíncrono con JobQueue y botones táctiles)
* **httpx** (Cliente HTTP asíncrono con `AsyncHTTPTransport` resiliente)
* **pandas & numpy** (Manipulación matricial de datos y modelos matemáticos)
* **SQLite Relacional con modo WAL** (Persistencia concurrente de alto rendimiento)
* **Docker** (Empaquetado ligero sin dependencias pesadas de compilación)

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
