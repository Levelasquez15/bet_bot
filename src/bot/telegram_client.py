import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.bot.subscribers import add_subscriber, get_subscribers, set_paused
from src.bot.pick_tracker import get_stats, get_recent_picks
from src.scraper.scraper_365 import Scraper365

logger = logging.getLogger(__name__)

STATUS_EMOJI = {
    "GANADO":          "✅",
    "PERDIDO":         "❌",
    "PENDIENTE":       "⏳",
    "NO_VERIFICABLE":  "⚪",
}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user    = update.effective_user
    chat_id = update.effective_chat.id
    is_new  = add_subscriber(chat_id)

    if is_new:
        logger.info(f"Nuevo suscriptor: {chat_id} ({user.full_name})")
        await update.message.reply_html(
            rf"¡Hola {user.mention_html()}! Soy 365BetBot. 🤖"
            "\n\n✅ <b>¡Registrado con éxito!</b>"
            "\nRecibirás alertas de partidos <b>en vivo</b> y <b>próximos</b>."
            "\n\n📊 Tecnología:"
            "\n  • 8 árboles de decisión (live)"
            "\n  • Modelo Poisson (pre-partido)"
            "\n  • Verificación automática de resultados"
            "\n<b>Comandos disponibles:</b>"
            "\n/status — Estado del motor"
            "\n/historial — Últimos 10 picks enviados"
            "\n/stats — Tu tasa de acierto"
            "\n/pause — Pausa las notificaciones"
            "\n/resume — Reactiva las notificaciones"
            "\n/debug — Datos en tiempo real del scraper"
        )
    else:
        await update.message.reply_html(
            rf"¡Hola de nuevo {user.mention_html()}! 👋"
            "\n\nYa estás registrado. Sigo analizando cada 2 minutos. 🔄"
            "\nUsa /historial o /stats para ver el rendimiento del bot. 🎯"
        )
    set_paused(chat_id, False)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs  = get_subscribers()
    stats = get_stats()
    await update.message.reply_html(
        "📊 <b>Estado del Motor BetBot</b>\n\n"
        "✅ Scraping 365scores: ACTIVO\n"
        "✅ Análisis en Vivo (8 árboles): ACTIVO\n"
        "✅ Análisis Próximos (Poisson): ACTIVO\n"
        "✅ Verificación de resultados: ACTIVO\n"
        f"👥 Suscriptores: {len(subs)}\n"
        f"📈 Picks totales enviados: {stats['total']}\n"
        f"🏆 Efectividad: {stats['efectividad']}%\n"
        "⏱️ Ciclos: 2min (señales) | 10min (resultados)"
    )


async def historial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra los últimos 10 picks con su resultado."""
    picks = get_recent_picks(limit=10)
    if not picks:
        await update.message.reply_text("📭 Aún no hay picks en el historial.")
        return

    lines = ["📋 <b>Últimos 10 Picks</b>\n"]
    for p in picks:
        emoji  = STATUS_EMOJI.get(p["status"], "❓")
        tipo   = "🔴 LIVE" if p["type"] == "live" else "📅 PRE"
        score  = f" → Final: {p['final_score']}" if p["final_score"] else ""
        lines.append(
            f"{emoji} [{tipo}] <b>{p['match']}</b>\n"
            f"   🎯 {p['market']}\n"
            f"   {p['timestamp']}{score}\n"
        )

    await update.message.reply_html("\n".join(lines))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra estadísticas de rendimiento del bot."""
    s = get_stats()

    if s["total"] == 0:
        await update.message.reply_text("📭 Aún no hay picks registrados para calcular estadísticas.")
        return

    bar_won  = "🟩" * min(s["ganados"],  10)
    bar_lost = "🟥" * min(s["perdidos"], 10)

    await update.message.reply_html(
        f"📊 <b>Estadísticas del Bot</b>\n\n"
        f"📦 Total picks enviados: <b>{s['total']}</b>\n\n"
        f"✅ Ganados:         <b>{s['ganados']}</b>   {bar_won}\n"
        f"❌ Perdidos:        <b>{s['perdidos']}</b>   {bar_lost}\n"
        f"⏳ Pendientes:      <b>{s['pendientes']}</b>\n"
        f"⚪ No verificables: <b>{s['no_verif']}</b>\n\n"
        f"🏆 <b>Efectividad: {s['efectividad']}%</b>\n"
        f"<i>(sobre {s['ganados'] + s['perdidos']} picks verificados)</i>"
    )


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    set_paused(chat_id, True)
    await update.message.reply_html("🔇 <b>Bot Pausado.</b>\nYa no recibirás alertas de apuestas. Usa /resume para reactivar.")

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    set_paused(chat_id, False)
    await update.message.reply_html("🔊 <b>Bot Reactivado.</b>\nVuelves a estar en la lista prioritaria para recibir picks.")

async def debugodds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔍 Extrayendo el JSON de un partido con cuotas para análisis... un momento.")
    scraper = Scraper365()
    try:
        games = await scraper.fetch_live_matches()
        game_con_cuotas = next((g for g in games if "odds" in g or "bookmakers" in g), None)
        if game_con_cuotas:
            import json
            bookmakers = game_con_cuotas.get("bookmakers", [])
            odds = game_con_cuotas.get("odds", {})
            report = {
                "match": f"{game_con_cuotas.get('homeCompetitor', {}).get('name')} vs {game_con_cuotas.get('awayCompetitor', {}).get('name')}",
                "odds_key": odds,
                "bookmakers_key": bookmakers
            }
            json_text = json.dumps(report, ensure_ascii=False, indent=2)
            # Limpiar longitud
            if len(json_text) > 3000:
                json_text = json_text[:3000] + "\n...[TRUNCATED]"
            await update.message.reply_html(f"<b>RAW JSON (Cuotas):</b>\n<pre>{json_text}</pre>")
        else:
            await update.message.reply_text("❌ No encontré ningún partido en vivo con nodo 'odds' o 'bookmakers' en este instante.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error en debugodds: {e}")
    finally:
        await scraper.close()

def create_application() -> Application:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("No se encontró TELEGRAM_TOKEN en el entorno.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",     start_command))
    app.add_handler(CommandHandler("status",    status_command))
    app.add_handler(CommandHandler("historial", historial_command))
    app.add_handler(CommandHandler("stats",     stats_command))
    app.add_handler(CommandHandler("pause",     pause_command))
    app.add_handler(CommandHandler("resume",    resume_command))
    app.add_handler(CommandHandler("debug",     debug_command))
    app.add_handler(CommandHandler("debugodds", debugodds_command))

    return app
