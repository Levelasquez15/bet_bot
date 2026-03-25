from __future__ import annotations

import os
from typing import Tuple

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, rely on environment variables

# Default configuration
DEFAULT_LEAGUE_ID = 39  # Premier League
DEFAULT_SEASON = 2024  # Usar temporada con datos disponibles
MAX_FIXTURES_ANALYSIS = 12

# Mensajes en formato HTML (más robusto que Markdown)
MESSAGES = {
    'start': """<b>BetBot - Pronosticos Deportivos</b>

Hola! Soy tu asistente de pronosticos deportivos con IA.

<b>Comandos disponibles:</b>
/jornada - Analisis de partidos proximos (hoy y proximos dias)
/jornada_manana - Analisis especifico de manana
/jornada_pasado - Analisis especifico en 2 dias
/proximos - Ver lista completa de proximos partidos
/partido <code>Local</code> vs <code>Visitante</code> - Analisis especifico
/combinada - Generar combinada automatica
/comparar_lineas <code>Local</code> vs <code>Visitante</code> - Comparar cuotas
/notificaciones - Activar/desactivar alertas de oportunidades
/status - Estado del bot y configuracion
/setleague <code>id</code> <code>temporada</code> - Cambiar liga y temporada

<b>Para activar notificaciones de oportunidades:</b> Usa /notificaciones
<b>Configuracion actual:</b> Liga={league}, Temporada={season}
<b>Notificaciones:</b> {notifications}""",

    'status': """<b>Estado del Bot</b>

Configuracion:
- Liga: {league_id}
- Temporada: {season}
- API Football: {api_status}
- Token Telegram: {token_status}
- Notificaciones: {notifications}

Modelo listo para analisis""",

    'jornada_header': """<b>ANALISIS DE JORNADA - {date}</b>

<b>{count} partidos programados</b>
<b>Liga:</b> {league_name}
<b>Actualizado:</b> {time}

---------------""",

    'match_analysis': """<b>{home} vs {away}</b>
{time}

<b>Probabilidades del Modelo:</b>
- Local: {home_win:.1%}
- Empate: {draw:.1%}
- Visitante: {away_win:.1%}
- +2.5 Goles: {over:.1%}

<b>Fuerza de Ataque:</b>
- {home}: {lambda_home:.2f}
- {away}: {lambda_away:.2f}

<b>Recomendacion:</b> {recommendation}
---------------""",

    'top_picks': """<b>TOP PICKS RECOMENDADOS</b>

{matches_text}

<b>Recomendaciones basadas en modelo Poisson+Elo</b>
<b>Valor esperado minimo:</b> 3%""",

    'accumulator': """<b>COMBINADA SUGERIDA</b>

{legs} partidos combinados
Probabilidad total: {prob:.1%}
Cuota total: {odds:.2f}
Valor esperado: {ev:.1%}

<b>Recuerda:</b> Juego responsable""",

    'notification_alert': """<b>ALERTA DE OPORTUNIDAD!</b>

<b>{home} vs {away}</b>
{date}

<b>Pick recomendado:</b> {selection} ({market})
Probabilidad: {prob:.1%}
Cuota: {odds:.2f}
EV: {ev:.1%}

<b>Confianza:</b> {confidence}

<b>Actua rapido - las cuotas cambian</b>""",

    'no_matches': "No hay partidos programados para {date} en la liga configurada.",

    'analyzing': "Analizando {count} partidos de {date}...",

    'error_data': "Error obteniendo datos. Verifica la configuracion.",
    'error_analysis': "Error en el analisis. Intentelo de nuevo.",
    'processing': "Procesando...",

    'notifications_enabled': "*Notificaciones activadas*\n\nRecibiras alertas automaticas cuando el bot encuentre oportunidades de valor (EV >3% y prob >50%) durante los analisis de jornada.",
    'notifications_disabled': "*Notificaciones desactivadas*",

    'upcoming_matches_notification': """*PARTIDOS PROXIMOS - {date}*

*{count} partidos programados*

{matches_list}

*Usa /jornada para analisis completo*
*Usa /notificaciones para activar alertas de oportunidades*""",

    'invalid_format': "Formato invalido. Usa: {usage}",
    'accumulator_options': "Uso: /combinada <número>\nEjemplo: /combinada 3 (3, 5 o 10 cuotas)",
    'single_match': """<b>ANÁLISIS: {home} vs {away}</b>
<b>Fecha:</b> {date}
<b>Liga:</b> {league}

<b>Probabilidades del Modelo:</b>
- Local: {home_win:.1%}
- Empate: {draw:.1%}
- Visitante: {away_win:.1%}
- +2.5 Goles: {over:.1%}

<b>Fuerza de Ataque:</b>
- {home}: {lambda_home:.2f}
- {away}: {lambda_away:.2f}

<b>Recomendación:</b> {recommendation}""",
}


def get_api_key() -> str:
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing API_FOOTBALL_KEY in .env or environment")
    return api_key


def get_telegram_token() -> str:
    token = os.getenv("TELEGRAM_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TELEGRAM_TOKEN/TELEGRAM_BOT_TOKEN in .env or environment")
    return token


def current_config(context) -> Tuple[int, int]:
    league_id = int(context.bot_data.get("league_id", DEFAULT_LEAGUE_ID))
    season = int(context.bot_data.get("season", DEFAULT_SEASON))
    return league_id, season


def get_notifications_enabled(context) -> bool:
    """Check if notifications are enabled for this user."""
    return context.bot_data.get("notifications_enabled", False)


def set_notifications_enabled(context, enabled: bool):
    """Enable or disable notifications for this user."""
    context.bot_data["notifications_enabled"] = enabled