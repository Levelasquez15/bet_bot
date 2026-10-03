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

logger = logging.getLogger(__name__)

# Instancia global del Grafo de Decisión y Director Técnico IA (Módulo 7)
graph_engine = DecisionGraph()

STATUS_EMOJI = {
    "GANADO":          "✅",
    "PERDIDO":         "❌",
    "PENDIENTE":       "⏳",
    "NO_VERIFICABLE":  "⚪",
}


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Genera la botonera táctil principal para la navegación de los usuarios."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 Analizar Partido (IA)", callback_data="btn_analizar"),
            InlineKeyboardButton("🎰 Armar Combinada", callback_data="btn_combinada"),
        ],
        [
            InlineKeyboardButton("💼 Mi Bankroll & ROI", callback_data="btn_bankroll"),
            InlineKeyboardButton("📊 Estadísticas", callback_data="btn_stats"),
        ],
        [
            InlineKeyboardButton("📋 Últimos Picks", callback_data="btn_historial"),
            InlineKeyboardButton("⚽ Partidos En Vivo", callback_data="btn_live"),
        ],
        [
            InlineKeyboardButton("📅 Próximos Partidos", callback_data="btn_upcoming"),
            InlineKeyboardButton("⚙️ Mis Preferencias", callback_data="btn_prefs"),
        ],
        [
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
        rf"¡Hola {user.mention_html()}! Soy <b>BetBot AI</b> 🤖⚽"
        "\n\nTu asistente inteligente de pronósticos deportivos con <b>Valor Esperado (+EV)</b>."
        "\n\n📊 <b>Tecnología Activa:</b>"
        "\n  • 8 árboles heurísticos con stats en vivo (xG, tiros a puerta, córners)"
        "\n  • Modelo matemático Poisson bivariado + Calibración Elo de clubes"
        "\n  • Value Betting matemático & Gestión de Stake con Criterio de Kelly"
        "\n  • Generador inteligente de apuestas combinadas (Parlays)"
        "\n  • Verificación y auditoría de balance relacional en SQLite"
        "\n\n👇 <i>Selecciona una opción del panel interactivo para comenzar:</i>"
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
        "📊 <b>Estado del Motor BetBot</b>\n\n"
        "✅ Ingestión 365scores: ACTIVO\n"
        "✅ Análisis en Vivo (Stats xG + Tiros + Córners): ACTIVO\n"
        "✅ Análisis Próximos (Poisson + Elo + Kelly): ACTIVO\n"
        "✅ Generador de Combinadas (+EV): ACTIVO\n"
        "✅ Base de Datos Relacional SQLite WAL: ACTIVO\n"
        "✅ Verificación de Resultados: ACTIVO\n"
        f"👥 Suscriptores Registrados: {len(subs)}\n"
        f"📈 Pronósticos Totales: {stats['total']}\n"
        f"🏆 Efectividad: {stats['efectividad']}%\n"
        "⏱️ Ciclos: 2min (escaneo) | 10min (verificación)"
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
    """Muestra el calendario de partidos monitoreados para hoy y en vivo."""
    scraper = Scraper365()
    try:
        live = await scraper.fetch_live_matches(filter_leagues=True, fetch_stats=False)
        upcoming = await scraper.fetch_upcoming_matches(hours_ahead=12, filter_leagues=True)

        lines = ["📅 <b>JORNADA DE FÚTBOL MONITOREADA HOY</b> 📅\n"]

        truly_live = []
        now_cur = datetime.now(tz=BOGOTA_TZ)
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

            truly_live.append(g)

        if truly_live:
            lines.append("🔴 <b>PARTIDOS EN VIVO AHORA:</b>")
            for g in truly_live[:6]:
                h = g.get("homeCompetitor", {}).get("name", "")
                a = g.get("awayCompetitor", {}).get("name", "")
                try:
                    sh = int(float(g.get("homeCompetitor", {}).get("score", 0)))
                    sa = int(float(g.get("awayCompetitor", {}).get("score", 0)))
                except (ValueError, TypeError):
                    sh, sa = 0, 0
                min_str = str(g.get("gameTimeDisplay") or g.get("gameTime") or "Live").replace("'", "")
                lines.append(f"  • {h} {sh}-{sa} {a} ⏱️ ({min_str}')")
            lines.append("")

        if upcoming:
            lines.append("⏳ <b>PRÓXIMOS DESTACADOS:</b>")
            for g in upcoming[:8]:
                h = g.get("homeCompetitor", {}).get("name", "")
                a = g.get("awayCompetitor", {}).get("name", "")
                st = g.get("startTime", "")[11:16] if g.get("startTime") else "Hoy"
                lines.append(f"  • <b>{h} vs {a}</b> 🕐 {st}")
        else:
            lines.append("Sin más partidos programados en las próximas 12 horas.")

        msg = "\n".join(lines)
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_html(msg, reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"Error en jornada_command: {e}", exc_info=True)
        if update.callback_query:
            await update.callback_query.edit_message_text(f"❌ Error consultando jornada: {e}", reply_markup=get_back_keyboard())
        elif update.message:
            await update.message.reply_text(f"❌ Error consultando jornada: {e}")
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

    # Comandos
    app.add_handler(CommandHandler("start",     start_command))
    app.add_handler(CommandHandler("menu",      menu_command))
    app.add_handler(CommandHandler("status",    status_command))
    app.add_handler(CommandHandler("combinada", combinada_command))
    app.add_handler(CommandHandler("parlay",    combinada_command))
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
