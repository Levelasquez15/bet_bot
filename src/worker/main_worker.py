import logging
import os
from telegram.ext import ContextTypes
from src.scraper.scraper_365 import Scraper365
from src.analyzer.logic_tree import LogicTreeAnalyzer
from src.bot.subscribers import get_subscribers
from src.bot.pick_tracker import record_pick
from src.worker.result_checker import setup_result_checker

logger = logging.getLogger(__name__)

_sent_picks: set = set()


def format_live_pick(pick: dict) -> str:
    stake = 4 if pick["confidence"] >= 80 else 3 if pick["confidence"] >= 73 else 2
    return (
        f"🤖⚽🤖 <b>ROBOT APUESTA</b> ⚽🤖⚽\n\n"
        f"<b>{pick['match']}</b>\n\n"
        f"{pick['market']}\n\n"
        f"🏦 <b>CONFIANZA</b> 🏦 👉 {pick['confidence']}%\n\n"
        f"⏱️ Minuto: {pick['minute']}'\n"
        f"💡 {pick['reason']}\n\n"
        f"STAKE {stake}"
    )


def format_upcoming_pick(pick: dict) -> str:
    stake = 3 if pick["confidence"] >= 78 else 2
    return (
        f"📅⚽ <b>ANÁLISIS PRE-PARTIDO</b> ⚽📅\n\n"
        f"<b>{pick['match']}</b>\n"
        f"🕐 Inicio: {pick['minute']}\n\n"
        f"{pick['market']}\n\n"
        f"📊 <b>PROBABILIDAD</b> 📊 👉 {pick['confidence']}%\n"
        f"💡 {pick['reason']}\n\n"
        f"STAKE {stake}"
    )


async def _broadcast(context, picks: list, formatter, game_map: dict, pick_type: str) -> None:
    """Envía picks a todos los suscriptores y los registra en el tracker."""
    global _sent_picks
    subscribers = get_subscribers()

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
    """Tarea principal: cada 2 minutos analiza en vivo + próximos."""
    logger.info("━━━ Ciclo de escaneo ━━━")
    scraper  = Scraper365()
    analyzer = LogicTreeAnalyzer()

    try:
        # ── En Vivo ────────────────────────────────────────────
        live_games = await scraper.fetch_live_matches()
        if live_games:
            picks = analyzer.analyze_live(live_games)
            if picks:
                # Enriquecer picks con score actual para el tracker
                live_map = {}
                score_lookup = {}
                for g in live_games:
                    h = g.get("homeCompetitor", {}).get("name", "")
                    a = g.get("awayCompetitor", {}).get("name", "")
                    key = f"{h} - {a}"
                    live_map[key]    = str(g.get("id", ""))
                    score_lookup[key] = (
                        g.get("homeCompetitor", {}).get("score", 0),
                        g.get("awayCompetitor", {}).get("score", 0)
                    )
                for pick in picks:
                    sh, sa = score_lookup.get(pick["match"], (0, 0))
                    pick["score_home"] = sh
                    pick["score_away"] = sa
                await _broadcast(context, picks, format_live_pick, live_map, "live")
        else:
            logger.info("Sin partidos en vivo.")

        # ── Próximos ───────────────────────────────────────────
        upcoming_games = await scraper.fetch_upcoming_matches(hours_ahead=3)
        if upcoming_games:
            picks = analyzer.analyze_upcoming(upcoming_games)
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
