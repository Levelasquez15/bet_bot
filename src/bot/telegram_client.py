# pyright: reportOptionalMemberAccess=none
# pyright: reportAttributeAccessIssue=none
# pyright: reportArgumentType=none
# pyright: reportGeneralTypeIssues=none

"""
Cliente de Telegram para BetBot.
Incluye comandos interactivos, botones Inline, menú de preferencias y control de bankroll.
"""

import logging
import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from src.bot.subscribers import (
    add_subscriber, get_subscribers, set_paused,
    get_subscriber_data, update_subscriber_prefs
)
from src.bot.pick_tracker import get_stats, get_recent_picks
from src.scraper.scraper_365 import Scraper365, BOGOTA_TZ
from src.analyzer.logic_tree import LogicTreeAnalyzer
from src.analyzer.combinadas import generate_best_parlay, format_parlay_message
from src.db.database import db
from src.graph.decision_graph import DecisionGraph
from src.graph.state import MatchState

from src.assistant import (
    BetAssistant,
    format_corners_report,
    format_players_report,
    format_full_match_report
)

logger = logging.getLogger(__name__)

# Instancia global del Asistente Personal de Apuestas (Córners & Jugadores)
assistant_engine = BetAssistant(limit_corners_matches=10)

# Instancia global del Grafo de Decisión y Director Técnico IA (Módulo 7)
graph_engine = DecisionGraph()

STATUS_EMOJI = {
    "GANADO":          "✅",
    "PERDIDO":         "❌",
    "PENDIENTE":       "⏳",
    "NO_VERIFICABLE":  "⚪",
}


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Genera la botonera táctil principal optimizada para el Ayudante Pre-Partido."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚩 Córners (Historial 10P)", callback_data="btn_ayudante_corners"),
            InlineKeyboardButton("🎯 Disparos & Faltas", callback_data="btn_ayudante_players"),
        ],
        [
            InlineKeyboardButton("🟢 Oficiales Confirmadas (~1h)", callback_data="btn_oficiales_1h"),
            InlineKeyboardButton("🟡 Horas Antes (Once Habitual)", callback_data="btn_horas_antes"),
        ],
        [
            InlineKeyboardButton("📋 Análisis Completo Partido", callback_data="btn_ayudante_full"),
            InlineKeyboardButton("🎰 Combinadas Córners/Props", callback_data="btn_combinada_ayudante"),
        ],
        [
            InlineKeyboardButton("⚽ Partidos y Alineaciones Hoy", callback_data="btn_partidos_hoy"),
            InlineKeyboardButton("💼 Mi Bankroll & ROI", callback_data="btn_bankroll"),
        ],
        [
            InlineKeyboardButton("⚙️ Mis Preferencias", callback_data="btn_prefs"),
            InlineKeyboardButton("🔄 Estado del Bot", callback_data="btn_status"),
        ]
    ])


