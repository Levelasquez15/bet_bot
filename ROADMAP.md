# 🗺️ BetBot AI - Hoja de Ruta de Desarrollo (Roadmap Interno)

Documento interno de seguimiento de arquitectura, módulos implementados y backlog de tareas para el equipo de desarrollo.

---

## 📊 Estado Global del Proyecto

| Módulo | Componente | Estado | Cobertura / Tests |
| :--- | :--- | :---: | :---: |
| **Módulo 1** | Ingestión & Scraping 365scores/Flashscore | ✅ Completado | Tests validados |
| **Módulo 2** | Motor Cuantitativo (Poisson + Elo + Kelly) | ✅ Completado | Tests validados |
| **Módulo 3** | Persistencia Relacional SQLite WAL | ✅ Completado | Tests validados |
| **Módulo 4** | Verificador de Resultados & Bankroll Audit | ✅ Completado | Tests validados |
| **Módulo 5** | Bot de Telegram Táctil & Notificaciones | ✅ Completado | Tests validados |
| **Módulo 6** | Despliegue Docker & Render 24/7 con Health Check | ✅ Completado | Producción Activa |
| **Módulo 7** | Decision Graph Multi-Agente & Gemini Flash | ✅ Completado | Tests validados |
| **Calidad** | Modo Francotirador (Sniper Mode & Anti-Congelamiento) | ✅ Completado | Tests validados |

---

## 📋 Detalle de Módulos Implementados

### 🔹 Módulo 1: Ingestión de Datos y Scraping en Tiempo Real (`src/scraper/`)
- [x] Conexión asíncrona a la API web de 365scores con `httpx` y reintentos automáticos (`AsyncHTTPTransport`).
- [x] Detección de partidos del día y partidos de mañana en zona horaria Bogotá (UTC-5).
- [x] Separación de partidos en vivo (`statusGroup 3`) y próximos programados (`statusGroup 1 y 2`).
- [x] Filtro y categorización por Ligas Top (`src/scraper/leagues.py`) con descarte de juveniles (Sub-17/19), reservas y ligas amateurs.
- [x] Extracción y normalización de cuotas decimales 1X2 desde el feed del partido.
- [x] Extracción de estadísticas en vivo avanzadas: tiros a puerta, posesión, córners, tarjetas y xG.
- [x] Scraper de contingencia Flashscore (`src/scraper/flashscore_scraper.py`) para enriquecer estadísticas cuando el proveedor principal no las reporte.

### 🔹 Módulo 2: Motor Cuantitativo y Modelado Predictivo (`src/analyzer/`, `src/models/`)
- [x] Árboles heurísticos de ritmo y asedio territorial para partidos en juego.
- [x] Distribución bivariada de Poisson para mercados 1X2, Over/Under (1.5, 2.5, 3.5), Doble Oportunidad y BTTS.
- [x] Modelo Elo dinámico para clubes con ventaja de localía y calibración de goles esperados ($\lambda$).
- [x] Cálculo de Valor Esperado matemático ($EV > 0$ / Value Betting): Probabilidad del modelo vs Cuota de la casa.
- [x] Dimensionamiento de apuesta inteligente con Criterio de Kelly fraccional (Stake 1 al 5).
- [x] Generador de apuestas combinadas (Parlays de 2 a 3 selecciones optimizando cuota y probabilidad conjunta).

### 🔹 Módulo 3: Base de Datos y Persistencia Concurrente (`src/db/`)
- [x] Base de datos relacional SQLite con modo concurrente WAL e índices optimizados.
- [x] Migración transparente y retrocompatible desde archivos JSON legados.
- [x] Esquema relacional estructurado: tablas `subscribers`, `picks`, `parlays` y `bankroll_log`.
- [x] Repositorios desacoplados (`SubscriberRepository`, `PickRepository`, `ParlayRepository`) con bloqueos seguros de concurrencia.

### 🔹 Módulo 4: Verificación de Resultados y Auditoría Financiera (`src/worker/`)
- [x] Tarea periódica de verificación de partidos finalizados (cada 10 min).
- [x] Verificación matemática de mercados: 1X2, Doble Oportunidad, Goles Over/Under, BTTS, Córners y Tarjetas.
- [x] Notificación automática a suscriptores con resultado final y desglose de ganancia (+/- U).
- [x] Auditoría de Bankroll: cálculo automático de Unidades Ganadas (+/- U), ROI / Yield %, racha actual y comando `/bankroll`.

