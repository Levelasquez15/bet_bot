import logging
import os
from telegram.ext import ContextTypes
from src.scraper.scraper_365 import Scraper365
from src.analyzer.logic_tree import LogicTreeAnalyzer
from src.bot.subscribers import add_subscriber, get_active_subscribers, get_active_subscribers_for_type
from src.bot.pick_tracker import record_pick
from src.worker.result_checker import setup_result_checker

from src.graph.decision_graph import DecisionGraph

logger = logging.getLogger(__name__)

_sent_picks: set = set()


def format_live_pick(pick: dict) -> str:
    stake = pick.get("recommended_stake") or (4 if pick["confidence"] >= 80 else 3 if pick["confidence"] >= 73 else 2)
    tactical = f"\n🧠 <b>TÁCTICA IA:</b> {pick['tactical_report']}" if pick.get("tactical_report") else ""
    try:
        min_disp = str(int(float(pick["minute"])))
    except (ValueError, TypeError):
        min_disp = str(pick.get("minute", "Live")).replace("'", "")
    return (
        f"🤖⚽🤖 <b>ROBOT APUESTA (LIVE)</b> ⚽🤖⚽\n\n"
        f"<b>{pick['match']}</b>\n\n"
        f"{pick['market']}\n\n"
        f"💶 <b>CUOTA</b> 👉 {pick.get('odd', 'Validada ✅')}\n\n"
        f"🏦 <b>CONFIANZA</b> 🏦 👉 {pick['confidence']}%\n\n"
        f"⏱️ Minuto: {min_disp}'\n"
        f"💡 {pick['reason']}{tactical}\n\n"
        f"STAKE {stake}"
    )


def format_upcoming_pick(pick: dict) -> str:
    v_info = pick.get("value_info")
    stake = pick.get("recommended_stake") or (v_info.get("recommended_stake", 2) if v_info else (3 if pick["confidence"] >= 78 else 2))
    ev_str = f"\n📈 <b>VALOR ESPERADO (EV):</b> +{v_info['ev_pct']}%\n🎯 <b>CUOTA JUSTA:</b> {v_info['fair_odd']}" if v_info else ""
    tactical = f"\n🧠 <b>TÁCTICA IA:</b> {pick['tactical_report']}" if pick.get("tactical_report") else ""
    return (
        f"📅⚽ <b>ANÁLISIS PRE-PARTIDO (VALUE BET)</b> ⚽📅\n\n"
        f"<b>{pick['match']}</b>\n"
        f"🕐 Inicio: {pick['minute']}\n\n"
        f"{pick['market']}\n\n"
        f"💶 <b>CUOTA CASA</b> 👉 {pick.get('odd', 'Validada ✅')}{ev_str}\n\n"
        f"📊 <b>PROBABILIDAD</b> 📊 👉 {pick['confidence']}%\n"
        f"💡 {pick['reason']}{tactical}\n\n"
        f"STAKE {stake}"
    )


async def _broadcast(context, picks: list, formatter, game_map: dict, pick_type: str) -> None:
    """Envía picks a los suscriptores activos según sus preferencias."""
    global _sent_picks
    subscribers = get_active_subscribers_for_type(pick_type)

    if not subscribers:
        logger.warning(f"{len(picks)} señal(es) sin suscriptores para enviar.")
        return

    for pick in picks:
        pick_key = f"{pick['match']}|{pick['market']}"
        if pick_key in _sent_picks:
            continue

        msg = formatter(pick)
        sent_to = 0

        for chat_id in subscribers:
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode="HTML"
                )
                sent_to += 1
            except Exception as e:
                logger.error(f"Error enviando a {chat_id}: {e}")

        if sent_to > 0:
            _sent_picks.add(pick_key)

            # Guardar en historial para verificación posterior
            game_id   = game_map.get(pick["match"], "unknown")
            sh        = pick.get("score_home", 0)
            sa        = pick.get("score_away", 0)
            score_str = f"{sh}-{sa}"
            record_pick(pick, game_id=game_id, score_at_pick=score_str, pick_type=pick_type)

            logger.info(f"✅ Enviado a {sent_to} usuario(s): {pick['match']} → {pick['market']}")

    if len(_sent_picks) > 500:
        _sent_picks.clear()


def _build_game_map(games: list) -> dict:
    """Construye un mapa match_name → game_id para el tracker."""
    gmap = {}
    for g in games:
        home = g.get("homeCompetitor", {}).get("name", "")
        away = g.get("awayCompetitor", {}).get("name", "")
        gmap[f"{home} - {away}"] = str(g.get("id", ""))
    return gmap


async def scraping_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tarea principal: cada 2 minutos analiza en vivo + próximos con el Grafo de Decisión."""
    logger.info("━━━ Ciclo de escaneo ━━━")
    scraper = Scraper365()
    graph = DecisionGraph()

    try:
        # ── En Vivo ────────────────────────────────────────────
        live_games = await scraper.fetch_live_matches()
        if live_games:
            picks = await graph.analyze_batch(live_games, is_live=True)
            if picks:
                live_map = _build_game_map(live_games)
                await _broadcast(context, picks, format_live_pick, live_map, "live")
        else:
            logger.info("Sin partidos en vivo.")

        # ── Próximos ───────────────────────────────────────────
        upcoming_games = await scraper.fetch_upcoming_matches(hours_ahead=3)
        if upcoming_games:
            picks = await graph.analyze_batch(upcoming_games, is_live=False)
            if picks:
                upcoming_map = _build_game_map(upcoming_games)
                for pick in picks:
                    pick["score_home"] = 0
                    pick["score_away"] = 0
                await _broadcast(context, picks, format_upcoming_pick, upcoming_map, "upcoming")
        else:
            logger.info("Sin partidos próximos en 3h.")

    except Exception as e:
        logger.error(f"Error en scraping_job: {e}", exc_info=True)
    finally:
        await scraper.close()
        logger.info("━━━ Ciclo completado ━━━")


def setup_worker(app) -> None:
    """Registra el worker principal y el verificador de resultados."""
    app.job_queue.run_repeating(scraping_job, interval=120, first=15)
    setup_result_checker(app)
    logger.info("⚙️  Workers activos: Scraping (2min) + Result Checker (10min).")