def get_prefs_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Genera la botonera interactiva para alternar preferencias de alertas."""
    sub = get_subscriber_data(chat_id) or {}
    live_on = sub.get("notify_live", 1) == 1
    upcoming_on = sub.get("notify_upcoming", 1) == 1
    is_paused = sub.get("is_paused", 0) == 1

    live_text = "🟢 Live: Activado" if live_on else "🔴 Live: Desactivado"
    upcoming_text = "🟢 Pre-Partido: Activado" if upcoming_on else "🔴 Pre-Partido: Desactivado"
    pause_text = "🔇 Estado: Pausado" if is_paused else "🔊 Estado: Recibiendo Alertas"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(live_text, callback_data="toggle_live")],
        [InlineKeyboardButton(upcoming_text, callback_data="toggle_upcoming")],
        [InlineKeyboardButton(pause_text, callback_data="toggle_pause")],
        [InlineKeyboardButton("🔙 Volver al Menú Principal", callback_data="btn_main_menu")]
    ])


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Botón sencillo para regresar al menú principal."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Volver al Menú Principal", callback_data="btn_main_menu")]
    ])


# ── Comandos Principales ───────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not update.message:
        return
    chat_id = chat.id
    is_new = add_subscriber(chat_id, username=user.username, first_name=user.first_name)

    welcome_text = (
        rf"¡Hola {user.mention_html()}! Soy <b>BetBot Ayudante</b> 🤖⚽"
        "\n\nTu <b>asistente personal de pronósticos pre-partido</b> especializado en tu estrategia:"
        "\n\n🚩 <b>Tiros de Esquina (Córners):</b>"
        "\n  • Historial y promedios de los <b>últimos 10 partidos</b> de cada equipo"
        "\n  • Córners a favor, en contra, promedios y líneas recomendadas"
        "\n\n🎯 <b>Mercados de Jugadores (Props):</b>"
        "\n  • <b>🟢 A ~1 Hora del Partido:</b> Con alineación oficial confirmada (11 titulares exactos)."
        "\n  • <b>🟡 Horas Antes:</b> Análisis previo con el Once Habitual según partidos anteriores."
        "\n  • Disparos totales (+1.5, +2.5), Remates al arco (+0.5, +1.5) y Faltas (+1.5)."
        "\n\n🏆 <b>Cobertura:</b> Champions League, Ligas Top Europeas y Sudamericanas (Brasileirão, Libertadores)"
        "\n\n👇 <i>Selecciona una opción del panel táctil para comenzar:</i>"
    )

    await update.message.reply_html(welcome_text, reply_markup=get_main_menu_keyboard())


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Abre el panel táctil interactivo."""
    if update.message:
        await update.message.reply_html(
            "📱 <b>PANEL DE CONTROL INTERACTIVO</b> 📱\n"
            "Elige qué deseas consultar:",
            reply_markup=get_main_menu_keyboard()
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs  = get_subscribers()
    stats = get_stats()
    text = (
        "📊 <b>Estado del Motor BetBot Ayudante</b>\n\n"
        "✅ Ingestión 365scores: ACTIVO\n"
        "✅ Ayudante de Córners (Historial 10 Partidos): ACTIVO\n"
        "✅ Props de Jugadores (Tiros Totales, Arco & Faltas): ACTIVO\n"
        "✅ Detección de Alineaciones Oficiales (~1h): ACTIVO\n"
        "✅ Once Habitual Histórico (Horas Antes): ACTIVO\n"
        "✅ Verificación Automática de Resultados: ACTIVO\n"
        f"👥 Suscriptores Registrados: {len(subs)}\n"
        f"📈 Pronósticos Totales: {stats['total']}\n"
        f"🏆 Efectividad: {stats['efectividad']}%\n"
        "⏱️ Monitor de Alineaciones: cada 2 min"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    elif update.message:
        await update.message.reply_html(text, reply_markup=get_back_keyboard())


async def historial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los últimos 10 picks con su resultado."""
    picks = get_recent_picks(limit=10)
    if not picks:
        msg = "📭 Aún no hay picks en el historial."
    else:
        lines = ["📋 <b>Últimos 10 Picks Registrados</b>\n"]
        for p in picks:
            emoji  = STATUS_EMOJI.get(p["status"], "❓")
            tipo   = "🔴 LIVE" if p.get("type") == "live" else "📅 PRE"
            score  = f" → Final: {p['final_score']}" if p.get("final_score") else ""
            odd_str = f" [@ {p['odd']}]" if p.get("odd") else ""
            lines.append(
                f"{emoji} [{tipo}] <b>{p['match']}</b>\n"
                f"   🎯 {p['market']}{odd_str}\n"
                f"   ⏱️ {p['timestamp']}{score}\n"
            )
        msg = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_back_keyboard())
    elif update.message:
        await update.message.reply_html(msg, reply_markup=get_back_keyboard())


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra estadísticas completas de rendimiento y rentabilidad."""
    s = get_stats()

    if s["total"] == 0:
        msg = "📭 Aún no hay picks registrados para calcular estadísticas."
    else:
        bar_won  = "🟩" * min(s["ganados"], 10)
        bar_lost = "🟥" * min(s["perdidos"], 10)
        profit_emoji = "🟢" if s["net_profit"] >= 0 else "🔴"

        msg = (
            f"📊 <b>Estadísticas y Rentabilidad (BetBot)</b>\n\n"
            f"📦 Total picks enviados: <b>{s['total']}</b>\n\n"
            f"✅ Ganados:         <b>{s['ganados']}</b>   {bar_won}\n"
            f"❌ Perdidos:        <b>{s['perdidos']}</b>   {bar_lost}\n"
            f"⏳ Pendientes:      <b>{s['pendientes']}</b>\n"
            f"⚪ No verificables: <b>{s['no_verif']}</b>\n\n"
            f"🏆 <b>Efectividad: {s['efectividad']}%</b>\n"
            f"{profit_emoji} <b>Beneficio Neto:</b> <code>{s['net_profit']:+.2f} U</code>\n"
            f"📈 <b>Yield / ROI:</b> <code>{s['yield_pct']:+.1f}%</code>\n"
            f"🔥 <b>Racha Actual:</b> <code>{s['streak']}</code>\n"
            f"<i>(sobre {s['ganados'] + s['perdidos']} picks verificados)</i>"
        )

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_back_keyboard())
    elif update.message:
        await update.message.reply_html(msg, reply_markup=get_back_keyboard())


async def bankroll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra un desglose completo de la gestión de bankroll y rendimiento financiero."""
    s = get_stats()
    if s["total"] == 0:
        msg = "📭 Aún no hay pronósticos registrados en la base de datos."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_text(msg, reply_markup=get_back_keyboard())
        return

    profit_emoji = "🟢" if s["net_profit"] >= 0 else "🔴"

    type_stats = []
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT pick_type, COUNT(*) as cnt, SUM(profit_units) as profit
        FROM picks
        WHERE status IN ('GANADO', 'PERDIDO')
        GROUP BY pick_type
        """)
        type_stats = cur.fetchall()

    lines = [
        "💼 <b>AUDITORÍA DE BANKROLL Y RENTABILIDAD</b> 💼\n",
        f"💰 <b>Total Apostado:</b> <code>{s['total_staked']} U</code>",
        f"{profit_emoji} <b>Beneficio Neto:</b> <code>{s['net_profit']:+.2f} U</code>",
        f"📈 <b>Yield (ROI Real):</b> <code>{s['yield_pct']:+.1f}%</code>",
        f"🎯 <b>Winrate:</b> <code>{s['efectividad']}%</code> ({s['ganados']}W - {s['perdidos']}L)",
        f"🔥 <b>Racha Actual:</b> <code>{s['streak']}</code>",
        f"⏳ <b>Picks en Juego:</b> <code>{s['pendientes']}</code>\n",
    ]

    if type_stats:
        lines.append("📊 <b>Rendimiento por Modalidad:</b>")
        for row in type_stats:
            p_type = "🔴 En Vivo (Live)" if row["pick_type"] == "live" else "📅 Pre-Partido"
            p_prof = row["profit"] or 0.0
            p_emoji = "🟩" if p_prof >= 0 else "🟥"
            lines.append(f"  • {p_type}: <b>{row['cnt']} picks</b> | {p_emoji} <code>{p_prof:+.2f} U</code>")

    lines.append("\n💡 <i>Cálculos basados en el Criterio de Kelly y cuotas validadas en tiempo real.</i>")
    msg = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_back_keyboard())
    elif update.message:
        await update.message.reply_html(msg, reply_markup=get_back_keyboard())