### 🔹 Módulo 5: Bot de Telegram Interactivo (`src/bot/`)
- [x] Comandos interactivos principales: `/start`, `/menu`, `/status`, `/historial`, `/stats`, `/pause`, `/resume`, `/debug`.
- [x] Menú interactivo táctil con botones Inline (`InlineKeyboardMarkup` y `CallbackQueryHandler`).
- [x] Comando `/jornada` y `/partidos` para consultar partidos en vivo y destacados del día.
- [x] Comando `/combinada` para generar un ticket inteligente bajo demanda.
- [x] Panel de preferencias personalizadas por usuario: alternar alertas Live, Pre-partido o Pausa global con botones interactivos.

### 🔹 Módulo 6: Despliegue en la Nube y Operación 24/7 (`deploy/`)
- [x] Contenedor Docker optimizado (`Dockerfile` ligero basado en Python 3.12).
- [x] Servidor de salud HTTP en segundo plano en puerto 8000 con telemetría en vivo (`/` y `/health`).
- [x] Soporte unificado para variables de entorno `TELEGRAM_TOKEN` y `TELEGRAM_BOT_TOKEN`.
- [x] Integración de CI/CD continuo vía GitHub hacia Render.

### 🔹 Módulo 7: Grafo de Decisión Multi-Agente y Director Técnico IA (`src/graph/`)
- [x] **Grafo de Estados Orquestado (`DecisionGraph`):**
  - **MomentumSpecialistNode:** Timing, ritmo de juego, empate tardío y goles tempraneros.
  - **SiegeXGSpecialistNode:** Asedio territorial, córners masivos y cerrojos defensivos (Under).
  - **PoissonEloValueSpecialistNode:** Modelado cuantitativo Poisson + Elo y Value Betting (+EV).
  - **DisciplinarySpecialistNode:** Superioridad numérica por tarjetas rojas y desbalance táctico.
- [x] **Gatekeeper de Costo $0 y Anti-Saturación:**
  - Filtrado local previo que bloquea llamadas innecesarias a la IA.
  - Enfriamiento por partido y control estricto de cuota API.
- [x] **Director Técnico IA (Supervisor):**
  - Inferencia con Google Gemini Flash (`GEMINI_API_KEY`) y respaldo determinista 100% infalible.
  - Resolución de conflictos entre especialistas contradictorios.
  - Generación de informe táctico natural explicable.
- [x] **Comando `/analizar [equipo]`** y botón táctil para análisis táctico bajo demanda.

### 🔹 Módulo de Calidad: Modo Francotirador & Anti-Congelamiento
- [x] **Modo Francotirador (Sniper Mode):** Umbral mínimo de confianza elevado al $78\%$, cero tolerancia a conflictos tácticos y filtro prioritario en Ligas Tier 1 y 2.
- [x] **Hard Cutoff de Minutos ($\le 80'$):** Prohibición absoluta de emitir recomendaciones en los últimos 10 minutos (minuto 80+) o en tiempo añadido (90'+).
- [x] **Detección Real de Medio Tiempo:** Restricción estricta de heurísticas de descanso a un minuto $\le 52'$ y estado explícito de entretiempo.
- [x] **Control de Tiempo Real Transcurrido ($\Delta t$ Sanity Check):**
  - Purga automática de partidos congelados en la API que superen los 125 minutos reales de juego.
  - Purga de partidos con supuesto entretiempo que lleven más de 75 minutos reales desde el inicio.
  - Purga de partidos en supuesto primer tiempo con más de 65 minutos reales.
- [x] **Limpieza Visual:** Formato limpio de marcadores (ej. `1-1` en vez de `1.0-1.0`) y minutos sin decimales ni comillas duplicadas.

---

## 🎯 Plan de Trabajo y Tareas para Mañana

1. **Monitoreo de Telemetría en Render:**
   - [ ] Inspeccionar logs de Render durante los ciclos de madrugada y mañana para verificar la estabilidad de las alertas.
   - [ ] Evaluar el comportamiento de las alertas en vivo durante las jornadas de ligas europeas y latinoamericanas.

2. **Calibración y Expansión Cuantitativa:**
   - [ ] Incorporar parámetros de forma reciente (últimos 5 partidos: ponderación exponencial) en el rating Elo de clubes.
   - [ ] Ajustar dinámicamente el valor $\lambda$ por liga según promedios actualizados de la temporada 2026.

3. **Reportes Automáticos de Resumen:**
   - [ ] Diseñar un job nocturno (medianoche Bogotá) que envíe un resumen automático del día a los usuarios (Picks enviados, aciertos, ganancia en unidades y yield del día).

4. **Mercados Adicionales de Alto Valor:**
   - [ ] Evaluar la incorporación de Hándicap Asiático ($+0.5$, $-0.5$) en el especialista cuantitativo.
   - [ ] Integrar mercado de córners por mitad (1T vs 2T).