async def combinada_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera en tiempo real un ticket de apuesta combinada optimizada con Valor Esperado."""
    if update.callback_query:
        await update.callback_query.edit_message_text("🎰 Calculando la mejor combinada con valor matemático... un momento.")
    elif update.message:
        await update.message.reply_text("🎰 Calculando la mejor combinada con valor matemático... un momento.")

    scraper = Scraper365()
    analyzer = LogicTreeAnalyzer()
    try:
        upcoming_games = await scraper.fetch_upcoming_matches(hours_ahead=24, filter_leagues=True)
        if not upcoming_games:
            msg = "❌ No hay partidos programados en las próximas 24 horas."
        else:
            picks = analyzer.analyze_upcoming(upcoming_games)
            if len(picks) < 2:
                msg = (
                    f"⚠️ Solo se encontraron {len(picks)} selecciones con Valor Esperado positivo (+EV). "
                    "Se requieren al menos 2 partidos para armar una combinada."
                )
            else:
                parlay = generate_best_parlay(picks, legs=min(3, len(picks)))
                if not parlay:
                    msg = "⚠️ No se encontró una combinación que cumpla con los filtros de cuota (2.0 a 6.0) y probabilidad acumulada."
                else:
                    msg = format_parlay_message(parlay)

        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_html(msg, reply_markup=get_back_keyboard())

    except Exception as e:
        logger.error(f"Error generando combinada: {e}", exc_info=True)
        err_msg = f"❌ Error calculando combinada: {e}"
        if update.callback_query:
            await update.callback_query.edit_message_text(err_msg, reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_text(err_msg, reply_markup=get_back_keyboard())
    finally:
        await scraper.close()


async def jornada_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el calendario de partidos pre-partido monitoreados para hoy con estado de alineación."""
    scraper = Scraper365()
    try:
        games = await scraper.fetch_assistant_matches(hours_ahead=24, min_tier=2)

        lines = [
            "⚽ <b>PARTIDOS Y ALINEACIONES DE HOY (PRE-PARTIDO)</b> ⚽\n",
            "Monitoreo exclusivo de ligas destacadas: Champions League, Premier, LaLiga, Serie A, Bundesliga, Ligue 1, Brasileirão, Libertadores.\n",
            "🟢 <b>Alineaciones Oficiales (~1h antes):</b> Los 11 titulares confirmados al 100%.",
            "🟡 <b>Horas Antes (Once Habitual):</b> Proyección anticipada con los titulares más repetidos en sus últimos partidos.\n"
        ]

        buttons = [
            [
                InlineKeyboardButton("🟢 Solo Confirmadas (~1h)", callback_data="btn_oficiales_1h"),
                InlineKeyboardButton("🟡 Horas Antes (Once Habitual)", callback_data="btn_horas_antes")
            ]
        ]

        if games:
            lines.append("📋 <b>Próximos Partidos Programados:</b>")
            for g in games[:8]:
                gid = str(g.get("id"))
                h = g.get("homeCompetitor", {}).get("name", "")[:12]
                a = g.get("awayCompetitor", {}).get("name", "")[:12]
                comp = g.get("competitionDisplayName") or ""
                comp_short = comp[:10]
                st = g.get("startTime", "")[11:16] if g.get("startTime") else "Hoy"
                time_left = g.get("time_left_str", "")
                badge = "🟢" if g.get("is_lineup_confirmed") else "🟡"
                time_disp = f"{st} · {time_left}" if time_left else st

                lines.append(f"  • {badge} <b>{h} vs {a}</b> 🕐 {time_disp} <i>[{comp_short}]</i>")
                buttons.append([InlineKeyboardButton(f"{badge} {h} vs {a} ({time_disp})", callback_data=f"ply_{gid}")])

            lines.append("\n👉 <i>Toca un partido para consultar su alineación (oficial o habitual) y props de jugadores/córners.</i>")
        else:
            lines.append("⏳ <i>No hay partidos programados en las próximas 24 horas para las ligas monitoreadas.</i>")

        buttons.append([InlineKeyboardButton("🔙 Volver al Menú Principal", callback_data="btn_main_menu")])

        msg = "\n".join(lines)
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        elif update.message:
            await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Error en jornada_command: {e}", exc_info=True)
        err_msg = f"❌ Error consultando partidos de hoy: {e}"
        if update.callback_query:
            await update.callback_query.edit_message_text(err_msg, reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_text(err_msg, reply_markup=get_back_keyboard())
    finally:
        await scraper.close()


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    set_paused(chat_id, True)
    await update.message.reply_html(
        "🔇 <b>Bot Pausado.</b>\nYa no recibirás alertas de apuestas. Usa /resume o el menú para reactivar.",
        reply_markup=get_main_menu_keyboard()
    )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    set_paused(chat_id, False)
    await update.message.reply_html(
        "🔊 <b>Bot Reactivado.</b>\nVuelves a estar en la lista prioritaria para recibir picks.",
        reply_markup=get_main_menu_keyboard()
    )


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("🔍 Consultando 365scores... un momento.")
    scraper = Scraper365()
    try:
        info = await scraper.fetch_all_for_debug()
        lines = [
            "🛠️ <b>DEBUG — Estado del Scraper</b>\n",
            f"📅 Partidos hoy: <b>{info['total']}</b>",
            f"🟡 Próximos totales: {info['upcoming']}",
            f"🟢 En vivo: {info['live']}",
            f"⚫ Finalizados: {info['finished']}",
            f"⏰ Próximos (3h): {info['upcoming_3h']}\n",
        ]
        if info["live_sample"]:
            lines.append("⚽ <b>En vivo ahora:</b>")
            lines += [f"  • {m}" for m in info["live_sample"]]
        else:
            lines.append("⚽ Sin partidos en vivo ahora mismo.")

        if info["upcoming_sample"]:
            lines.append("\n📅 <b>Próximos partidos (3h):</b>")
            lines += [f"  • {m}" for m in info["upcoming_sample"]]
        else:
            lines.append("\n📅 Sin partidos próximos en 3h.")

        await update.message.reply_html("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error en debug: {e}")
    finally:
        await scraper.close()


async def debugodds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("🔍 Extrayendo el JSON de un partido con cuotas para análisis... un momento.")
    scraper = Scraper365()
    try:
        games = await scraper.fetch_live_matches()
        game_con_cuotas = next((g for g in games if "odds" in g or "bookmakers" in g), None)
        if game_con_cuotas:
            bookmakers = game_con_cuotas.get("bookmakers", [])
            odds = game_con_cuotas.get("odds", {})
            report = {
                "match": f"{game_con_cuotas.get('homeCompetitor', {}).get('name')} vs {game_con_cuotas.get('awayCompetitor', {}).get('name')}",
                "odds_key": odds,
                "bookmakers_key": bookmakers
            }
            json_text = json.dumps(report, ensure_ascii=False, indent=2)
            if len(json_text) > 3000:
                json_text = json_text[:3000] + "\n...[TRUNCATED]"
            await update.message.reply_html(f"<b>RAW JSON (Cuotas):</b>\n<pre>{json_text}</pre>")
        else:
            await update.message.reply_text("❌ No encontré ningún partido en vivo con cuotas en este instante.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error en debugodds: {e}")

# ── Módulo 7: Informes Tácticos y Comando /analizar ───────────────────────────

def format_tactical_analysis_report(state: MatchState) -> str:
    verdict = state.verdict
    sh = state.score_home
    sa = state.score_away

    if state.is_live:
        header_time = f"🔴 <b>EN VIVO</b> (Minuto {state.minute}') | Marcador: <b>{sh} - {sa}</b>"
    else:
        header_time = f"⏳ <b>PRE-PARTIDO</b> | Inicio: <b>{state.minute}</b>"

    ai_badge = "🤖 <b>DIRECTOR TÉCNICO IA (Gemini Flash)</b>" if (verdict and verdict.source == "GEMINI_FLASH") else "🧠 <b>SUPERVISOR TÁCTICO & CUANTITATIVO</b>"

    selected_market = verdict.selected_market if verdict else "Bajo Observación"
    odd_str = verdict.odd_str if verdict else "N/A"
    conf = verdict.confidence if verdict else 0.0
    stake = verdict.recommended_stake if verdict else 1
    report = verdict.tactical_report if verdict else "Sin anomalías tácticas suficientes para sugerir apuesta activa."

    stats = state.live_stats
    stats_lines = []
    if state.is_live and stats:
        poss_h = stats.get("possession", {}).get("home", 50)
        poss_a = stats.get("possession", {}).get("away", 50)
        shots_h = stats.get("shots_on_target", {}).get("home", 0)
        shots_a = stats.get("shots_on_target", {}).get("away", 0)
        corners_h = stats.get("corners", {}).get("home", 0)
        corners_a = stats.get("corners", {}).get("away", 0)
        xg_h = stats.get("xg", {}).get("home", 0.0)
        xg_a = stats.get("xg", {}).get("away", 0.0)
        red_h = stats.get("red_cards", {}).get("home", 0)
        red_a = stats.get("red_cards", {}).get("away", 0)

        stats_lines.append("📊 <b>Estadísticas Reales en Vivo:</b>")
        stats_lines.append(f"  • Posesión: {poss_h}% - {poss_a}%")
        stats_lines.append(f"  • Tiros al arco: {shots_h} - {shots_a} | xG: {xg_h} - {xg_a}")
        stats_lines.append(f"  • Córners: {corners_h} - {corners_a}")
        if red_h > 0 or red_a > 0:
            stats_lines.append(f"  • 🟥 Tarjetas Rojas: {red_h} - {red_a}")

    specs_lines = []
    for name, ev in state.evaluations.items():
        specs_lines.append(f"  • <b>{name}:</b> {ev.recommended_market} ({ev.confidence}%)")

    conflicts_lines = []
    if state.conflicts:
        for c in state.conflicts:
            conflicts_lines.append(f"  • ⚠️ {c}")

    synergies_lines = []
    if state.synergies:
        for s in state.synergies:
            synergies_lines.append(f"  • ⚡ {s}")

    lines = [
        f"{ai_badge}\n",
        f"⚽ <b>{state.match_name}</b>",
        f"🏆 <i>{state.competition}</i>",
        f"{header_time}\n",
    ]
    if stats_lines:
        lines.extend(stats_lines)
        lines.append("")

    lines.extend([
        "🎯 <b>VEREDICTO PRINCIPAL:</b>",
        f"👉 <b>{selected_market}</b>",
        f"💶 <b>Cuota Referencia:</b> {odd_str}",
        f"🏦 <b>Confianza del Modelo:</b> {conf}%",
        f"💰 <b>Stake Recomendado:</b> {stake} / 5\n",
        "💡 <b>INFORME TÁCTICO:</b>",
        f"{report}\n",
    ])

    if specs_lines:
        lines.append("🧩 <b>Votos de Nodos Especialistas:</b>")
        lines.extend(specs_lines)
        lines.append("")

    if synergies_lines:
        lines.append("⚡ <b>Sinergias Detectadas:</b>")
        lines.extend(synergies_lines)
        lines.append("")

    if conflicts_lines:
        lines.append("⚠️ <b>Alertas de Riesgo / Conflictos:</b>")
        lines.extend(conflicts_lines)
        lines.append("")

    return "\n".join(lines)


async def build_analizar_matches_keyboard() -> tuple[str, InlineKeyboardMarkup]:
    """Genera la botonera táctil para seleccionar un partido a analizar con IA."""
    scraper = Scraper365()
    try:
        live = await scraper.fetch_live_matches(filter_leagues=True, fetch_stats=False)
        upcoming = await scraper.fetch_upcoming_matches(hours_ahead=12, filter_leagues=True)

        buttons = []
        now_cur = datetime.now(tz=BOGOTA_TZ)
        if live:
            for g in live:
                try:
                    gt = float(g.get("gameTime", 0))
                except (ValueError, TypeError):
                    gt = 0.0
                gtd = str(g.get("gameTimeDisplay", "")).strip()
                if gt >= 88.0 or gtd in ("90'", "90+", "Fin", "Finalizado"):
                    continue

                start_str = g.get("startTime", "")
                if start_str:
                    try:
                        start_dt = datetime.fromisoformat(start_str)
                        elapsed = (now_cur - start_dt).total_seconds() / 60.0
                        if elapsed > 125.0 or (elapsed > 75.0 and gt <= 45.0):
                            continue
                    except Exception:
                        pass

                gid = str(g.get("id"))
                h = g.get("homeCompetitor", {}).get("name", "")[:12]
                a = g.get("awayCompetitor", {}).get("name", "")[:12]
                min_str = str(g.get("gameTimeDisplay") or g.get("gameTime") or "Live").replace("'", "")
                btn_txt = f"🔴 {h} vs {a} ({min_str}')"
                buttons.append([InlineKeyboardButton(btn_txt, callback_data=f"anlz_{gid}")])
                if len(buttons) >= 5:
                    break

        if upcoming:
            for g in upcoming[:5]:
                gid = str(g.get("id"))
                h = g.get("homeCompetitor", {}).get("name", "")[:12]
                a = g.get("awayCompetitor", {}).get("name", "")[:12]
                st = g.get("startTime", "")[11:16] if g.get("startTime") else "Hoy"
                btn_txt = f"⏳ {h} vs {a} ({st})"
                buttons.append([InlineKeyboardButton(btn_txt, callback_data=f"anlz_{gid}")])

        buttons.append([InlineKeyboardButton("🔙 Volver al Menú Principal", callback_data="btn_main_menu")])

        if not live and not upcoming:
            text = (
                "🧠 <b>ANALIZADOR TÁCTICO CON IA (MÓDULO 7)</b> 🧠\n\n"
                "No hay partidos programados o en vivo en este momento.\n"
                "Puedes usar <code>/analizar [equipo]</code> (ej: <code>/analizar Real Madrid</code>) para buscar cualquier encuentro."
            )
        else:
            text = (
                "🧠 <b>ANALIZADOR TÁCTICO CON IA (MÓDULO 7)</b> 🧠\n\n"
                "Selecciona un partido para que el <b>Grafo de Especialistas</b> y el <b>Director Técnico IA</b> elaboren un informe táctico profundo:"
            )

        return text, InlineKeyboardMarkup(buttons)
    finally:
        await scraper.close()


async def analizar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /analizar [equipo/partido] para invocar el DecisionGraph y Gemini Flash bajo demanda."""
    if not update.effective_chat:
        return

    # Si el usuario pasó argumentos (ej: /analizar Barcelona)
    if context.args:
        query = " ".join(context.args).strip().lower()
        if update.message:
            wait_msg = await update.message.reply_html(f"🔍 Buscando <b>'{query}'</b> y corriendo Grafo de Agentes IA...")
        else:
            wait_msg = None

        scraper = Scraper365()
        try:
            live = await scraper.fetch_live_matches(filter_leagues=False, fetch_stats=True)
            upcoming = await scraper.fetch_upcoming_matches(hours_ahead=24, filter_leagues=False)

            all_matches = [(g, True) for g in live] + [(g, False) for g in upcoming]
            matched = None
            is_live = False

            for g, live_flag in all_matches:
                h = g.get("homeCompetitor", {}).get("name", "").lower()
                a = g.get("awayCompetitor", {}).get("name", "").lower()
                if query in h or query in a:
                    matched = g
                    is_live = live_flag
                    break

            if not matched:
                err_text = (
                    f"❌ No se encontró ningún partido activo hoy para: <b>'{query}'</b>.\n\n"
                    "Usa <code>/analizar</code> sin argumentos para ver la lista de partidos disponibles."
                )
                if wait_msg:
                    await wait_msg.edit_text(err_text, parse_mode="HTML", reply_markup=get_back_keyboard())
                elif update.message:
                    await update.message.reply_html(err_text, reply_markup=get_back_keyboard())
                return

            # Ejecutar Grafo de Estados con Gemini Supervisor
            state = await graph_engine.evaluate_match(matched, is_live=is_live, force_llm=True)
            report_msg = format_tactical_analysis_report(state)

            if wait_msg:
                await wait_msg.edit_text(report_msg, parse_mode="HTML", reply_markup=get_back_keyboard())
            elif update.message:
                await update.message.reply_html(report_msg, reply_markup=get_back_keyboard())

        except Exception as e:
            logger.error(f"Error en analizar_command con args: {e}", exc_info=True)
            err_msg = f"❌ Error ejecutando análisis con IA: {e}"
            if wait_msg:
                await wait_msg.edit_text(err_msg, reply_markup=get_back_keyboard())
            elif update.message:
                await update.message.reply_text(err_msg, reply_markup=get_back_keyboard())
        finally:
            await scraper.close()
    else:
        # Menú táctil con botones de partidos
        try:
            text, keyboard = await build_analizar_matches_keyboard()
            if update.message:
                await update.message.reply_html(text, reply_markup=keyboard)
            elif update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error en analizar_command sin args: {e}", exc_info=True)
            if update.message:
                await update.message.reply_text(f"❌ Error consultando partidos para análisis: {e}")


# ── Módulo Especialista: Ayudante de Córners y Jugadores ───────────────────────

async def build_assistant_matches_keyboard(action_type: str = "corners") -> tuple[str, InlineKeyboardMarkup]:
    """Genera la botonera táctil para seleccionar un partido a analizar con el Ayudante."""
    scraper = Scraper365()
    try:
        only_confirmed = (action_type == "oficiales")
        hours_ahead = 4 if action_type == "oficiales" else 24
        games = await scraper.fetch_assistant_matches(hours_ahead=hours_ahead, min_tier=2, only_confirmed=only_confirmed)

        if action_type == "horas_antes":
            games = [g for g in games if not g.get("is_lineup_confirmed")]

        buttons = []

        title_map = {
            "corners":     ("🚩 <b>AYUDANTE DE CÓRNERS (10 PARTIDOS)</b> 🚩", "crn", "Análisis estadístico sobre los últimos 10 partidos de cada equipo.\n\nSelecciona un partido próximo:"),
            "players":     ("🎯 <b>AYUDANTE DE JUGADORES (TIROS & FALTAS)</b> 🎯", "ply", "🟢 = Alineación Oficial (~1h) | 🟡 = Once Habitual (Horas antes)\n\nSelecciona un partido próximo:"),
            "full":        ("📋 <b>ANÁLISIS COMPLETO (CÓRNERS + PROPS)</b> 📋", "ful", "Dossier completo: Córners (10 partidos) + Alineaciones y Props de Jugadores.\n\nSelecciona un partido próximo:"),
            "oficiales":   ("🟢 <b>ALINEACIONES OFICIALES CONFIRMADAS (~1H)</b> 🟢", "ply", "Partidos a punto de empezar con los 11 titulares 100% confirmados por las ligas.\n\nSelecciona un partido para ver sus alineaciones y tiros/faltas:"),
            "horas_antes": ("🟡 <b>PRE-PARTIDO HORAS ANTES (ONCE HABITUAL)</b> 🟡", "ply", "Partidos de hoy programados con antelación. Análisis previo con alineación probable y el Once Habitual (últimos 2-3 partidos).\n\nSelecciona un partido:")
        }
        header_title, prefix, subtitle = title_map.get(action_type, title_map["corners"])

        if games:
            for g in games[:8]:
                gid = str(g.get("id"))
                h = g.get("homeCompetitor", {}).get("name", "")[:12]
                a = g.get("awayCompetitor", {}).get("name", "")[:12]
                comp = g.get("competitionDisplayName") or ""
                comp_short = comp[:10]
                st = g.get("startTime", "")[11:16] if g.get("startTime") else "Hoy"
                time_left = g.get("time_left_str", "")
                badge = "🟢" if g.get("is_lineup_confirmed") else "🟡"
                time_disp = f"{st} · {time_left}" if time_left else st

                btn_text = f"{badge} {h} vs {a} ({time_disp}) [{comp_short}]"
                buttons.append([InlineKeyboardButton(btn_text, callback_data=f"{prefix}_{gid}")])

        # Botones de navegación contextuales
        nav_row = []
        if action_type == "oficiales":
            nav_row.append(InlineKeyboardButton("🟡 Ver Horas Antes (Once Habitual)", callback_data="btn_horas_antes"))
        elif action_type == "horas_antes":
            nav_row.append(InlineKeyboardButton("🟢 Ver Oficiales (~1h)", callback_data="btn_oficiales_1h"))
        elif action_type in ("corners", "players", "full"):
            nav_row.append(InlineKeyboardButton("⚽ Todos los Partidos Hoy", callback_data="btn_partidos_hoy"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("🔙 Volver al Menú Principal", callback_data="btn_main_menu")])

        if not games:
            if action_type == "oficiales":
                text = (
                    f"{header_title}\n\n"
                    "⏳ <i>Actualmente no hay partidos que comiencen en la próxima hora con alineación oficial publicada.</i>\n\n"
                    "📌 <b>¿Cuándo salen las alineaciones?</b>\n"
                    "Las ligas y clubes oficiales publican sus 11 titulares entre <b>45 y 60 minutos antes</b> del pitazo inicial.\n\n"
                    "💡 <b>¿Quieres planificar con antelación?</b>\n"
                    "Consulta los partidos en la sección <b>Horas Antes (Once Habitual)</b> para proyectar con los titulares más repetidos en sus últimos partidos."
                )
            else:
                text = (
                    f"{header_title}\n\n"
                    "No hay partidos programados en las próximas horas para las ligas monitoreadas.\n"
                    "Puedes buscar cualquier partido directamente escribiendo:\n"
                    f"• <code>/{action_type} [equipo]</code> (ej: <code>/{action_type} Real Madrid</code>)"
                )
        else:
            text = (
                f"{header_title}\n\n"
                f"{subtitle}"
            )

        return text, InlineKeyboardMarkup(buttons)
    finally:
        await scraper.close()


def get_assistant_navigation_keyboard(gid: str, current_view: str) -> InlineKeyboardMarkup:
    """Genera la botonera de navegación entre vistas de Córners, Jugadores y Completo."""
    row = []
    if current_view != "corners":
        row.append(InlineKeyboardButton("🚩 Ver Córners", callback_data=f"crn_{gid}"))
    if current_view != "players":
        row.append(InlineKeyboardButton("🎯 Ver Jugadores", callback_data=f"ply_{gid}"))
    if current_view != "full":
        row.append(InlineKeyboardButton("📋 Ver Completo", callback_data=f"ful_{gid}"))

    return InlineKeyboardMarkup([
        row,
        [
            InlineKeyboardButton("⚽ Volver a Partidos", callback_data="btn_partidos_hoy"),
            InlineKeyboardButton("🏠 Menú", callback_data="btn_main_menu")
        ]
    ])


async def corners_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /corners [equipo]: Análisis de tiros de esquina sobre 10 partidos."""
    if context.args:
        query = " ".join(context.args).strip().lower()
        wait_msg = await update.message.reply_html(f"🔍 Buscando <b>'{query}'</b> y analizando últimos 10 partidos de córners...")
        scraper = Scraper365()
        try:
            games = await scraper.fetch_assistant_matches(hours_ahead=48, min_tier=3)
            matched = None
            for g in games:
                h = g.get("homeCompetitor", {}).get("name", "").lower()
                a = g.get("awayCompetitor", {}).get("name", "").lower()
                if query in h or query in a:
                    matched = g
                    break
            if not matched:
                await wait_msg.edit_text(f"❌ No se encontró ningún partido próximo o en juego para: <b>'{query}'</b>.", parse_mode="HTML", reply_markup=get_back_keyboard())
                return

            gid = matched.get("id")
            hid = matched.get("homeCompetitor", {}).get("id")
            aid = matched.get("awayCompetitor", {}).get("id")
            hn = matched.get("homeCompetitor", {}).get("name")
            an = matched.get("awayCompetitor", {}).get("name")

            data = await assistant_engine.analyze_match_corners(scraper.session, hid, aid, hn, an, game_id=gid)
            report = format_corners_report(data)
            await wait_msg.edit_text(report, parse_mode="HTML", reply_markup=get_assistant_navigation_keyboard(str(gid), "corners"))
        except Exception as e:
            logger.error(f"Error en corners_command: {e}", exc_info=True)
            await wait_msg.edit_text(f"❌ Error analizando córners: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()
    else:
        text, kb = await build_assistant_matches_keyboard("corners")
        if update.message:
            await update.message.reply_html(text, reply_markup=kb)
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def jugadores_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /jugadores [equipo]: Análisis de alineaciones, disparos y faltas de jugador."""
    if context.args:
        query = " ".join(context.args).strip().lower()
        wait_msg = await update.message.reply_html(f"🔍 Buscando <b>'{query}'</b> y consultando alineaciones y jugadores...")
        scraper = Scraper365()
        try:
            games = await scraper.fetch_assistant_matches(hours_ahead=48, min_tier=3)
            matched = None
            for g in games:
                h = g.get("homeCompetitor", {}).get("name", "").lower()
                a = g.get("awayCompetitor", {}).get("name", "").lower()
                if query in h or query in a:
                    matched = g
                    break
            if not matched:
                await wait_msg.edit_text(f"❌ No se encontró ningún partido próximo o en juego para: <b>'{query}'</b>.", parse_mode="HTML", reply_markup=get_back_keyboard())
                return

            gid = matched.get("id")
            hid = matched.get("homeCompetitor", {}).get("id")
            aid = matched.get("awayCompetitor", {}).get("id")
            hn = matched.get("homeCompetitor", {}).get("name")
            an = matched.get("awayCompetitor", {}).get("name")

            data = await assistant_engine.analyze_match_players(scraper.session, gid, hid, aid, hn, an)
            report = format_players_report(data)
            await wait_msg.edit_text(report, parse_mode="HTML", reply_markup=get_assistant_navigation_keyboard(str(gid), "players"))
        except Exception as e:
            logger.error(f"Error en jugadores_command: {e}", exc_info=True)
            await wait_msg.edit_text(f"❌ Error analizando jugadores: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()
    else:
        text, kb = await build_assistant_matches_keyboard("players")
        if update.message:
            await update.message.reply_html(text, reply_markup=kb)
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def ayudante_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /ayudante [equipo]: Reporte completo de Córners + Jugadores."""
    if context.args:
        query = " ".join(context.args).strip().lower()
        wait_msg = await update.message.reply_html(f"🔍 Buscando <b>'{query}'</b> y generando informe completo del ayudante...")
        scraper = Scraper365()
        try:
            games = await scraper.fetch_assistant_matches(hours_ahead=48, min_tier=3)
            matched = None
            for g in games:
                h = g.get("homeCompetitor", {}).get("name", "").lower()
                a = g.get("awayCompetitor", {}).get("name", "").lower()
                if query in h or query in a:
                    matched = g
                    break
            if not matched:
                await wait_msg.edit_text(f"❌ No se encontró ningún partido próximo o en juego para: <b>'{query}'</b>.", parse_mode="HTML", reply_markup=get_back_keyboard())
                return

            gid = matched.get("id")
            hid = matched.get("homeCompetitor", {}).get("id")
            aid = matched.get("awayCompetitor", {}).get("id")
            hn = matched.get("homeCompetitor", {}).get("name")
            an = matched.get("awayCompetitor", {}).get("name")

            data = await assistant_engine.analyze_full_match(scraper.session, gid, hid, aid, hn, an)
            report = format_full_match_report(data)
            await wait_msg.edit_text(report, parse_mode="HTML", reply_markup=get_assistant_navigation_keyboard(str(gid), "full"))
        except Exception as e:
            logger.error(f"Error en ayudante_command: {e}", exc_info=True)
            await wait_msg.edit_text(f"❌ Error generando informe del ayudante: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()
    else:
        text, kb = await build_assistant_matches_keyboard("full")
        if update.message:
            await update.message.reply_html(text, reply_markup=kb)
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def combinada_ayudante_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera un ticket combinado combinando líneas de Córners y Props de Jugadores."""
    if update.callback_query:
        await update.callback_query.edit_message_text("🎰 <i>Calculando combinada especializada de Córners & Jugadores...</i>", parse_mode="HTML")
    elif update.message:
        await update.message.reply_html("🎰 <i>Calculando combinada especializada de Córners & Jugadores...</i>")

    scraper = Scraper365()
    try:
        games = await scraper.fetch_assistant_matches(hours_ahead=24, min_tier=2)
        if len(games) < 2:
            msg = "⚠️ Se requieren al menos 2 partidos destacados programados para armar la combinada de Córners y Jugadores."
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=get_back_keyboard())
            elif update.message:
                await update.message.reply_text(msg, reply_markup=get_back_keyboard())
            return

        # Analizar primer partido para córners
        g1 = games[0]
        c1 = await assistant_engine.analyze_match_corners(
            scraper.session,
            g1.get("homeCompetitor",{}).get("id"),
            g1.get("awayCompetitor",{}).get("id"),
            g1.get("homeCompetitor",{}).get("name"),
            g1.get("awayCompetitor",{}).get("name"),
            game_id=g1.get("id")
        )

        # Analizar segundo partido para props de jugador
        g2 = games[1]
        p2 = await assistant_engine.analyze_match_players(
            scraper.session,
            g2.get("id"),
            g2.get("homeCompetitor",{}).get("id"),
            g2.get("awayCompetitor",{}).get("id"),
            g2.get("homeCompetitor",{}).get("name"),
            g2.get("awayCompetitor",{}).get("name")
        )

        top_player = p2["top_shots_on_target"][0] if p2["top_shots_on_target"] else (p2["top_total_shots"][0] if p2["top_total_shots"] else None)

        lines = [
            "🎰 <b>COMBINADA ESPECIALIZADA (CÓRNERS + PROPS)</b> 🎰\n",
            f"1️⃣ <b>{g1.get('homeCompetitor',{}).get('name')} vs {g1.get('awayCompetitor',{}).get('name')}</b>",
            f"   🚩 Mercado: <b>{c1['recommended_line']}</b>",
            f"   📊 Confianza: {c1['confidence']}% | Proyección: {c1['projected_total']} córners\n"
        ]

        if top_player:
            lines.extend([
                f"2️⃣ <b>{g2.get('homeCompetitor',{}).get('name')} vs {g2.get('awayCompetitor',{}).get('name')}</b>",
                f"   🎯 Jugador: <b>{top_player['player']}</b> ({top_player['team']})",
                f"   👉 Línea: <b>{top_player['line']}</b> [@ {top_player['odd']}]",
                f"   📋 Alineación: {p2['lineup_status_text']}\n"
            ])

        lines.extend([
            "💵 <b>CUOTA TOTAL ESTIMADA:</b> <code>2.40 - 2.95</code>",
            "🏦 <b>STAKE RECOMENDADO:</b> <code>2 / 5</code>\n",
            "💡 <i>Ticket generado a partir del análisis de últimos 10 partidos y promedios individuales.</i>"
        ])

        msg = "\n".join(lines)
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_html(msg, reply_markup=get_back_keyboard())

    except Exception as e:
        logger.error(f"Error generando combinada ayudante: {e}", exc_info=True)
        err_msg = f"❌ Error armando combinada: {e}"
        if update.callback_query:
            await update.callback_query.edit_message_text(err_msg, reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_text(err_msg, reply_markup=get_back_keyboard())
    finally:
        await scraper.close()


# ── Manejador de Botones Táctiles (Callback Queries) ──────────────────────────

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestiona los toques en los botones InlineKeyboardMarkup."""
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id
    if not chat_id:
        return

    if data == "btn_main_menu":
        await query.edit_message_text(
            "📱 <b>PANEL DE CONTROL PRINCIPAL</b> 📱\n"
            "Elige la opción que deseas consultar:",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )

    # Botones del Ayudante
    elif data == "btn_ayudante_corners":
        text, keyboard = await build_assistant_matches_keyboard("corners")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data == "btn_ayudante_players":
        text, keyboard = await build_assistant_matches_keyboard("players")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data == "btn_oficiales_1h":
        text, keyboard = await build_assistant_matches_keyboard("oficiales")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data == "btn_horas_antes":
        text, keyboard = await build_assistant_matches_keyboard("horas_antes")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data == "btn_ayudante_full":
        text, keyboard = await build_assistant_matches_keyboard("full")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data == "btn_combinada_ayudante":
        await combinada_ayudante_command(update, context)

    elif data == "btn_partidos_hoy":
        await jornada_command(update, context)

    # Detalle de Córners (crn_{gid})
    elif data.startswith("crn_"):
        target_gid = data.replace("crn_", "").strip()
        await query.edit_message_text("🚩 <i>Consultando historial de últimos 10 partidos y promedios de córners...</i>", parse_mode="HTML")
        scraper = Scraper365()
        try:
            game_obj = await scraper.fetch_game_by_id(int(target_gid))
            if not game_obj:
                await query.edit_message_text("❌ No se pudo cargar la información del partido.", reply_markup=get_back_keyboard())
                return
            hid = game_obj.get("homeCompetitor", {}).get("id")
            aid = game_obj.get("awayCompetitor", {}).get("id")
            hn = game_obj.get("homeCompetitor", {}).get("name", "Local")
            an = game_obj.get("awayCompetitor", {}).get("name", "Visitante")
            h_rec = game_obj.get("homeCompetitor", {}).get("recentMatches")
            a_rec = game_obj.get("awayCompetitor", {}).get("recentMatches")

            c_data = await assistant_engine.analyze_match_corners(scraper.session, hid, aid, hn, an, h_rec, a_rec, game_id=int(target_gid))
            report = format_corners_report(c_data)
            await query.edit_message_text(report, parse_mode="HTML", reply_markup=get_assistant_navigation_keyboard(target_gid, "corners"))
        except Exception as e:
            logger.error(f"Error analizando córners por botón: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error analizando córners: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()

    # Detalle de Jugadores (ply_{gid})
    elif data.startswith("ply_"):
        target_gid = data.replace("ply_", "").strip()
        await query.edit_message_text("🎯 <i>Consultando alineación oficial/probable, disparos y faltas de jugadores...</i>", parse_mode="HTML")
        scraper = Scraper365()
        try:
            game_obj = await scraper.fetch_game_by_id(int(target_gid))
            if not game_obj:
                await query.edit_message_text("❌ No se pudo cargar la información del partido.", reply_markup=get_back_keyboard())
                return
            hid = game_obj.get("homeCompetitor", {}).get("id")
            aid = game_obj.get("awayCompetitor", {}).get("id")
            hn = game_obj.get("homeCompetitor", {}).get("name", "Local")
            an = game_obj.get("awayCompetitor", {}).get("name", "Visitante")

            p_data = await assistant_engine.analyze_match_players(scraper.session, int(target_gid), hid, aid, hn, an, game_obj=game_obj)
            report = format_players_report(p_data)
            await query.edit_message_text(report, parse_mode="HTML", reply_markup=get_assistant_navigation_keyboard(target_gid, "players"))
        except Exception as e:
            logger.error(f"Error analizando jugadores por botón: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error analizando jugadores: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()

    # Detalle Completo (ful_{gid})
    elif data.startswith("ful_"):
        target_gid = data.replace("ful_", "").strip()
        await query.edit_message_text("📋 <i>Generando informe completo: Córners (10 partidos) + Alineaciones y Jugadores...</i>", parse_mode="HTML")
        scraper = Scraper365()
        try:
            game_obj = await scraper.fetch_game_by_id(int(target_gid))
            if not game_obj:
                await query.edit_message_text("❌ No se pudo cargar la información del partido.", reply_markup=get_back_keyboard())
                return
            hid = game_obj.get("homeCompetitor", {}).get("id")
            aid = game_obj.get("awayCompetitor", {}).get("id")
            hn = game_obj.get("homeCompetitor", {}).get("name", "Local")
            an = game_obj.get("awayCompetitor", {}).get("name", "Visitante")

            f_data = await assistant_engine.analyze_full_match(scraper.session, int(target_gid), hid, aid, hn, an, game_obj=game_obj)
            report = format_full_match_report(f_data)
            await query.edit_message_text(report, parse_mode="HTML", reply_markup=get_assistant_navigation_keyboard(target_gid, "full"))
        except Exception as e:
            logger.error(f"Error analizando partido completo por botón: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error generando informe: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()

    elif data == "btn_analizar":
        text, keyboard = await build_analizar_matches_keyboard()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif data.startswith("anlz_"):
        target_gid = data.replace("anlz_", "").strip()
        await query.edit_message_text("🧠 <i>Procesando estadísticas tácticas con Director Técnico IA...</i>", parse_mode="HTML")
        scraper = Scraper365()
        try:
            live = await scraper.fetch_live_matches(filter_leagues=False, fetch_stats=True)
            upcoming = await scraper.fetch_upcoming_matches(hours_ahead=24, filter_leagues=False)

            target_game = None
            is_live = False
            for g in live:
                if str(g.get("id")) == target_gid:
                    target_game = g
                    is_live = True
                    break

            if not target_game:
                for g in upcoming:
                    if str(g.get("id")) == target_gid:
                        target_game = g
                        is_live = False
                        break

            if not target_game:
                await query.edit_message_text("❌ No se encontró la información del partido solicitado.", reply_markup=get_back_keyboard())
                return

            state = await graph_engine.evaluate_match(target_game, is_live=is_live, force_llm=True)
            report = format_tactical_analysis_report(state)
            await query.edit_message_text(report, parse_mode="HTML", reply_markup=get_back_keyboard())
        except Exception as e:
            logger.error(f"Error analizando partido por botón: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error analizando partido: {e}", reply_markup=get_back_keyboard())
        finally:
            await scraper.close()

    elif data == "btn_combinada":
        await combinada_command(update, context)

    elif data == "btn_bankroll":
        await bankroll_command(update, context)

    elif data == "btn_stats":
        await stats_command(update, context)

    elif data == "btn_historial":
        await historial_command(update, context)

    elif data == "btn_live" or data == "btn_upcoming":
        await jornada_command(update, context)

    elif data == "btn_status":
        await status_command(update, context)

    elif data == "btn_prefs":
        await query.edit_message_text(
            "⚙️ <b>CONFIGURACIÓN DE ALERTAS PERSONALES</b> ⚙️\n\n"
            "Personaliza qué tipo de notificaciones deseas recibir en tiempo real.\n"
            "Toca cada botón para activar o desactivar:",
            parse_mode="HTML",
            reply_markup=get_prefs_keyboard(chat_id)
        )

    elif data == "toggle_live":
        sub = get_subscriber_data(chat_id) or {}
        curr = sub.get("notify_live", 1)
        update_subscriber_prefs(chat_id, notify_live=0 if curr == 1 else 1)
        await query.edit_message_reply_markup(reply_markup=get_prefs_keyboard(chat_id))

    elif data == "toggle_upcoming":
        sub = get_subscriber_data(chat_id) or {}
        curr = sub.get("notify_upcoming", 1)
        update_subscriber_prefs(chat_id, notify_upcoming=0 if curr == 1 else 1)
        await query.edit_message_reply_markup(reply_markup=get_prefs_keyboard(chat_id))

    elif data == "toggle_pause":
        sub = get_subscriber_data(chat_id) or {}
        curr = sub.get("is_paused", 0)
        set_paused(chat_id, False if curr == 1 else True)
        await query.edit_message_reply_markup(reply_markup=get_prefs_keyboard(chat_id))


# ── Constructor de la Aplicación ───────────────────────────────────────────────

def create_application() -> Application:
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("No se encontró TELEGRAM_TOKEN ni TELEGRAM_BOT_TOKEN en el entorno.")

    app = Application.builder().token(token).build()

    # Comandos Principales
    app.add_handler(CommandHandler("start",     start_command))
    app.add_handler(CommandHandler("menu",      menu_command))
    app.add_handler(CommandHandler("status",    status_command))

    # Comandos del Ayudante (Córners y Jugadores)
    app.add_handler(CommandHandler("corners",   corners_command))
    app.add_handler(CommandHandler("corner",    corners_command))
    app.add_handler(CommandHandler("jugadores", jugadores_command))
    app.add_handler(CommandHandler("jugador",   jugadores_command))
    app.add_handler(CommandHandler("disparos",  jugadores_command))
    app.add_handler(CommandHandler("tiros",     jugadores_command))
    app.add_handler(CommandHandler("ayudante",  ayudante_command))
    app.add_handler(CommandHandler("asistente", ayudante_command))

    # Comandos de Rendimiento y Apuestas
    app.add_handler(CommandHandler("combinada", combinada_ayudante_command))
    app.add_handler(CommandHandler("parlay",    combinada_ayudante_command))
    app.add_handler(CommandHandler("bankroll",  bankroll_command))
    app.add_handler(CommandHandler("historial", historial_command))
    app.add_handler(CommandHandler("stats",     stats_command))
    app.add_handler(CommandHandler("jornada",   jornada_command))
    app.add_handler(CommandHandler("partidos",  jornada_command))
    app.add_handler(CommandHandler("pause",     pause_command))
    app.add_handler(CommandHandler("resume",    resume_command))
    app.add_handler(CommandHandler("analizar",  analizar_command))
    app.add_handler(CommandHandler("debug",     debug_command))
    app.add_handler(CommandHandler("debugodds", debugodds_command))

    # Manejador de botones táctiles
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    return app

